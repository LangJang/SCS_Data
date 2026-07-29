# SCS Marine Data Tool — Technical Documentation

## 1. Overview

The SCS Marine Data Tool ingests multi-source oceanographic data (ROMS model output, CMEMS satellite products) and point-based fishery records, normalizes them through an adapter layer into a unified canonical schema, and provides interactive visualization, spatial subsetting, downsampling, and hybrid export via a PyQt6 desktop GUI.

**Three data domains** are integrated:

| Domain | Type | Grid | Sources |
|--------|------|------|---------|
| Physical Oceanography | 3-D gridded | 872 × 586 rectilinear (0.05°) | ROMS, CMEMS |
| Biogeochemistry | 3-D gridded | 872 × 586 rectilinear (0.05°) | CMEMS |
| Fishery | Point records | Lat / Lon scatter | CSV pseudo-data (extensible) |

---

## 2. Adapter Architecture

### 2.1 Design Pattern

Each data source implements the `DataSourceAdapter` abstract base class with two methods:

```python
class DataSourceAdapter(ABC):
    @classmethod
    def detect(cls, ds: xr.Dataset, file_path: str | None) -> bool: ...
    def adapt(self, ds: xr.Dataset) -> SourceMeta: ...
```

- `detect()` — classmethod: inspects coordinate and variable names to determine if a NetCDF file belongs to this source
- `adapt()` — produces a `SourceMeta` dataclass that maps source-specific names to canonical names

All downstream code (visualization, export, alignment) operates exclusively on canonical names and is source-agnostic.

### 2.2 Adapter Registry

Defined in `src/core/adapters/__init__.py`.  Adapters are tried in priority order; the first `detect()` returning `True` wins.

```python
REGISTERED_ADAPTERS = [
    StandardROMSAdapter,       # ROMS with depth (no s_rho), curvilinear
    ROMSAdapter,                # ROMS with s_rho, curvilinear (legacy)
    RectilinearROMSAdapter,     # ROMS regridded to 1-D rectilinear
    CMEMSAdapter,               # CMEMS / CF-compliant 1-D rectilinear
]
```

### 2.3 SourceMeta — Canonical Metadata

```python
@dataclass
class SourceMeta:
    source_name: str          # "ROMS", "CMEMS", "ROMS-Rectilinear", etc.
    grid_type: GridType       # RECTILINEAR (1-D lon/lat) or CURVILINEAR (2-D)
    vertical_type: VerticalType  # DEPTH (meters), SIGMA (fractional), NONE (2-D)
    var_map: Dict[str, str]   # canonical_name → source_variable_name
    coord_map: Dict[str, str] # canonical_coord → source_coord_name
    time_dim: str | None      # e.g. "ocean_time" or "time"
    extra_attrs: dict         # staggered coords, variable attrs, grid dims
```

### 2.4 Adding a New Data Source

1. **Subclass `DataSourceAdapter`**: implement `detect()` and `adapt()`
2. **Register** in `adapters/__init__.py` via `REGISTERED_ADAPTERS`
3. **Add canonical variables** (if new variable types) to `CANONICAL_VARIABLES` in `canonical.py`
4. **Add config entry** in `config.yaml` with metadata (spatial extent, temporal range, resolution, depth layers, etc.)

---

## 3. Canonical Variable Schema

Defined in `src/core/canonical.py`.  All 16 variables use CF Standard Names where applicable.

| Canonical Name | Display Label | Units | Category |
|---------------|---------------|-------|----------|
| `temperature` | Potential Temperature | °C | Physical |
| `salinity` | Salinity | PSU | Physical |
| `u_current` | Eastward Current | m s⁻¹ | Physical |
| `v_current` | Northward Current | m s⁻¹ | Physical |
| `w_velocity` | Vertical Velocity | m s⁻¹ | Physical |
| `u_barotropic` | Depth-Averaged U-Current | m s⁻¹ | Physical |
| `v_barotropic` | Depth-Averaged V-Current | m s⁻¹ | Physical |
| `sea_surface_height` | Sea Surface Height | m | Physical |
| `mixed_layer_thickness` | Mixed Layer Thickness | m | Physical |
| `chlorophyll` | Chlorophyll-a | mg m⁻³ | BGC |
| `dissolved_oxygen` | Dissolved Oxygen | mmol m⁻³ | BGC |
| `nitrate` | Nitrate | mmol m⁻³ | BGC |
| `phosphate` | Phosphate | mmol m⁻³ | BGC |
| `silicate` | Dissolved Silicate | mmol m⁻³ | BGC |
| `ph` | pH | | BGC |
| `primary_production` | Primary Production | mg C m⁻² day⁻¹ | BGC |

