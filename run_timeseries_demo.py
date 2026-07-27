"""
ROMS Daily Time Series Demo.

Loads all ROMS daily files as a single lazy time series, generates
time-series plots, daily map grids, and ROMS-CMEMS comparisons.

Usage:
    cd d:\\ChatWithAI\\SCS_data
    set PYTHONIOENCODING=utf-8
    D:\\PYTHON\\envs\\scs_marine\\python.exe run_timeseries_demo.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.core.config import DATA_DIR_ROMS, DATA_DIR_CMEMS, OUTPUT_DIR
from src.core.pipeline import MarineDataPipeline
from src.core.time_assembler import TimeAssembler
from src.core.roms_utils import (
    extract_timeseries, extract_point, time_stats,
)
from src.core.aligner import SourceAligner
from src.viz.time_plotter import (
    plot_timeseries, plot_daily_maps,
    plot_multi_variable_timeseries,
    plot_comparison_timeseries,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OUTPUT = OUTPUT_DIR / "timeseries_demo"
OUTPUT.mkdir(parents=True, exist_ok=True)

LEVEL_IDX = -1          # surface (s_rho=-1 for ROMS, depth=0 for CMEMS)
N_TEST_FILES = 5        # use only first 5 ROMS files for quick demo
                        # set to None to use all 27 files

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 65)
    print("  SCS Marine Data — Time Series Demo")
    print("=" * 65)

    # ==================================================================
    # Step 1 — Scan ROMS daily files
    # ==================================================================
    print("\n" + "=" * 65)
    print("  STEP 1 — Discover ROMS daily files")
    print("=" * 65)

    assembler = TimeAssembler(DATA_DIR_ROMS)
    assembler.scan()

    print(f"  Files found:   {assembler.n_files}")
    dr = assembler.date_range()
    print(f"  Date range:    {dr[0].date()} to {dr[1].date()}")
    missing = assembler.missing_dates()
    if missing:
        print(f"  Missing dates: {', '.join(str(d.date()) for d in missing)}")
    else:
        print(f"  Missing dates: (none)")

    # ==================================================================
    # Step 2 — Assemble (lazy) with a subset for quick demo
    # ==================================================================
    print("\n" + "=" * 65)
    print("  STEP 2 — Assemble multi-file time series (lazy)")
    print("=" * 65)

    if N_TEST_FILES:
        print(f"  [DEMO MODE] Using first {N_TEST_FILES} files for quick testing")
        dates = assembler.dates[:N_TEST_FILES]
        assembler._file_map = {d: assembler._file_map[d] for d in dates}

    ds = assembler.assemble()
    meta = assembler.assembled_meta

    print(f"\n  Dataset size:  {dict(ds.sizes)}")
    print(f"  Variables:     {sorted(meta.base_meta.available_variables())}")
    print(f"  Dask chunks:   {ds.chunks if hasattr(ds, 'chunks') else 'N/A'}")

    # ==================================================================
    # Step 3 — Extract SST time series
    # ==================================================================
    print("\n" + "=" * 65)
    print("  STEP 3 — Extract SST time series")
    print("=" * 65)

    # 3a — Domain-mean SST
    ts_sst_mean = extract_timeseries(
        ds, meta.base_meta, "temperature", level_idx=LEVEL_IDX,
        lat_range=(0, 25), lon_range=(105, 122),
    )
    print(f"\n  Domain-mean SST (SCS): {ts_sst_mean}")
    print(f"  Times: {ts_sst_mean.time_labels}")

    # 3b — Central SCS point
    ts_sst_pt = extract_point(
        ds, meta.base_meta, "temperature",
        lon=115, lat=13, level_idx=LEVEL_IDX,
    )
    print(f"\n  Point SST (115E, 13N): {ts_sst_pt}")

    # 3c — Statistics
    stats_sst = time_stats(
        ds, meta.base_meta, "temperature", level_idx=LEVEL_IDX,
        lat_range=(0, 25), lon_range=(105, 122),
    )
    print(f"\n  SST Statistics (SCS domain):")
    for k, v in stats_sst.items():
        print(f"    {k}: {v:.4f}" if isinstance(v, float) else f"    {k}: {v}")

    # ==================================================================
    # Step 4 — Plots
    # ==================================================================
    print("\n" + "=" * 65)
    print("  STEP 4 — Generate time-series plots")
    print("=" * 65)

    # 4a — SST time series with gap shading
    ts_path = OUTPUT / "sst_timeseries.png"
    plot_timeseries(
        ts_sst_mean,
        title=f"ROMS SST — South China Sea Domain Mean ({meta.date_start.date()} to {meta.date_end.date()})",
        missing_indices=meta.missing_indices,
        output_path=ts_path,
    )
    print(f"  [OK] SST time series → {ts_path}")

    # 4b — Multi-variable panel
    mv_vars = ["temperature", "salinity", "sea_surface_height"]
    mv_path = OUTPUT / "multi_variable_timeseries.png"
    plot_multi_variable_timeseries(
        ds, meta.base_meta, mv_vars, level_idx=LEVEL_IDX,
        lat_range=(0, 25), lon_range=(105, 122),
        missing_indices=meta.missing_indices,
        output_path=mv_path,
    )
    print(f"  [OK] Multi-variable panel → {mv_path}")

    # 4c — Daily map grid (every 2nd day for the demo subset)
    step = max(1, meta.n_timesteps // 6)
    map_indices = list(range(0, meta.n_timesteps, step))
    map_labels = [meta.time_labels[i] for i in map_indices]
    map_path = OUTPUT / "daily_sst_maps.png"
    plot_daily_maps(
        ds, meta.base_meta, "temperature", map_indices,
        time_labels=map_labels, level_idx=LEVEL_IDX,
        output_path=map_path,
    )
    print(f"  [OK] Daily SST map grid → {map_path}")

    # ==================================================================
    # Step 5 — ROMS-CMEMS comparison
    # ==================================================================
    print("\n" + "=" * 65)
    print("  STEP 5 — ROMS vs CMEMS comparison")
    print("=" * 65)

    # Load CMEMS pH data (overlaps with ROMS Jan 2023)
    cmems_pipe = MarineDataPipeline(DATA_DIR_CMEMS)
    cmems_pipe.load_all()

    cmems_keys = cmems_pipe.keys_for("CMEMS")
    cmems_key = [k for k in cmems_keys if "PH" in k.upper()]
    if not cmems_key:
        cmems_key = cmems_keys[0] if cmems_keys else None

    if cmems_key is not None:
        cmems_key = cmems_key[0] if isinstance(cmems_key, list) else cmems_key
        cmems_ds = cmems_pipe.ds_for(cmems_key)
        cmems_meta = cmems_pipe.meta_for(cmems_key)

        aligner = SourceAligner(
            ds, meta.base_meta,
            cmems_ds, cmems_meta,
        )
        print(f"\n  {aligner.summary()}")

        # Compare common variables at a point
        for var in aligner.common_variables:
            try:
                roms_ts, cmems_ts = aligner.compare_point(
                    var, lon=115, lat=13,
                    level_idx_roms=LEVEL_IDX,
                    level_idx_cmems=0,  # surface
                )
                cmp_path = OUTPUT / f"comparison_{var}.png"
                plot_comparison_timeseries(
                    roms_ts, cmems_ts,
                    title=f"ROMS vs CMEMS — {var} at (115E, 13N)",
                    output_path=cmp_path,
                )
                print(f"  [OK] {var} comparison → {cmp_path}")
            except Exception as e:
                print(f"  [SKIP] {var}: {e}")

        # Show CMEMS-only variables too (for context)
        if aligner.cmems_only_variables:
            print(f"\n  CMEMS-only variables (available for time-aligned extraction):")
            for var in aligner.cmems_only_variables:
                try:
                    cmems_ts = extract_point(
                        cmems_ds, cmems_meta, var,
                        lon=115, lat=13, level_idx=0,
                    )
                    # Subset to ROMS date range
                    print(f"    {var}: {cmems_ts}")
                except Exception as e:
                    print(f"    {var}: SKIP ({e})")
    else:
        print("\n  [SKIP] No CMEMS file found.")

    # ==================================================================
    # Summary
    # ==================================================================
    print("\n" + "=" * 65)
    print("  SUMMARY")
    print("=" * 65)

    n_figs = len(list(OUTPUT.glob("*.png")))
    print(f"  Output directory:  {OUTPUT}/")
    print(f"  Figures generated: {n_figs}")
    print(f"  ROMS timesteps:    {meta.n_timesteps}")
    if cmems_key:
        print(f"  CMEMS matched:     {aligner.n_matched if 'aligner' in dir() else 'N/A'}")
    print("\nDone.")


if __name__ == "__main__":
    main()
