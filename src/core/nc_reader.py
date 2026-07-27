"""
NetCDF file reader for SCS marine environmental data.

Handles .nc / .nc4 files via xarray with netCDF4 backend.
Auto-detects data source (ROMS, CMEMS, …) and builds a canonical
:class:`SourceMeta` for each loaded dataset.
Supports product grouping from CMEMS-style filenames
(``cmems_{product}_{resolution}_{start}_{end}.nc``).
"""

from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from collections import defaultdict

import xarray as xr
import numpy as np
import pandas as pd

from src.core.canonical import SourceMeta, GridType, VerticalType
from src.core.adapters import detect_source


# ---------------------------------------------------------------------------
# Product grouping (CMEMS naming convention)
# ---------------------------------------------------------------------------

_PRODUCT_POSITION = 1  # stem.split('_')[1] is the product key

_KNOWN_PRODUCT_LABELS: Dict[str, str] = {
    "phy-thetao": "Potential Temperature (thetao)",
    "phy-so":     "Salinity (so)",
    "phy-cur":    "Ocean Currents (uo, vo)",
    "bgc-pft":    "Chlorophyll — PFT",
    "phy-chl":    "Chlorophyll (chl)",
    "phy-ssh":    "Sea Surface Height (ssh)",
    "phy-mlt":    "Mixed Layer Thickness (mlt)",
    "bgc-no3":    "Nitrate (no3)",
    "bgc-po4":    "Phosphate (po4)",
    "bgc-o2":     "Dissolved Oxygen (o2)",
    "bgc-ph":     "pH (ph)",
    "bgc-pp":     "Primary Production (pp)",
    "wave":       "Wave Parameters",
}


def group_by_product(
    files: List[Path],
    stem_split_char: str = "_",
    product_position: int = _PRODUCT_POSITION,
) -> Dict[str, List[Path]]:
    """Group NetCDF files by product key parsed from filenames.

    Expects filenames like ``prefix_product_suffix.nc``.
    Files whose stem does not contain enough segments are collected
    under the key ``"__ungrouped__"``.

    Parameters
    ----------
    files : list[Path]
        File paths to group.
    stem_split_char : str
        Delimiter for splitting the file stem.
    product_position : int
        Zero-based segment index for the product key.

    Returns
    -------
    dict[str, list[Path]]
        Product key → list of matching file paths.
    """
    groups: Dict[str, List[Path]] = defaultdict(list)
    for fp in files:
        segments = fp.stem.split(stem_split_char)
        if len(segments) > product_position:
            key = segments[product_position]
        else:
            key = "__ungrouped__"
        groups[key].append(fp)
    return dict(groups)


def product_label(product_key: str) -> str:
    """Return a human-readable label for a known CMEMS product key."""
    return _KNOWN_PRODUCT_LABELS.get(product_key, product_key)


# ---------------------------------------------------------------------------
# NCReader
# ---------------------------------------------------------------------------

