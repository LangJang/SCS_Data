#!/usr/bin/env python3
"""
ROMS Sigma-to-Z Depth Level Extractor
======================================
将 ROMS 日平均文件中的地形跟随 S 坐标三维变量插值到固定深度层。

Depth levels (16 levels):
    0        - 表层 (surface)    : 直接取顶部 sigma 层值
    20,40,60,80,100,120,140,160,
    200,250,300,350,400          : 线性插值到固定深度
    -99999   - 底层 (bottom)     : 直接取底部 sigma 层值 (flag value)

Author: Generated for ROMS daily processing
Date: 2026-07-27
"""

import os
import sys
import time
import glob
import argparse
import numpy as np
import netCDF4 as nc
from datetime import datetime

# ============================================================================
# Configuration
# ============================================================================

# Vtransform=2 depth formula parameter (from file metadata)
HC = 100.0  # critical depth, will be read from file

# Target depth levels: 14 intermediate + surface + bottom
TARGET_DEPTHS = [20, 40, 60, 80, 100, 120, 140, 160, 200, 250, 300, 350, 400]
N_INTERP_DEPTHS = len(TARGET_DEPTHS)  # 14
N_TOTAL_DEPTHS = N_INTERP_DEPTHS + 2  # 16: surface + interp + bottom

OUTPUT_DEPTH_VALUES = np.array(
    [0.0] + TARGET_DEPTHS + [-99999.0], dtype=np.float32
)

# Variables with vertical dimension on s_rho (RHO points) or on specific grids
S_RHO_VARS = {
    'temp': {
        'dims': ('ocean_time', 's_rho', 'eta_rho', 'xi_rho'),
        'grid': 'rho',
        'long_name': 'potential temperature at depth levels',
        'units': 'Celsius',
    },
    'salt': {
        'dims': ('ocean_time', 's_rho', 'eta_rho', 'xi_rho'),
        'grid': 'rho',
        'long_name': 'salinity at depth levels',
        'units': '',
    },
}

S_RHO_U_VARS = {
    'u': {
        'dims': ('ocean_time', 's_rho', 'eta_u', 'xi_u'),
        'grid': 'u',
        'long_name': 'u-momentum component at depth levels',
        'units': 'meter second-1',
    },
}

S_RHO_V_VARS = {
    'v': {
        'dims': ('ocean_time', 's_rho', 'eta_v', 'xi_v'),
        'grid': 'v',
        'long_name': 'v-momentum component at depth levels',
        'units': 'meter second-1',
    },
}

S_W_VARS = {
    'w': {
        'dims': ('ocean_time', 's_w', 'eta_rho', 'xi_rho'),
        'grid': 'rho',  # horizontal grid is RHO, vertical is W
        'long_name': 'vertical momentum component at depth levels',
        'units': 'meter second-1',
    },
}

# All 3D variables to process: dict of var_name -> config
ALL_3D_VARS = {}
ALL_3D_VARS.update(S_RHO_VARS)
ALL_3D_VARS.update(S_RHO_U_VARS)
ALL_3D_VARS.update(S_RHO_V_VARS)
ALL_3D_VARS.update(S_W_VARS)

FILL_VALUE = np.float32(1.0e37)

# ============================================================================
# Depth computation
# ============================================================================


def compute_depth_field(zeta, h, s, Cs, hc):
    """
    Compute 3D depth field on the given grid.

    Vtransform=2 formula:
        z(σ) = ζ + (ζ + h) * (hc*σ + h*Cs(σ)) / (hc + h)

    Parameters
    ----------
    zeta : ndarray (ny, nx)
        Free-surface elevation.
    h : ndarray (ny, nx)
        Bathymetry (positive down).
    s : ndarray (ns,)
        S-coordinate values.
    Cs : ndarray (ns,)
        S-coordinate stretching curve.
    hc : float
        Critical depth parameter.

    Returns
    -------
    z : ndarray (ns, ny, nx)
        Depth at each sigma layer (negative values, 0 at surface).
    """
    ns = len(s)
    ny, nx = h.shape

    # Broadcast: (ns, ny, nx)
    s_3d = s[:, np.newaxis, np.newaxis]  # (ns, 1, 1)
    Cs_3d = Cs[:, np.newaxis, np.newaxis]  # (ns, 1, 1)
    h_3d = h[np.newaxis, :, :]  # (1, ny, nx)
    zeta_3d = zeta[np.newaxis, :, :]  # (1, ny, nx)

    numerator = hc * s_3d + h_3d * Cs_3d
    denominator = hc + h_3d
    S = numerator / denominator

    z = zeta_3d + (zeta_3d + h_3d) * S
    return z.astype(np.float32)


