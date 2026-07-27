# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

South China Sea (SCS) oceanographic data tool — ingests NetCDF files from multiple sources (ROMS model output and CMEMS/Copernicus products), normalizes them to a canonical variable/coordinate schema, and produces maps, time series, and cross-source comparisons. GUI (PyQt6) is planned but not yet functional.

## Environment

```bash
conda activate scs_marine       # Python 3.11
python tools/check_env.py       # verify all packages import correctly
```

## Running Demos

```bash
# Individual source demos (these are the primary entry points):
D:\PYTHON\envs\scs_marine\python.exe run_roms_demo.py
D:\PYTHON\envs\scs_marine\python.exe run_cmes_demo.py
```

## Architecture

### Adapter + Canonical Schema (the core design pattern)

Multi-source data is normalized through an adapter layer. Each adapter (`src/core/adapters/`) translates source-specific variable and coordinate names to canonical names defined in `src/core/canonical.py`. Downstream code (viz, export, alignment) operates only on canonical names and is source-agnostic.

- **`DataSourceAdapter`** (abstract base) — subclasses implement `detect()` (classmethod: does this dataset belong to this source?) and `adapt()` (produces a `SourceMeta` from the dataset).
- **`ROMSAdapter`** — detects via `ocean_time` + `s_rho` + `lon_rho`; curvilinear grid, sigma vertical coordinates.
- **`CMEMSAdapter`** — detects via CF-standard `time`/`longitude`/`latitude` coords (with alias support) OR filename prefix `cmems_`; rectilinear grid, depth vertical coordinates.
- **`SourceMeta`** — canonical metadata dataclass: `source_name`, `grid_type` (RECTILINEAR/CURVILINEAR), `vertical_type` (DEPTH/SIGMA/NONE), `var_map` (canonical→source var names), `coord_map` (canonical→source coord names).
- **`detect_source()`** — tries each registered adapter in order; returns the first match or `None`.
- **Adding a new data source** — subclass `DataSourceAdapter`, add it to `REGISTERED_ADAPTERS` in `adapters/__init__.py`, add any new variable mappings to `CANONICAL_VARIABLES` in `canonical.py`.

### Key Modules

| Module | Purpose |
|--------|---------|
| `src/core/nc_reader.py` | File discovery, loading, source detection, product grouping (CMEMS naming convention) |
| `src/core/canonical.py` | Canonical variable/coordinate definitions, `SourceMeta`, grid/vertical enums |
| `src/core/pipeline.py` | `MarineDataPipeline` — high-level orchestrator: scan→detect→inspect→snapshot maps→time series→cross-source comparison |
| `src/core/time_assembler.py` | `TimeAssembler` — lazy multi-file concatenation via `xr.open_mfdataset` with dask; date extraction from ROMS filenames; `AssembledMeta` for multi-file temporal context |
| `src/core/roms_utils.py` | Field extraction (`extract_field`, `extract_point`, `extract_timeseries`), interpolation, `TimeseriesResult` dataclass, `current_speed` derived variable |
| `src/core/aligner.py` | `SourceAligner` — temporal matching (date alignment between ROMS/CMEMS), spatial regridding (curvilinear→rectilinear via KDTree or linear), point/spatial-mean comparison |
| `src/core/preprocess.py` | Missing value detection, temporal resampling, spatial bbox subsetting, variable selection |
| `src/core/export.py` | CSV, multi-sheet Excel, NetCDF round-trip |
| `src/core/config.py` | Project-wide path constants (`DATA_DIR_ROMS`, `DATA_DIR_CMEMS`, `OUTPUT_DIR`) |
| `src/viz/map_plotter.py` | Single-call Cartopy map rendering (coastlines, gridlines, colorbar) |
| `src/viz/time_plotter.py` | Time-series line plots, daily map grids, source-comparison overlays |
| `src/ui/main_window.py` | PyQt6 main window skeleton (WIP) |
| `src/main.py` | GUI entry point (WIP) |

### Data Flow

```
NetCDF files → NCReader.load_all() → detect_source() → Adapter.adapt() → SourceMeta
                                                                              ↓
                              MarineDataPipeline ←── canonical var/coord names
                                     ↓
                    ┌────────────────┼────────────────┐
                    ↓                ↓                 ↓
              snapshot maps    TimeAssembler     SourceAligner
              (map_plotter)    (multi-file)      (ROMS↔CMEMS)
                                    ↓
                              time_plotter
```

### CMEMS Product Grouping

CMEMS files follow a naming convention `prefix_{product}_{resolution}_{start}_{end}.nc`. `NCReader.group_by_product()` parses the product key from the second underscore-delimited segment and maps it to human-readable labels via `_KNOWN_PRODUCT_LABELS`.

### Time Assembler for ROMS Daily Data

ROMS daily averages are individual files named `roms_avg_YYYYMMDDZhh.nc`. `TimeAssembler`:
1. `scan()` — glob-match files, extract dates from filenames, detect gaps
2. `assemble()` — `xr.open_mfdataset` with `chunks={"ocean_time": 1}` and `compat="override"` for lazy concatenation (105 GB across 27 files never loaded into RAM at once)
3. Provides `AssembledMeta` wrapping single-file `SourceMeta` with multi-file temporal context (time labels, missing indices for gap shading in plots)

### Source Aligner (ROMS↔CMEMS comparison)

Three alignment dimensions, two of which are implemented:
- **Temporal** — nearest-timestep matching (ROMS 12:00Z → CMEMS 00:00Z, same calendar day within 24h max)
- **Spatial** — ROMS curvilinear grid regridded to CMEMS rectilinear grid via `scipy.spatial.cKDTree` (nearest-neighbor) or `scipy.interpolate.griddata` (linear)
- **Vertical** — deferred (surface-level only for now; ROMS sigma→depth conversion not yet implemented)

### ROMS Grid Specifics

ROMS uses a staggered Arakawa-C grid. The adapter maps ρ-point coordinates (`lon_rho`, `lat_rho`, `s_rho`) to canonical names. Other grid points (`lon_u`, `lat_u`, `lon_v`, `lat_v`, `s_w`) are exposed through `extra_attrs["staggered_coords"]` but not used by the canonical pipeline. 2-D ROMS fields require no vertical level index; 3-D fields require a sigma layer index (0=bottom, -1=surface).

## Important Conventions

- **Canonical-first**: all downstream code references variables by canonical name, never by source-native name. Use `SourceMeta.source_var()` / `canonical_var()` to translate.
- **Lazy loading for time series**: `TimeAssembler.assemble()` returns a dask-backed Dataset. Slice with `.isel()` to trigger reading only the relevant file(s). Never call `.values` or `.load()` on the full assembled dataset.
- **Data directories** are configured in `src/core/config.py`, not hardcoded. Import `DATA_DIR_ROMS`, `DATA_DIR_CMEMS`, `OUTPUT_DIR` from there.
- **`data/` and `output/` are git-ignored** — input NetCDF files and generated figures live outside version control.
- **`_incoming/`** is a staging area for user scripts that aren't part of the core tool.

## Key Missing Pieces

- No test suite (no pytest, unittest, or test files exist yet)
- No linter/formatter configuration
- GUI is a skeleton — `src/main.py` and `src/ui/main_window.py` exist but are not functional
- PyInstaller packaging is configured in `environment.yml` but no `.spec` file is present in `build/`
- Vertical alignment (ROMS sigma→depth) in `SourceAligner` is deferred