class NCReader:
    """Reader for NetCDF oceanographic data files.

    Parameters
    ----------
    data_dir : str or Path
        Root directory containing .nc files.
    """

    # Coordinate names to inspect for range reporting
    _RANGE_COORDS = {
        "longitude", "long", "lon",
        "latitude", "lat",
        "depth", "deptht", "z",
    }

    def __init__(self, data_dir: str | Path) -> None:
        self._data_dir = Path(data_dir)
        self._datasets: Dict[str, xr.Dataset] = {}
        self._metas: Dict[str, SourceMeta] = {}
        self._unmatched: List[str] = []  # datasets without a recognized source

    # ------------------------------------------------------------------
    # File Discovery
    # ------------------------------------------------------------------

    def scan_files(self, pattern: str = "*.nc") -> List[Path]:
        """Return sorted list of NetCDF files in the data directory.

        Parameters
        ----------
        pattern : str
            Glob pattern to match (also matches .nc4 when ``*.nc`` is used).

        Returns
        -------
        list[Path]
            Absolute paths to matching files, sorted alphabetically.
        """
        files = sorted(self._data_dir.glob(pattern))
        if pattern == "*.nc":
            files += sorted(self._data_dir.glob("*.nc4"))
            files = sorted(set(files))
        return files

    def scan_files_with_sizes(self) -> pd.DataFrame:
        """Scan data directory and return file name + size table.

        Returns
        -------
        pd.DataFrame
            Columns: ``name``, ``size_mb``.
        """
        rows = []
        for fp in self.scan_files():
            rows.append({
                "name": fp.name,
                "size_mb": fp.stat().st_size / 1e6,
            })
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Product grouping
    # ------------------------------------------------------------------

    def product_groups(self) -> Dict[str, List[Path]]:
        """Group scanned files by CMEMS product key.

        Returns
        -------
        dict[str, list[Path]]
        """
        return group_by_product(self.scan_files())

    def product_summary(self) -> pd.DataFrame:
        """Return a summary of product groups found in the data directory.

        Returns
        -------
        pd.DataFrame
            Columns: ``product``, ``label``, ``file_count``, ``files``.
        """
        groups = self.product_groups()
        rows = []
        for key, flist in sorted(groups.items()):
            rows.append({
                "product": key,
                "label": product_label(key),
                "file_count": len(flist),
                "files": ", ".join(f.name for f in flist),
            })
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self, file_path: str | Path) -> xr.Dataset:
        """Load a single NetCDF file into an xarray Dataset.

        Auto-detects the data source (ROMS, CMEMS, …) and builds a
        :class:`SourceMeta` accessible via :meth:`meta`.

        Parameters
        ----------
        file_path : str or Path
            Path to the NetCDF file.

        Returns
        -------
        xr.Dataset
        """
        path = Path(file_path)
        key = path.name
        ds = xr.open_dataset(path, engine="netcdf4")
        self._datasets[key] = ds
        self._build_meta(key, ds, str(path))
        return ds

    def load_all(self) -> Dict[str, xr.Dataset]:
        """Scan data_dir and load every NetCDF file found.

        Returns
        -------
        dict[str, xr.Dataset]
            Mapping of filename → Dataset.
        """
        for fp in self.scan_files():
            self.load(fp)
        return self._datasets

    def load_first_of_each_product(self) -> Dict[str, xr.Dataset]:
        """Load only the first file of each product group.

        Returns
        -------
        dict[str, xr.Dataset]
            Product key → Dataset (first file only).
        """
        result: Dict[str, xr.Dataset] = {}
        for product, flist in self.product_groups().items():
            ds = self.load(flist[0])
            result[product] = ds
        return result

    # ------------------------------------------------------------------
    # Source detection & canonical access
    # ------------------------------------------------------------------

    def _build_meta(self, key: str, ds: xr.Dataset, file_path: str) -> None:
        """Detect data source and build SourceMeta for a loaded dataset."""
        adapter_cls = detect_source(ds, file_path)
        if adapter_cls is None:
            self._unmatched.append(key)
            return
        adapter = adapter_cls()
        self._metas[key] = adapter.adapt(ds)

    def meta(self, key: str) -> SourceMeta:
        """Return the SourceMeta for a loaded dataset.

        Raises
        ------
        KeyError
            If *key* is not loaded or its source was not recognized.
        """
        if key not in self._datasets:
            raise KeyError(f"No dataset loaded for key '{key}'.")
        if key not in self._metas:
            raise KeyError(
                f"Dataset '{key}' has no recognized data source. "
                f"Available sources: ROMS, CMEMS."
            )
        return self._metas[key]

    @property
    def unmatched(self) -> List[str]:
        """Dataset keys that could not be matched to a known source."""
        return list(self._unmatched)

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def summary(self) -> pd.DataFrame:
        """Return a summary DataFrame of all loaded datasets.

        Columns: file, variables, dimensions, time_range, size_mb
        """
        rows = []
        for name, ds in self._datasets.items():
            rows.append({
                "file": name,
                "variables": ", ".join(list(ds.data_vars.keys())),
                "dimensions": dict(ds.dims),
                "time_range": self._time_range(ds),
                "size_mb": ds.nbytes / (1024 * 1024),
            })
        return pd.DataFrame(rows)

    def inspect(self, dataset_key: str) -> str:
        """Produce a human-readable inspection report for one dataset.

        Parameters
        ----------
        dataset_key : str
            Key in ``self._datasets`` (typically the filename).

        Returns
        -------
        str
            Multi-line report suitable for printing or display.
        """
        ds = self._datasets[dataset_key]
        lines: List[str] = []

        # Dimensions
        lines.append(f"Dimensions: {dict(ds.sizes)}")
        lines.append(f"Coordinates: {list(ds.coords)}")

        # Data variables with metadata
        for vname in ds.data_vars:
            da = ds[vname]
            dims = list(da.dims)
            attrs = da.attrs
            parts = [f"  {vname}: dims={dims}  dtype={da.dtype}"]
            if "units" in attrs:
                parts.append(f"units={attrs['units']}")
            if "long_name" in attrs:
                parts.append(f"long_name={attrs['long_name']}")
            lines.append("  ".join(parts))

        # Time
        t_range = self._time_range(ds)
        if t_range:
            lines.append(f"Time range: {t_range}")

        # Spatial / vertical ranges
        for coord_name in self._RANGE_COORDS:
            if coord_name in ds.coords:
                vals = ds[coord_name].values
                lines.append(
                    f"{coord_name}: [{vals.min():.4f}, {vals.max():.4f}] "
                    f"({len(vals)} pts)"
                )

        return "\n".join(lines)

    def inspect_all(self) -> Dict[str, str]:
        """Return inspection reports for all loaded datasets.

        Returns
        -------
        dict[str, str]
            Dataset key → report string.
        """
        return {key: self.inspect(key) for key in self._datasets}

    @staticmethod
    def _time_range(ds: xr.Dataset) -> Optional[str]:
        """Extract min/max time string from a dataset if a time-like dim exists."""
        time_names = {"time", "ocean_time", "t", "date"}
        found = None
        for tn in time_names:
            if tn in ds.coords or tn in ds.dims:
                found = tn
                break
        if found is None:
            return None
        try:
            t = ds[found].values
            return f"{pd.Timestamp(t[0])} → {pd.Timestamp(t[-1])}"
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    @property
    def datasets(self) -> Dict[str, xr.Dataset]:
        return self._datasets

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    def __getitem__(self, key: str) -> xr.Dataset:
        return self._datasets[key]

    def __len__(self) -> int:
        return len(self._datasets)

    def __repr__(self) -> str:
        n = len(self._datasets)
        return f"<NCReader: {n} dataset(s) loaded from {self._data_dir}>"
