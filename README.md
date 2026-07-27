# SCS Marine Environmental Data Tool

South China Sea (SCS) oceanographic data aggregation, preprocessing, visualization, and export utility.

## Features (planned)

- **Multi-format data ingestion** — NetCDF (.nc/.nc4) first; additional formats TBD
- **Preprocessing** — missing value handling, temporal aggregation, spatial subsetting, variable selection
- **Visualization** — time series, spatial maps (with Cartopy coastlines), statistical plots
- **Export** — CSV, Excel, NetCDF round-trip, publication-quality figures
- **Packaged EXE** — standalone Windows executable via PyInstaller

## Tech Stack

| Layer | Technology |
|-------|-----------|
| GUI | PyQt6 |
| Data | xarray, netCDF4, numpy, pandas |
| Visualization | matplotlib, seaborn, cartopy |
| Export | openpyxl, netCDF4 |
| Packaging | PyInstaller |
| Environment | conda (Python 3.11) |

## Quick Start

```bash
conda activate scs_marine

# Unified demo — auto-detects ROMS & CMEMS, generates all maps
python run_demo.py

# Source-specific demos
python run_roms_demo.py       # ROMS model output only
python run_cmes_demo.py       # CMEMS products only
```

## Pipeline Usage

```python
from src.core.pipeline import MarineDataPipeline, quick_pipeline

# One-liner
quick_pipeline("D:/data/roms", "ROMS")
quick_pipeline("D:/data/cemes", "CMEMS")

# Step-by-step
pipe = MarineDataPipeline("D:/data")
pipe.scan()                    # list files
pipe.sources()                 # {"ROMS": [...], "CMEMS": [...]}
pipe.inspect(source="CMEMS")   # metadata
pipe.process("CMEMS")          # snapshot all fields
```

## Project Structure

```
SCS_data/
├── run_demo.py              # unified pipeline demo
├── run_roms_demo.py         # ROMS-only demo
├── run_cmes_demo.py         # CMEMS-only demo
├── tools/
│   └── check_env.py         # env verification
├── environment.yml
├── requirements.txt
├── src/
│   ├── main.py              # GUI entry point (WIP)
│   ├── ui/
│   │   └── main_window.py
│   ├── viz/
│   │   └── map_plotter.py   # Cartopy map rendering
│   └── core/
│       ├── pipeline.py      # unified pipeline
│       ├── canonical.py     # variable/coordinate standards
│       ├── nc_reader.py     # NetCDF ingestion + source detection
│       ├── roms_utils.py    # field extraction + interpolation
│       ├── preprocess.py    # missing values, resampling, subset
│       ├── export.py        # CSV, Excel, NetCDF export
│       └── adapters/        # data-source adapters
│           ├── base.py
│           ├── roms_adapter.py
│           └── cmems_adapter.py
├── _incoming/               # user script staging area
├── data/                    # input data (git-ignored)
├── output/                  # generated figures (git-ignored)
└── build/                   # PyInstaller config
```
