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

## Getting Started

### 1. Create conda environment

```bash
conda env create -f environment.yml
conda activate scs_marine
```

### 2. Run the application

```bash
python src/main.py
```

### 3. Build standalone EXE

```bash
pyinstaller build/scs_marine.spec
```

## Project Structure

```
SCS_data/
├── environment.yml          # conda env spec (reproducible)
├── requirements.txt         # pip fallback
├── README.md
├── src/
│   ├── main.py              # entry point
│   ├── ui/                  # PyQt6 GUI modules
│   │   └── main_window.py
│   ├── core/                # data logic
│   │   ├── nc_reader.py     # NetCDF ingestion
│   │   ├── preprocess.py    # preprocessing
│   │   └── export.py        # data export
│   └── assets/              # bundled resources
├── data/                    # input data (git-ignored)
├── output/                  # generated exports (git-ignored)
└── build/                   # PyInstaller config
```
