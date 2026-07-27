"""
Unified demo — multi-source marine data pipeline.

Scans from configured data directories, auto-detects ROMS / CMEMS
sources, and produces snapshot maps for each.

Usage:
    cd d:\ChatWithAI\SCS_data
    D:\PYTHON\envs\scs_marine\python.exe demo_unified.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.core.pipeline import MarineDataPipeline

# ---------------------------------------------------------------------------
# Configuration — add your data directories here
# ---------------------------------------------------------------------------
DATA_ROMS   = Path("D:/ChatWithAI")               # ROMS output directory
DATA_CMEMS  = Path("D:/ChatWithAI/Downloading_CEMES")  # CMEMS downloads
OUTPUT      = Path("output/unified_demo")

# Pipeline settings
TIME_IDX    = 0     # first time step
LEVEL_IDX   = 0     # surface layer (depth=0 for CMEMS, s_rho=0 for ROMS)


def main() -> None:
    print("=" * 65)
    print("  SCS Marine Data — Unified Pipeline Demo")
    print("=" * 65)

    # ==================================================================
    # Step 1 — Scan & auto-detect all files
    # ==================================================================
    print("\n" + "=" * 65)
    print("  STEP 1 — Scan & auto-detect sources")
    print("=" * 65)

    # ROMS
    pipe_roms = MarineDataPipeline(DATA_ROMS)
    print(f"\n[ROMS]  {DATA_ROMS}")
    for _, row in pipe_roms.scan().iterrows():
        print(f"  {row['name']:<45s} {row['size_mb']:>8.0f} MB")

    # CMEMS
    pipe_cemes = MarineDataPipeline(DATA_CMEMS)
    print(f"\n[CMEMS] {DATA_CMEMS}")
    for _, row in pipe_cemes.scan().iterrows():
        print(f"  {row['name']:<45s} {row['size_mb']:>8.0f} MB")

    # ==================================================================
    # Step 2 — Inspect (source-level metadata)
    # ==================================================================
    print("\n" + "=" * 65)
    print("  STEP 2 — Source metadata")
    print("=" * 65)

    # ROMS inspection (single-file)
    pipe_roms.load_all()
    print(f"\n[ROMS] Sources found: {pipe_roms.sources()}")
    roms_vars = pipe_roms.list_variables(source="ROMS")
    for k, v in roms_vars.items():
        print(f"  {k}: {sorted(v)}")

    # CMEMS inspection (multi-file)
    pipe_cemes.load_all()
    print(f"\n[CMEMS] Sources found: {pipe_cemes.sources()}")
    cemes_vars = pipe_cemes.list_variables(source="CMEMS")
    for k, v in cemes_vars.items():
        print(f"  {k}: {sorted(v)}")

    # ==================================================================
    # Step 3 — Process each source (snapshot all fields)
    # ==================================================================
    print("\n" + "=" * 65)
    print("  STEP 3 — Generate snapshot maps")
    print("=" * 65)

    # ROMS — all fields for the single ROMS file
    print("\n--- Processing ROMS ---")
    roms_saved = pipe_roms.process(
        "ROMS",
        output_dir=OUTPUT,
        time_idx=TIME_IDX,
        level_idx=36,   # ROMS: s_rho near-surface
    )

    # CMEMS — all files, all variables
    print("\n--- Processing CMEMS ---")
    cemes_saved = pipe_cemes.process(
        "CMEMS",
        output_dir=OUTPUT,
        time_idx=TIME_IDX,
        level_idx=LEVEL_IDX,   # depth=0 = surface
    )

    # ==================================================================
    # Summary
    # ==================================================================
    print("\n" + "=" * 65)
    print("  SUMMARY")
    print("=" * 65)

    total_roms  = sum(len(v) for v in roms_saved.values())
    total_cemes = sum(len(v) for v in cemes_saved.values())

    print(f"  ROMS:  {total_roms} figure(s)")
    for k, paths in roms_saved.items():
        print(f"    {k}: {len(paths)} plots → {Path(paths[0]).parent if paths else 'N/A'}")

    print(f"  CMEMS: {total_cemes} figure(s)")
    for k, paths in cemes_saved.items():
        print(f"    {k}: {len(paths)} plots → {Path(paths[0]).parent if paths else 'N/A'}")

    print(f"\n  Total: {total_roms + total_cemes} figures in {OUTPUT}/")
    print("\nDone.")


if __name__ == "__main__":
    main()