### 3.1 Grid Type

```
RECTILINEAR  — lon/lat are 1-D arrays (CMEMS, regridded ROMS)
CURVILINEAR  — lon/lat are 2-D arrays (original ROMS on Arakawa-C grid)
```

### 3.2 Vertical Type

```
DEPTH  — absolute depth in meters, surface = index 0
SIGMA  — terrain-following fractional coordinate, surface = last index
NONE   — 2-D variable without vertical dimension
```

---

## 4. ROMS Staggered Grid Handling

ROMS uses an Arakawa-C staggered grid:

| Grid Point | Variables | Longitude | Latitude |
|-----------|-----------|-----------|----------|
| ρ (rho) | temp, salt, w, zeta | `lon_rho` (2-D) | `lat_rho` (2-D) |
| u | u, ubar | `lon_u` (2-D) | `lat_u` (2-D) |
| v | v, vbar | `lon_v` (2-D) | `lat_v` (2-D) |

When extracting u/v fields, `_resolve_roms_coords()` in `roms_utils.py` selects the correct coordinate array based on the source variable name.  When computing `current_speed`, u/v are interpolated to the ρ-grid via linear averaging along the staggered dimension:

```
u_rho[:, 1:-1] = 0.5 * (u_raw[:, :-1] + u_raw[:, 1:])   # xi_u → xi_rho
v_rho[1:-1, :] = 0.5 * (v_raw[:-1, :] + v_raw[1:, :])   # eta_v → eta_rho
```

Boundary points copy the nearest edge value.

---

## 5. Key Algorithms

### 5.1 Curvilinear → Rectilinear Regridding (KDTree)

**File**: `tools/regrid_roms_to_rectilinear.py`  
**Algorithm**: `scipy.spatial.cKDTree` nearest-neighbor

```
Input:  ROMS 2-D lon_rho (1668 × 2340), lat_rho (1668 × 2340)
Target: CMEMS 1-D longitude (872), latitude (586)

For each variable × depth × timestep:
    1. Build KDTree on source 2-D points: (lon_rho.ravel(), lat_rho.ravel())
    2. Query nearest neighbor for each target point: (tgt_lon2d[i], tgt_lat2d[i])
    3. Map source values through index array
    4. Write to output NetCDF (one timestep at a time, memory-safe)

Complexity: O(N_target × log(N_source)) ≈ 511K × log(3.9M) per layer
```

**Memory**: processes one file at a time (~15 MB per 2-D layer).  Total output: 27 days × 14 depths × 5 variables on 872 × 586 grid.

### 5.2 Bilinear Spatial Interpolation (0.25° → 0.05°)

**File**: `tools/interp_to_005deg.py`  
**Algorithm**: `scipy.interpolate.RegularGridInterpolator`

```
Input:  Extracted 2-layer original CMEMS (175 × 118, 0.25°)
Target: Standardized CMEMS grid (872 × 586, 0.05°)

f(lat, lon) = RegularGridInterpolator(src_lat, src_lon, values, method="linear")
result[i, j] = f(tgt_lat[i], tgt_lon[j])

Bounds: fill_value=NaN for points outside the source domain
Method: bilinear — weighted average of 4 surrounding source cells
```

### 5.3 Coarsen Downsampling (Resolution Reduction)

**File**: `src/ui/widgets/export_dialog.py`, method `_save_data()`  
**Algorithm**: `xarray.DataArray.coarsen().mean()`

```
Given:  da on a 872 × 586 grid at 0.05° resolution
Target: 0.25° resolution  →  stride = 5

da.coarsen(longitude=5, latitude=5, boundary="trim").mean()

Each 5 × 5 block of source cells → 1 output cell (arithmetic mean).
boundary="trim": discard edge cells that don't fill a complete block.
```

The `stride` is computed automatically:
```python
native_res = abs(lon_values[1] - lon_values[0])   # e.g. 0.05
stride = max(1, int(round(target_res / native_res)))  # e.g. 0.25 / 0.05 = 5
```