def compute_h_uv(h):
    """
    Compute bathymetry at U and V points by averaging adjacent RHO points.

    Parameters
    ----------
    h : ndarray (eta_rho, xi_rho)
        Bathymetry at RHO points.

    Returns
    -------
    h_u : ndarray (eta_u, xi_u)
    h_v : ndarray (eta_v, xi_v)
    """
    h_u = 0.5 * (h[:, :-1] + h[:, 1:])  # (eta_rho, xi_rho-1) = (eta_u, xi_u)
    h_v = 0.5 * (h[:-1, :] + h[1:, :])  # (eta_rho-1, xi_rho) = (eta_v, xi_v)
    return h_u, h_v


def compute_zeta_uv(zeta):
    """Compute free-surface at U and V points."""
    zeta_u = 0.5 * (zeta[:, :-1] + zeta[:, 1:])
    zeta_v = 0.5 * (zeta[:-1, :] + zeta[1:, :])
    return zeta_u, zeta_v


# ============================================================================
# Vectorized interpolation
# ============================================================================


def interp_to_depth_levels(data_3d, z_3d, h_2d, mask_2d, fill_value=FILL_VALUE):
    """
    Vertically interpolate 3D sigma-coordinate field to fixed depth levels
    using vectorized numpy operations.

    Parameters
    ----------
    data_3d : ndarray (ns, ny, nx), float32
        Field values on sigma layers.
    z_3d : ndarray (ns, ny, nx), float32
        Depth at each sigma layer (negative values).
    h_2d : ndarray (ny, nx), float32
        Bathymetry (positive down).
    mask_2d : ndarray (ny, nx)
        Land-sea mask (1=water, 0=land).

    Returns
    -------
    result : ndarray (16, ny, nx), float32
        Field values at output depth levels.
    """
    ns, ny, nx = data_3d.shape
    n_out = N_TOTAL_DEPTHS  # 16

    # Output array, filled initially
    result = np.full((n_out, ny, nx), fill_value, dtype=np.float32)

    # Water mask
    water = (mask_2d == 1)

    # --- Layer 0: Surface (top sigma layer) ---
    result[0, :, :] = np.where(water, data_3d[0, :, :], fill_value)

    # --- Layer 15: Bottom (bottom sigma layer) ---
    result[-1, :, :] = np.where(water, data_3d[-1, :, :], fill_value)

    # --- Layers 1-14: Interpolated fixed depths ---
    for i_depth, target_m in enumerate(TARGET_DEPTHS):
        target_z = -target_m  # convert to negative depth (e.g., -20.0)
        out_idx = i_depth + 1  # output layer index

        # Valid points: water AND deep enough (h >= target depth)
        # h is positive down, so h >= target_m means water deep enough
        valid = water & (h_2d >= target_m)

        if not np.any(valid):
            continue

        # Find bracketing sigma layers for each horizontal point
        # z_3d is sorted surface→bottom (z=0 at surface, z=-h at bottom)
        # Target z is negative (e.g., -20). We need z_3d[k] <= target_z < z_3d[k-1]
        # "below" means the layer is at or below the target depth
        below = z_3d <= target_z  # (ns, ny, nx)

        # k_below: first (topmost) layer at or below target depth
        # argmax on boolean: first True occurrence
        k_below = np.argmax(below, axis=0).astype(np.int32)  # (ny, nx)

        # k_above: layer just above target depth
        k_above = np.maximum(k_below - 1, 0)  # (ny, nx)

        # Handle case where target is above all layers (shouldn't happen for valid points)
        # or below the deepest layer (shouldn't happen due to valid filter)
        # But k_below could be 0 for points where z[0] <= target_z already
        # (target shallower than top sigma layer — surface layer case)
        j_idx = np.arange(ny)[:, np.newaxis]  # (ny, 1)
        i_idx = np.arange(nx)[np.newaxis, :]  # (1, nx)

        z_below = z_3d[k_below, j_idx, i_idx]  # (ny, nx)
        z_above = z_3d[k_above, j_idx, i_idx]  # (ny, nx)

        data_below = data_3d[k_below, j_idx, i_idx]  # (ny, nx)
        data_above = data_3d[k_above, j_idx, i_idx]  # (ny, nx)

        # Interpolation weight
        dz = z_above - z_below  # positive (z_above > z_below, since above is shallower/more positive)
        # Avoid division by zero
        with np.errstate(divide='ignore', invalid='ignore'):
            weight = np.where(
                (valid) & (np.abs(dz) > 1e-10),
                (target_z - z_below) / dz,
                0.0,
            )

        # Linear interpolation: value = data_below + weight * (data_above - data_below)
        interp_val = data_below + weight * (data_above - data_below)

        # Mask invalid points
        interp_val = np.where(valid, interp_val, fill_value)

        # Handle points where k_above == k_below (same layer, use that layer value)
        same_layer = (k_above == k_below) & valid
        interp_val = np.where(same_layer, data_above, interp_val)

        result[out_idx, :, :] = interp_val

    return result


