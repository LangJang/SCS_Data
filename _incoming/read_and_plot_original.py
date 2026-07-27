

import xarray as xr
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from pathlib import Path

plt.rcParams['font.size'] = 11
plt.rcParams['figure.dpi'] = 100

# Data directory relative to the notebooks/ folder
DATA_DIR = Path('D:/ChatWithAI/')
OUTPUT_DIR = Path('../output')

files = sorted(DATA_DIR.glob("*.nc"))
print(f'Found {len(files)} NetCDF files:')
for f in files:
    size_mb = f.stat().st_size / 1e6
    print(f'  {f.name}  ({size_mb:.1f} MB)')

PRODUCT_LABELS = {
    'phy-thetao': 'Potential Temperature (thetao)',
    'phy-so':     'Salinity (so)',
    'phy-cur':    'Ocean Currents (uo, vo)',
    'bgc-pft':    'Chlorophyll - PFT',
}

groups = {}
for f in files:
    # New naming: cmems_{product}_{res}_{start}_{end}.nc
    product = f.stem.split('_')[1]
    groups.setdefault(product, []).append(f)

for k, flist in groups.items():
    label = PRODUCT_LABELS.get(k, k)
    print(f'\n{k}  ({label})')
    print(f'  Files: {len(flist)}')
    for f in flist:
        print(f'    {f.name}')


datasets = {}
for product, flist in groups.items():
    f = flist[0]
    ds = xr.open_dataset(f, chunks={})
    datasets[product] = ds
    label = PRODUCT_LABELS.get(product, product)
    print(f'\n{"="*60}')
    print(f'  {label}')
    print(f'{"="*60}')
    print(f'  File: {f.name}')
    print(f'  Dims: {dict(ds.sizes)}')
    print(f'  Coords: {list(ds.coords)}')
    for v in ds.data_vars:
        da = ds[v]
        print(f'  Data var: {v}  dims={list(da.dims)}  dtype={da.dtype}')
        if hasattr(da, 'units'):
            print(f'    units: {da.units}')
        if hasattr(da, 'long_name'):
            print(f'    long_name: {da.long_name}')

    if 'time' in ds.coords:
        t = pd.to_datetime(ds.time.values)
        print(f'  Time: {t[0]} -> {t[-1]}  ({len(t)} steps)')

    for c in ['longitude', 'latitude']:
        if c in ds.coords:
            vals = ds[c].values
            print(f'  {c}: [{vals.min():.4f}, {vals.max():.4f}] ({len(vals)} pts)')

    if 'depth' in ds.coords:
        d = ds.depth.values
        print(f'  depth: [{d.min():.1f}, {d.max():.1f}] m ({len(d)} levels)')



# ============================================================
# ROMS nc single snapshot visualization
# One time + one sigma layer
# ============================================================

import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature


time_idx = 0
s_idx = 44      # surface rho layer


# ============================================================
# Prepare fields
# ============================================================

fields = {

    'zeta': (
        ds.zeta.isel(ocean_time=time_idx),
        ds.lon_rho,
        ds.lat_rho
    ),

    'ubar': (
        ds.ubar.isel(ocean_time=time_idx),
        ds.lon_u,
        ds.lat_u
    ),

    'vbar': (
        ds.vbar.isel(ocean_time=time_idx),
        ds.lon_v,
        ds.lat_v
    ),

    'temp': (
        ds.temp.isel(
            ocean_time=time_idx,
            s_rho=s_idx
        ),
        ds.lon_rho,
        ds.lat_rho
    ),

    'salt': (
        ds.salt.isel(
            ocean_time=time_idx,
            s_rho=s_idx
        ),
        ds.lon_rho,
        ds.lat_rho
    ),

    'u': (
        ds.u.isel(
            ocean_time=time_idx,
            s_rho=s_idx
        ),
        ds.lon_u,
        ds.lat_u
    ),

    'v': (
        ds.v.isel(
            ocean_time=time_idx,
            s_rho=s_idx
        ),
        ds.lon_v,
        ds.lat_v
    ),

    'w': (
        ds.w.isel(
            ocean_time=time_idx,
            s_w=s_idx
        ),
        ds.lon_rho,
        ds.lat_rho
    )
}


# ============================================================
# Current speed
# interpolate u/v to rho grid
# ============================================================


# ============================================================
# Plot
# ============================================================

for name, (da, lon, lat) in fields.items():

    print(f'Plotting {name}')

    fig, ax = plt.subplots(
        figsize=(10,7),
        subplot_kw={
            'projection':ccrs.PlateCarree()
        }
    )

    ax.add_feature(
        cfeature.COASTLINE,
        linewidth=0.5
    )

    ax.add_feature(
        cfeature.LAND,
        facecolor='0.9'
    )


    im=ax.pcolormesh(
        lon,
        lat,
        da,
        shading='auto',
        cmap='Spectral_r',
        transform=ccrs.PlateCarree()
    )


    plt.colorbar(
        im,
        ax=ax,
        shrink=0.75,
        label=da.attrs.get(
            'units',
            ''
        )
    )


    ax.set_title(
        f'ROMS {name}\n'
        f'time={time_idx}, sigma={s_idx}',
        fontsize=13
    )


    gl=ax.gridlines(
        draw_labels=True,
        linewidth=0.3,
        alpha=0.5
    )

    gl.top_labels=False
    gl.right_labels=False


    plt.tight_layout()

    plt.savefig(
        OUTPUT_DIR /
        f'roms_{name}_snapshot.png',
        dpi=200,
        bbox_inches='tight'
    )

    plt.close()


print("All ROMS snapshot plots finished.")