### 5.4 Real Spatial Crop (1-D Rectilinear Only)

**File**: `src/ui/widgets/export_dialog.py`, method `_save_data()`  
**Algorithm**: `xarray.DataArray.sel(slice)`

```python
da = da.sel({
    longitude: slice(west, east),
    latitude: slice(south, north),
})
```

Only available for 1-D rectilinear grids (4 out of 4 visible datasets).  For 2-D curvilinear grids, spatial cropping is blocked with a clear error message.

### 5.5 Fishery Point Rasterization

**File**: `src/core/fishery_raster.py`  
**Algorithm**: nearest-grid-cell binning with per-cell aggregation

```
Input:  DataFrame with columns [lat, lon, species, catch_kg]
Target: 1-D longitude and latitude arrays from the ocean grid

For each fishery record (lat_i, lon_i, species_i, kg_i):
    j = argmin(|lat_grid - lat_i|)    # nearest latitude  index
    i = argmin(|lon_grid - lon_i|)    # nearest longitude index
    cell[j, i] accumulates: total_catch, record_count, per-species catch

Output layers (all 2-D float32, NaN where no data):
    catch_total     — total catch per cell (kg)
    n_records       — number of fishing records per cell
    n_species       — species richness per cell
    catch_{species} — per-species catch per cell (one layer per species)
```

Species names are sanitized for NetCDF compatibility: spaces → `_`, special characters removed.

### 5.6 Overlay Scatter / Pie Chart Rendering

**File**: `src/ui/widgets/map_canvas.py`, method `add_overlay_scatter()`  
**Algorithm**: per-location grouping with conditional rendering

```
Group DataFrame by (lat, lon):

    For each location:
        if n_species == 1:
            Draw a scatter point (radius ∝ catch_kg, color = species)
        else:
            Draw a Wedge pie chart (radius ∝ log(total_catch))
            - Slice angle ∝ species catch fraction
            - Slice color = species color from tab10 colormap

Species colors: tab10 qualitative colormap, consistent across all locations
Legend: Patch handles placed to the left of the map axes
```

### 5.7 Overlay Filter Logic (AND / OR)

**File**: `src/ui/widgets/filter_panel.py`, method `_apply()`  
**Algorithm**: boolean mask composition

```
For each filter group (Source, Species, Method, Date, Location):
    Build boolean mask: mask_g[i] = True if record i passes this group

Combine:
    AND mode: result = mask_0 & mask_1 & ... & mask_n  (intersection)
    OR  mode: result = mask_0 | mask_1 | ... | mask_n  (union)

Within each group: OR between checkboxes (e.g. Trawl OR Gillnet)
```

---

## 6. Data Pipeline

### 6.1 Configuration-Driven Data Discovery

`config.yaml` defines all available datasets.  Each entry includes:

```yaml
- name: "CMEMS Standardized — DO & Chlorophyll (0–400 m, 0.05°)"
  source: "CMEMS"
  keywords: [chlorophyll, oxygen, cmems, standardized]
  variables: [chlorophyll, dissolved_oxygen]
  resolution: { default: 0.05, available: [0.05, 0.1, 0.25] }
  spatial: { lon: {min: 90.0, max: 134.5}, lat: {min: -0.5, max: 30.0} }
  temporal: { start: 2023-01-01, end: 2023-12-31, frequency: daily }
  vertical: { type: depth, layers: 14, range: [0, 400] }
  path: "D:/ChatWithAI/Downloading_CEMES/output/"
  file_pattern: "SCS_cmems_do_chl.nc"
```

`AppConfig.search(query)` matches against `name`, `source`, `keywords`, and `variables`.  Results are displayed as cards in the GUI.  The actual NetCDF file is opened only when the user clicks **Plot**.

### 6.2 GUI Data Flow

```
config.yaml  ──→  SearchSection (cards)  ──→  ParamPanel (settings)
                                                    │
OverlayPanel (cards)  ──→  FilterPanel (filters)    │
        │                        │                   │
        └────────────────────────┴───────────────────┘
                                 │
                            [Plot] button
                                 │
                    MarineDataPipeline.load_all()
                         │              │
                    extract_field()   overlay DF
                         │              │
                    MapCanvas.update_map()
                         │
                    MapCanvas.add_overlay_scatter()
                         │
                    [Export] button
                         │
              ExportDialog._save_data()
                ├── sel(slice) spatial crop
                ├── coarsen().mean() downsampling
                └── rasterize_fishery() (if overlay active)
                         │
                    NetCDF / CSV / PNG / JPG / TIFF / PDF
```