# ============================================================================
# File processing
# ============================================================================


def process_file(input_path, output_path):
    """Process a single ROMS average file."""
    t_start = time.time()

    with nc.Dataset(input_path, 'r') as src:
        # --- Read essential fields ---
        h = src.variables['h'][:].astype(np.float32)
        mask_rho = src.variables['mask_rho'][:].astype(np.int32)
        zeta = src.variables['zeta'][0, :, :].astype(np.float32)  # (eta_rho, xi_rho)
        Cs_r = src.variables['Cs_r'][:].astype(np.float32)
        Cs_w = src.variables['Cs_w'][:].astype(np.float32)
        s_rho = src.variables['s_rho'][:].astype(np.float32)
        s_w = src.variables['s_w'][:].astype(np.float32)
        hc = float(src.variables['hc'][:])

        # Read masks for U, V points
        mask_u = src.variables['mask_u'][:].astype(np.int32)
        mask_v = src.variables['mask_v'][:].astype(np.int32)

        # --- Compute 3D depth fields ---
        # RHO grid depth (for temp, salt)
        z_rho = compute_depth_field(zeta, h, s_rho, Cs_r, hc)  # (45, eta_rho, xi_rho)

        # W grid depth (for w on RHO horizontal grid but W vertical)
        z_w = compute_depth_field(zeta, h, s_w, Cs_w, hc)  # (46, eta_rho, xi_rho)

        # U/V grid depth
        h_u, h_v = compute_h_uv(h)
        zeta_u, zeta_v = compute_zeta_uv(zeta)
        z_u = compute_depth_field(zeta_u, h_u, s_rho, Cs_r, hc)  # (45, eta_u, xi_u)
        z_v = compute_depth_field(zeta_v, h_v, s_rho, Cs_r, hc)  # (45, eta_v, xi_v)

        # --- Create output file (atomic: write to temp, rename on success) ---
        tmp_path = output_path + '.tmp'
        dst = nc.Dataset(tmp_path, 'w', format='NETCDF3_64BIT_OFFSET')

        # Minimal global attributes
        for attr in ['file', 'format', 'Conventions', 'type', 'title',
                     'grd_file', 'git_url', 'git_rev', 'svn_url',
                     'NLM_TADV', 'NLM_LBC']:
            if attr in src.ncattrs():
                dst.setncattr(attr, src.getncattr(attr))
        dst.setncattr(
            'history',
            f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} '
            f'sigma-to-z depth interpolation by depth_interp.py; '
            f'only depth-level variables retained',
        )
        dst.setncattr('depth_levels', 'surface, ' + ', '.join(
            [f'{d}m' for d in TARGET_DEPTHS]) + ', bottom')
        dst.setncattr('depth_interpolation', 'linear')
        dst.setncattr('note', 'Only variables with depth dimension are included. '
                      'For full fields (zeta, ubar, vbar, static grids, scalars), '
                      'refer to the original ROMS avg files.')

        # --- Create only necessary dimensions ---
        # Spatial dims needed by the 3D processed variables
        dim_map = {
            'ocean_time': None,  # unlimited
            'xi_rho': len(src.dimensions['xi_rho']),
            'eta_rho': len(src.dimensions['eta_rho']),
            'xi_u': len(src.dimensions['xi_u']),
            'eta_u': len(src.dimensions['eta_u']),
            'xi_v': len(src.dimensions['xi_v']),
            'eta_v': len(src.dimensions['eta_v']),
        }
        for dim_name, dim_size in dim_map.items():
            dst.createDimension(dim_name, dim_size)
        # New depth dimension (replaces s_rho/s_w)
        dst.createDimension('depth', N_TOTAL_DEPTHS)

        # --- Write depth coordinate variable ---
        depth_var = dst.createVariable('depth', 'f4', ('depth',))
        depth_var.long_name = 'target depth level'
        depth_var.units = 'meter'
        depth_var.positive = 'down'
        depth_var.flag_values = '-99999'
        depth_var.flag_meanings = 'bottom_layer_variable_depth'
        depth_var.comment = (
            'Depth levels: 0=surface (top sigma layer), '
            '20-400m=linearly interpolated, '
            '-99999=bottom (deepest sigma layer, depth varies spatially)'
        )
        depth_var[:] = OUTPUT_DEPTH_VALUES

        # --- Copy ocean_time ---
        ot = src.variables['ocean_time']
        dst_ot = dst.createVariable('ocean_time', ot.datatype, ('ocean_time',))
        for attr in ot.ncattrs():
            if attr != '_FillValue':
                try: dst_ot.setncattr(attr, ot.getncattr(attr))
                except Exception: pass
        dst_ot[:] = ot[:]

        # --- Copy georeferencing variables (lon/lat + mask for spatial plotting) ---
        geo_vars = {
            'lon_rho':  ('eta_rho', 'xi_rho'),
            'lat_rho':  ('eta_rho', 'xi_rho'),
            'lon_u':    ('eta_u',   'xi_u'),
            'lat_u':    ('eta_u',   'xi_u'),
            'lon_v':    ('eta_v',   'xi_v'),
            'lat_v':    ('eta_v',   'xi_v'),
            'mask_rho': ('eta_rho', 'xi_rho'),
            'mask_u':   ('eta_u',   'xi_u'),
            'mask_v':   ('eta_v',   'xi_v'),
        }
        for gname, gdims in geo_vars.items():
            gv = src.variables[gname]
            dvar = dst.createVariable(gname, gv.datatype, gdims)
            for attr in gv.ncattrs():
                if attr != '_FillValue':
                    try: dvar.setncattr(attr, gv.getncattr(attr))
                    except Exception: pass
            dvar[:] = gv[:]

        # --- Process 3D variables (only these are written) ---
        for var_name, var_cfg in ALL_3D_VARS.items():
            if var_name not in src.variables:
                print(f'  WARNING: {var_name} not found in file, skipping')
                continue

            print(f'  Processing {var_name}...', end=' ', flush=True)

            sv = src.variables[var_name]
            data = sv[0, :, :, :].astype(np.float32)  # (ns, ny, nx)

            grid = var_cfg['grid']
            if var_name == 'w':
                z_field = z_w
                h_field = h
                mask_field = mask_rho
            elif grid == 'rho':
                z_field = z_rho
                h_field = h
                mask_field = mask_rho
            elif grid == 'u':
                z_field = z_u
                h_field = h_u
                mask_field = mask_u
            elif grid == 'v':
                z_field = z_v
                h_field = h_v
                mask_field = mask_v
            else:
                raise ValueError(f'Unknown grid: {grid}')

            interp_data = interp_to_depth_levels(
                data, z_field, h_field, mask_field
            )  # (16, ny, nx)

            # Add ocean_time dimension back: (1, 16, ny, nx)
            interp_data = interp_data[np.newaxis, :, :, :]

            # Create output variable
            out_dims = ('ocean_time', 'depth') + var_cfg['dims'][2:]
            dst_var = dst.createVariable(
                var_name, 'f4', out_dims, fill_value=FILL_VALUE
            )
            dst_var.long_name = var_cfg['long_name']
            if var_cfg['units']:
                dst_var.units = var_cfg['units']
            dst_var.coordinates = sv.getncattr('coordinates') if hasattr(sv, 'coordinates') else ''
            dst_var.time = 'ocean_time'
            dst_var.grid = sv.getncattr('grid') if hasattr(sv, 'grid') else ''
            dst_var.location = sv.getncattr('location') if hasattr(sv, 'location') else ''
            dst_var.cell_methods = 'depth: linear_interpolation'
            dst_var.field = sv.getncattr('field') if hasattr(sv, 'field') else ''

            dst_var[:] = interp_data

            print(f'done (shape={interp_data.shape})')

        dst.close()

    # Atomically rename temp file to final output
    if os.path.exists(output_path):
        os.remove(output_path)
    os.rename(tmp_path, output_path)

    elapsed = time.time() - t_start
    fname = os.path.basename(input_path)
    print(f'  -> {fname} processed in {elapsed:.1f}s')


