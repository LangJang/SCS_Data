"""
Cartopy-based map plotting for oceanographic DataArrays.

Provides a single-call function to render a 2-D field on a geographic
map with coastlines, land fill, gridlines, and colorbar.
"""

from pathlib import Path
from typing import Optional

import numpy as np
import xarray as xr
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature

# ---------------------------------------------------------------------------
# Default style
# ---------------------------------------------------------------------------

DEFAULT_RCPARAMS = {
    "font.size": 11,
    "figure.dpi": 100,
}


def _apply_default_style() -> None:
    for k, v in DEFAULT_RCPARAMS.items():
        plt.rcParams.setdefault(k, v)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plot_map(
    da: xr.DataArray,
    lon: Optional[np.ndarray] = None,
    lat: Optional[np.ndarray] = None,
    *,
    title: str = "",
    cmap: str = "Spectral_r",
    figsize: tuple[float, float] = (10, 7),
    projection: ccrs.Projection | None = None,
    coastline_kw: dict | None = None,
    land_kw: dict | None = None,
    gridline_kw: dict | None = None,
    colorbar_kw: dict | None = None,
    output_path: str | Path | None = None,
    output_dpi: int = 200,
    show: bool = False,
) -> plt.Figure:
    """Plot a 2-D DataArray on a geographic map with coastlines.

    Parameters
    ----------
    da : xr.DataArray
        2-D field to plot (e.g., temperature, salinity at one time/depth).
    lon : np.ndarray or None
        2-D longitude array. If None, inferred from *da* coords
        (looks for ``lon``, ``longitude``, ``long``, ``lon_rho``).
    lat : np.ndarray or None
        2-D latitude array.  If None, inferred from *da* coords
        (looks for ``lat``, ``latitude``, ``lat_rho``).
    title : str
        Suptitle text.
    cmap : str
        Matplotlib colormap name.
    figsize : (float, float)
        Figure size in inches.
    projection : cartopy Projection or None
        Defaults to ``PlateCarree()``.
    coastline_kw : dict or None
        Passed to ``ax.add_feature(cfeature.COASTLINE, **kw)``.
    land_kw : dict or None
        Passed to ``ax.add_feature(cfeature.LAND, **kw)``.
    gridline_kw : dict or None
        Passed to ``ax.gridlines(**kw)``.
    colorbar_kw : dict or None
        Passed to ``plt.colorbar(**kw)``.
    output_path : str, Path or None
        If provided, save the figure to this path.
    output_dpi : int
        DPI for the saved figure.
    show : bool
        If True, call ``plt.show()``.

    Returns
    -------
    plt.Figure
        The matplotlib Figure object.
    """
    _apply_default_style()

    # --- Resolve coordinates -------------------------------------------------
    if lon is None:
        lon = _auto_coord(da, {"lon", "longitude", "long", "lon_rho"})
    if lat is None:
        lat = _auto_coord(da, {"lat", "latitude", "lat_rho"})

    if projection is None:
        projection = ccrs.PlateCarree()

    # --- Build figure --------------------------------------------------------
    fig, ax = plt.subplots(
        figsize=figsize,
        subplot_kw={"projection": projection},
    )

    # Coastline
    cl_kw = {"linewidth": 0.5}
    if coastline_kw:
        cl_kw.update(coastline_kw)
    ax.add_feature(cfeature.COASTLINE, **cl_kw)

    # Land fill
    ld_kw = {"facecolor": "0.9"}
    if land_kw:
        ld_kw.update(land_kw)
    ax.add_feature(cfeature.LAND, **ld_kw)

    # Data
    im = ax.pcolormesh(
        lon, lat, da.values,
        shading="auto",
        cmap=cmap,
        transform=ccrs.PlateCarree(),
    )

    # Colorbar
    cb_kw: dict = {"shrink": 0.75}
    unit = da.attrs.get("units", "")
    if unit:
        cb_kw["label"] = unit
    if colorbar_kw:
        cb_kw.update(colorbar_kw)
    plt.colorbar(im, ax=ax, **cb_kw)

    # Title
    ax.set_title(title, fontsize=13)

    # Gridlines (labels disabled by default — Cartopy GEOS compat)
    gl_kw: dict = {"draw_labels": False, "linewidth": 0.3, "alpha": 0.5}
    if gridline_kw:
        gl_kw.update(gridline_kw)
    gl = ax.gridlines(**gl_kw)
    if gl_kw.get("draw_labels", False):
        gl.top_labels = False
        gl.right_labels = False

    fig.tight_layout()

    # --- Output --------------------------------------------------------------
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=output_dpi, bbox_inches="tight")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return fig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auto_coord(da: xr.DataArray, candidates: set[str]) -> np.ndarray:
    """Return the coordinate array matching one of *candidates*."""
    for name in candidates:
        if name in da.coords:
            return da[name].values
        if name in da.dims:
            return da[name].values
    # Fallback: check the underlying dataset
    ds = getattr(da, "_ds", None) if hasattr(da, "_ds") else None
    if ds is not None:
        for name in candidates:
            if name in ds.coords:
                return ds[name].values
    raise KeyError(
        f"Cannot auto-detect coordinate from candidates {candidates}. "
        f"Available coords: {list(da.coords)}. Pass lon= / lat= explicitly."
    )