### 6.3 Multi-Source Overlay Merging

When multiple overlay datasets are selected:

1. `OverlayPanel` loads each CSV, adds a `source` column, and concatenates all DataFrames
2. `FilterPanel` adds a "Dataset" filter group so individual sources can be toggled
3. `add_overlay_scatter()` renders all points with unified species coloring
4. `rasterize_fishery()` aggregates all sources into the same grid cells

---

## 7. GUI Architecture

### 7.1 Layout

```
┌──────────────────────────────────────────────────────────┐
│  Find the Data                    │  Overlay Data         │
│  [Search] [Env Cards]             │  [Search] [Cards]     │
├──────────────────────────────────────────────────────────┤
│  Make a Graph                                            │
│  ┌──────────┬──────────────────┬────────────────────────┐│
│  │ParamPanel│  Preview Map     │  FilterPanel           ││
│  │ (settings│  (Cartopy canvas │  (dynamic, per overlay)││
│  │  panel)  │   + scatter/pie) │                        ││
│  └──────────┴──────────────────┴────────────────────────┘│
├──────────────────────────────────────────────────────────┤
│  Plot & Export              [Plot]  [Export]              │
└──────────────────────────────────────────────────────────┘
```

### 7.2 Widget Map

| Widget | File | Role |
|--------|------|------|
| `SearchSection` | `search_section.py` | Env data keyword search + dataset cards |
| `OverlayPanel` | `overlay_panel.py` | Overlay data search + multi-select cards |
| `ParamPanel` | `param_section.py` | Variable, depth, time, spatial, resolution, colormap |
| `MapCanvas` | `map_canvas.py` | Cartopy map embedded in PyQt; scatter + Wedge pie overlay |
| `FilterPanel` | `filter_panel.py` | Per-overlay dynamic filters with AND/OR logic |
| `PreviewSection` | `param_section.py` | Wraps MapCanvas + NavigationToolbar |
| `ExportDialog` | `export_dialog.py` | Spatial crop + coarsen + fishery raster + multi-format save |

### 7.3 Signal Flow

```
SearchSection.dataset_selected  →  MainWindow._on_dataset_selected  →  ParamPanel.set_dataset
OverlayPanel.overlay_toggled    →  MainWindow._on_overlay_toggled   →  FilterPanel.set_overlay
                                                                     →  MapCanvas.add_overlay_scatter
FilterPanel.filter_changed      →  MainWindow._on_filter_changed    →  MapCanvas.add_overlay_scatter (replace)
ParamPanel.params_changed       →  MainWindow._on_params_changed    →  _refresh_preview (spatial crop + zoom)
MapCanvas.map_clicked           →  MainWindow._on_map_clicked       →  status message
MapCanvas.region_selected       →  MainWindow._on_region_selected   →  status message
Plot button                     →  MainWindow._on_plot              →  _do_plot → _refresh_preview → _reapply_overlay
Export button                   →  MainWindow._on_export            →  ExportDialog → _save_data / _save_image
```

---

## 8. Key Design Decisions

1. **Canonical-first**: all downstream modules reference variables by canonical name.  Source-specific names exist only inside adapters.
2. **Config as registry**: `config.yaml` is the single source of truth for dataset metadata.  Search never touches NetCDF files.
3. **Memory-safe regridding**: KDTree regridding writes one timestep at a time via native netCDF4 I/O — no full-dataset allocation.
4. **Figure reuse**: MapCanvas replaces axes entirely on each `update_map()` call (`fig.delaxes` + new `add_subplot`) to prevent colorbar accumulation.
5. **Rasterized base layer**: `pcolormesh(rasterized=True)` renders the ocean field as a bitmap for smooth window resize, while scatter/pie overlays remain as vector graphics.
6. **Multi-select overlays**: Overlay cards support concurrent selection; DataFrames are concatenated with a `source` tag.  Filters operate on the merged dataset.
7. **Hybrid NC export**: Fishery point data is rasterized to the same grid and appended as additional 2-D layers in the exported NetCDF file.
