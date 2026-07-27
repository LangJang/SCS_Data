"""
ROMS vs CMEMS — spatio-temporal and vertical comparison.

Produces a systematic diff across the dimensions needed for
building a unified data structure.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import xarray as xr

from src.core.config import DATA_DIR_ROMS, DATA_DIR_CMEMS

# ── Paths (filenames are examples; update to match your data) ───────────────
ROMS_PATH  = DATA_DIR_ROMS / "roms_avg_20230122Z12.nc"
CMEMS_BGC  = DATA_DIR_CMEMS / "SCS_BGC_DO_CHL_2025.nc"
CMEMS_PH   = DATA_DIR_CMEMS / "SCS_BGC_PH_2023-2025.nc"

SEP = "=" * 68
SUB = "-" * 68


def load_quiet(path: Path) -> xr.Dataset:
    print(f"  Loading {path.name} ({path.stat().st_size / 1e9:.1f} GB) ...")
    return xr.open_dataset(path, engine="netcdf4")


def main():
    ds_r = load_quiet(ROMS_PATH)
    ds_c = load_quiet(CMEMS_BGC)   # representative CMEMS (has depth=75 levels)
    ds_ph = load_quiet(CMEMS_PH)

    # ══════════════════════════════════════════════════════════════════════
    # 1. SPATIAL COMPARISON
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{SEP}")
    print("  1. SPATIAL — Domain extent, resolution, grid type")
    print(SEP)

    # --- ROMS ---
    print(f"\n  {'ROMS':<10} | grid type: CURVILINEAR (lon_rho/lat_rho are 2-D)")
    lon_r = ds_r.lon_rho.values
    lat_r = ds_r.lat_rho.values
    print(f"  {'':<10} | lon_rho shape: {lon_r.shape}  (eta_rho × xi_rho)")
    print(f"  {'':<10} | lon range:    [{lon_r.min():.4f}, {lon_r.max():.4f}]")
    print(f"  {'':<10} | lat range:    [{lat_r.min():.4f}, {lat_r.max():.4f}]")
    # Approximate resolution from grid spacing at center
    cy, cx = lon_r.shape[0] // 2, lon_r.shape[1] // 2
    dx_r = np.abs(lon_r[cy, cx + 1] - lon_r[cy, cx]).item()
    dy_r = np.abs(lat_r[cy + 1, cx] - lat_r[cy, cx]).item()
    print(f"  {'':<10} | approx dx,dy at center: ({dx_r:.5f}°, {dy_r:.5f}°)")
    print(f"  {'':<10} | total grid points:     {lon_r.size:,}")

    # --- CMEMS ---
    print(f"\n  {'CMEMS':<10} | grid type: RECTILINEAR (1-D longitude/latitude)")
    lon_c = ds_c.longitude.values
    lat_c = ds_c.latitude.values
    print(f"  {'':<10} | longitude shape: {lon_c.shape}  (1-D)")
    print(f"  {'':<10} | latitude shape:  {lat_c.shape}  (1-D)")
    print(f"  {'':<10} | lon range:       [{lon_c.min():.4f}, {lon_c.max():.4f}]")
    print(f"  {'':<10} | lat range:       [{lat_c.min():.4f}, {lat_c.max():.4f}]")
    dx_c = np.abs(lon_c[1] - lon_c[0]).item()
    dy_c = np.abs(lat_c[1] - lat_c[0]).item()
    print(f"  {'':<10} | dx, dy:          ({dx_c:.5f}°, {dy_c:.5f}°)")
    print(f"  {'':<10} | total grid pts:  {lon_c.size * lat_c.size:,}")

    # --- OVERLAP ---
    print(f"\n  {'OVERLAP':<10}")
    olon = (max(lon_r.min(), lon_c.min()), min(lon_r.max(), lon_c.max()))
    olat = (max(lat_r.min(), lat_c.min()), min(lat_r.max(), lat_c.max()))
    print(f"  {'':<10} | lon overlap: [{olon[0]:.4f}, {olon[1]:.4f}] "
          f"({'OK' if olon[0] < olon[1] else 'NO OVERLAP'})")
    print(f"  {'':<10} | lat overlap: [{olat[0]:.4f}, {olat[1]:.4f}] "
          f"({'OK' if olat[0] < olat[1] else 'NO OVERLAP'})")

    # ══════════════════════════════════════════════════════════════════════
    # 2. TEMPORAL COMPARISON
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{SEP}")
    print("  2. TEMPORAL — Time range, frequency, alignment")
    print(SEP)

    print(f"\n  {'ROMS':<10} | time dim: 'ocean_time'")
    t_r = ds_r.ocean_time.values
    print(f"  {'':<10} | time steps: {len(t_r)}")
    print(f"  {'':<10} | value:      {t_r[0]} (single snapshot / average)")
    print(f"  {'':<10} | [!] ROMS file = 1 timestep only. Not a time series.")

    print(f"\n  {'CMEMS':<10} | time dim: 'time'")
    t_c = ds_c.time.values
    print(f"  {'':<10} | time steps: {len(t_c)}")
    print(f"  {'':<10} | start:      {t_c[0]}")
    print(f"  {'':<10} | end:        {t_c[-1]}")
    # Check frequency
    if len(t_c) >= 2:
        dt = np.diff(t_c.astype('datetime64[s]').astype(np.int64))
        uniq = np.unique(dt)
        freq_str = ", ".join(f"{u/3600:.0f}h" for u in uniq[:5])
        print(f"  {'':<10} | frequency:  {freq_str} ({'uniform' if len(uniq)==1 else 'irregular'})")

    print(f"\n  {'MATCH':<10}")
    # ROMS snapshot date vs CMEMS range
    roms_date = np.datetime64(t_r[0], 'D')
    c_start = np.datetime64(t_c[0], 'D')
    c_end = np.datetime64(t_c[-1], 'D')
    print(f"  {'':<10} | ROMS date:     {roms_date}")
    print(f"  {'':<10} | CMEMS range:   {c_start} → {c_end}")
    if c_start <= roms_date <= c_end:
        print(f"  {'':<10} | ✅ ROMS date falls WITHIN CMEMS range — can match")
    else:
        print(f"  {'':<10} | ❌ ROMS date outside CMEMS range")

    # ══════════════════════════════════════════════════════════════════════
    # 3. VERTICAL COMPARISON
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{SEP}")
    print("  3. VERTICAL — Coordinate type, levels, alignment challenge")
    print(SEP)

    print(f"\n  {'ROMS':<10} | vertical type: SIGMA (terrain-following s_rho)")
    print(f"  {'':<10} | s_rho layers: {ds_r.sizes['s_rho']}")
    print(f"  {'':<10} | s_w layers:   {ds_r.sizes['s_w']} (interfaces)")
    s_rho = ds_r.s_rho.values
    print(f"  {'':<10} | s_rho range:  [{s_rho.min():.4f}, {s_rho.max():.4f}]")
    print(f"  {'':<10} | ⚠ s_rho = fractional (0=bottom, 1=surface typically)")
    print(f"  {'':<10} |    Actual depth depends on bathymetry h(x,y) + zeta.")
    print(f"  {'':<10} |    No direct 'depth in meters' coordinate in file.")

    # ROMS: show bathymetry range to understand actual depth span
    h_r = ds_r.h.values
    print(f"  {'':<10} | bathymetry h:  min={h_r.min():.1f} m, "
          f"max={h_r.max():.1f} m, mean={h_r.mean():.1f} m")

    print(f"\n  {'CMEMS':<10} | vertical type: DEPTH (absolute meters)")
    depth_c = ds_c.depth.values
    print(f"  {'':<10} | depth levels:  {len(depth_c)}")
    print(f"  {'':<10} | depth range:   [{depth_c.min():.1f}, {depth_c.max():.1f}] m")
    print(f"  {'':<10} | surface index: 0 (depth[0] = {depth_c[0]:.1f} m)")
    print(f"  {'':<10} | bottom index:  {len(depth_c)-1} (depth[-1] = {depth_c[-1]:.1f} m)")

    # Depth spacing
    if len(depth_c) >= 2:
        d_diff = np.diff(depth_c)
        print(f"  {'':<10} | layer spacing: {d_diff[0]:.1f} m → {d_diff[-1]:.1f} m "
              f"(increasing with depth)")

    # CMEMS PH has different vertical structure
    depth_ph = ds_ph.depth.values
    print(f"\n  {'CMEMS-PH':<10} | depth levels: {len(depth_ph)}")
    print(f"  {'':<10} | depth range:  [{depth_ph.min():.1f}, {depth_ph.max():.1f}] m")
    print(f"  {'':<10} | ⚠ Different from BGC file ({len(depth_c)} vs {len(depth_ph)} levels)")

    print(f"\n  {'ALIGN':<10}")
    print(f"  {'':<10} | ROMS sigma → absolute depth requires:")
    print(f"  {'':<10} |   z(x,y,s) = h(x,y) * s  (+ zeta correction)")
    print(f"  {'':<10} |   → can compute ROMS depth at each grid point,")
    print(f"  {'':<10} |     then interpolate to CMEMS standard depth levels.")

    # ══════════════════════════════════════════════════════════════════════
    # 4. VARIABLE INVENTORY
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{SEP}")
    print("  4. VARIABLES — Inventory overlap")
    print(SEP)

    print(f"\n  {'ROMS':<25} {'CMEMS':<25} {'MATCH?':<10}")
    print(f"  {SUB}")
    roms_vars = {"temp": "temperature", "salt": "salinity", "u": "u_current",
                 "v": "v_current", "w": "w_velocity", "zeta": "sea_surface_height",
                 "ubar": "u_barotropic", "vbar": "v_barotropic"}
    cmems_vars = {"thetao": "temperature", "so": "salinity", "uo": "u_current",
                  "vo": "v_current", "wo": "w_velocity", "zos": "sea_surface_height",
                  "chl": "chlorophyll", "o2": "dissolved_oxygen", "ph": "ph",
                  "no3": "nitrate", "po4": "phosphate", "pp": "primary_production",
                  "mlotst": "mixed_layer_thickness"}

    all_canonical = set(roms_vars.values()) | set(cmems_vars.values())
    for canon in sorted(all_canonical):
        r_src = [k for k, v in roms_vars.items() if v == canon]
        c_src = [k for k, v in cmems_vars.items() if v == canon]
        r_str = ", ".join(r_src) if r_src else "—"
        c_str = ", ".join(c_src) if c_src else "—"
        match = "✅" if r_src and c_src else ("ROMS only" if r_src else "CMEMS only")
        print(f"  {r_str:<25} {c_str:<25} {match}")

    # ══════════════════════════════════════════════════════════════════════
    # 5. SUMMARY — Unified structure proposal
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{SEP}")
    print("  5. UNIFIED STRUCTURE — Key alignment tasks")
    print(SEP)

    print(f"""
  Spatial:
    ROMS  → regrid curvilinear → rectilinear (or vice versa)
    Target: common 1-D lon/lat grid at shared resolution (~0.083°)
    CMEMS is already rectilinear → use as reference grid

  Temporal:
    ROMS  → single snapshot. Match to nearest CMEMS timestep.
    CMEMS → 1096 daily steps. Subset to ROMS date or aggregate.

  Vertical:
    ROMS  → compute z = f(h, s_rho, zeta) → interpolate to depth levels
    CMEMS → already in depth (meters). Use as reference levels.
    Note: CMEMS-BGC has 75 levels, CMEMS-PH has 50 levels.

  Variables available in BOTH sources:
    temperature, salinity, u_current, v_current,
    w_velocity, sea_surface_height

  Variables in ONE source:
    ROMS-only:  u_barotropic, v_barotropic
    CMEMS-only: chlorophyll, dissolved_oxygen, pH (and others)
""")

    # Close
    for ds in [ds_r, ds_c, ds_ph]:
        ds.close()
    print("Done.")


if __name__ == "__main__":
    main()