# ============================================================================
# Main
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description='ROMS sigma-to-z depth level extractor'
    )
    parser.add_argument(
        '--input-dir', '-i',
        default=r'E:\ROMS\daily\2023',
        help='Input directory containing ROMS avg files',
    )
    parser.add_argument(
        '--output-dir', '-o',
        default=r'D:\ROMS\daily\Depth_process',
        help='Output directory for processed files',
    )
    parser.add_argument(
        '--pattern', '-p',
        default='roms_avg_*Z12.nc',
        help='File glob pattern to match',
    )
    parser.add_argument(
        '--start-date',
        default=None,
        help='Start date YYYYMMDD (optional, for subset processing)',
    )
    parser.add_argument(
        '--end-date',
        default=None,
        help='End date YYYYMMDD (optional, for subset processing)',
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='List files to process without executing',
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite existing output files',
    )
    args = parser.parse_args()

    # Find input files
    pattern = os.path.join(args.input_dir, args.pattern)
    all_files = sorted(glob.glob(pattern))

    if not all_files:
        print(f'ERROR: No files matching {pattern}')
        sys.exit(1)

    # Filter by date range
    if args.start_date or args.end_date:
        filtered = []
        for f in all_files:
            basename = os.path.basename(f)
            # Extract YYYYMMDD from roms_avg_YYYYMMDDZ12.nc
            date_str = basename.replace('roms_avg_', '').replace('Z12.nc', '')
            if args.start_date and date_str < args.start_date:
                continue
            if args.end_date and date_str > args.end_date:
                continue
            filtered.append(f)
        all_files = filtered

    print(f'Found {len(all_files)} files to process')
    print(f'Input:  {args.input_dir}')
    print(f'Output: {args.output_dir}')

    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)

    if args.dry_run:
        print('\nDRY RUN — files that would be processed:')
        for f in all_files[:10]:
            print(f'  {os.path.basename(f)}')
        if len(all_files) > 10:
            print(f'  ... and {len(all_files) - 10} more')
        return

    # Process each file
    n_total = len(all_files)
    n_processed = 0
    n_skipped = 0
    n_failed = 0
    t_total_start = time.time()

    for i, fpath in enumerate(all_files):
        fname = os.path.basename(fpath)
        out_path = os.path.join(args.output_dir, fname)

        # Check if output already exists
        if os.path.exists(out_path) and not args.overwrite:
            print(f'[{i+1}/{n_total}] {fname} — SKIPPED (output exists)')
            n_skipped += 1
            continue

        print(f'[{i+1}/{n_total}] {fname}')
        try:
            process_file(fpath, out_path)
            n_processed += 1
        except Exception as e:
            print(f'  ERROR: {e}')
            import traceback
            traceback.print_exc()
            n_failed += 1
            # Remove partial output if any
            for p in [out_path, out_path + '.tmp']:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

        # Progress summary every 10 files
        if (i + 1) % 10 == 0:
            elapsed = time.time() - t_total_start
            rate = (i + 1) / elapsed * 3600 if elapsed > 0 else 0
            remaining = (n_total - i - 1) / rate if rate > 0 else 0
            print(f'\n--- Progress: {i+1}/{n_total} files '
                  f'(~{rate:.1f} files/hr, ETA {remaining:.1f} hrs) ---\n')

    # Final summary
    t_total = time.time() - t_total_start
    print(f'\n{"="*60}')
    print(f'Processing complete!')
    print(f'  Total:   {n_total}')
    print(f'  Done:    {n_processed}')
    print(f'  Skipped: {n_skipped}')
    print(f'  Failed:  {n_failed}')
    print(f'  Time:    {t_total/3600:.2f} hours ({t_total/60:.1f} min)')


if __name__ == '__main__':
    main()
