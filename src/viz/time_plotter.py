"""
Time-series and multi-panel visualization for marine environmental data.

Builds on :mod:`src.viz.map_plotter` for spatial maps, adding
line plots, daily map grids, and source-comparison overlays.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, List, Dict

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import xarray as xr

from src.core.canonical import SourceMeta
from src.core.roms_utils import extract_field, extract_timeseries, TimeseriesResult
from src.core.time_assembler import AssembledMeta
from src.viz.map_plotter import plot_map

# ---------------------------------------------------------------------------
# Default style for time-series plots
# ---------------------------------------------------------------------------

_DEFAULT_FIGSIZE = (12, 5)
_GAP_COLOR = "lightcoral"
_GAP_ALPHA = 0.15


# ---------------------------------------------------------------------------
# Single-variable time series line plot
# ---------------------------------------------------------------------------

def plot_timeseries(
    ts: TimeseriesResult,
    *,
    title: str = "",
    ylabel: str | None = None,
    figsize: tuple = _DEFAULT_FIGSIZE,
    color: str = "tab:blue",
    marker: str = "o",
    markersize: int = 4,
    linewidth: float = 1.5,
    missing_indices: List[int] | None = None,
    output_path: str | Path | None = None,
    output_dpi: int = 200,
    show: bool = False,
    ax: plt.Axes | None = None,
) -> plt.Figure:
    """Plot a time series as a line chart with optional gap shading.

    Parameters
    ----------
    ts : TimeseriesResult
        Data from :func:`~src.core.roms_utils.extract_timeseries` or
        :func:`~src.core.roms_utils.extract_point`.
    title : str
    ylabel : str or None
        Default: ``"{label} ({units})"``.
    figsize : tuple
    color : str
    marker : str
    markersize : int
    linewidth : float
    missing_indices : list[int] or None
        Indices *before* which a temporal gap exists (e.g. from
        :attr:`AssembledMeta.missing_indices`).  Gaps are shaded in red.
    output_path : str or Path or None
    output_dpi : int
    show : bool
    ax : Axes or None
        If provided, plot into this axes instead of creating a new figure.

    Returns
    -------
    plt.Figure
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    if ylabel is None:
        ylabel = f"{ts.label} ({ts.units})" if ts.units else ts.label

    x = ts.times if ts.times is not None else np.arange(ts.n)

    ax.plot(x, ts.values, color=color, marker=marker,
            markersize=markersize, linewidth=linewidth,
            label=ts.label)

    ax.set_xlabel("Date")
    ax.set_ylabel(ylabel)
    ax.set_title(title or ts.label)
    ax.grid(True, alpha=0.3)

    # Format x-axis as dates
    if ts.times is not None:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        fig.autofmt_xdate(rotation=30)

    # Shade gap regions
    if missing_indices and ts.times is not None and len(ts.times) > 1:
        for idx in missing_indices:
            if 0 <= idx < len(ts.times) - 1:
                gap_start = ts.times[idx]
                gap_end = ts.times[idx + 1]
                ax.axvspan(gap_start, gap_end, color=_GAP_COLOR,
                          alpha=_GAP_ALPHA, label="_gap")

    fig.tight_layout()

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=output_dpi, bbox_inches="tight")

    if show:
        plt.show()
    elif output_path is None and ax is None:
        # Only close if we created it and aren't showing
        pass

    return fig


# ---------------------------------------------------------------------------
# Multi-panel daily map grid
# ---------------------------------------------------------------------------

def plot_daily_maps(
    ds: xr.Dataset,
    meta: SourceMeta,
    canonical_name: str,
    time_indices: List[int],
    *,
    time_labels: List[str] | None = None,
    level_idx: int = 0,
    ncols: int = 4,
    cmap: str = "Spectral_r",
    figsize_per_panel: tuple = (4, 3.5),
    colorbar_label: str | None = None,
    output_path: str | Path | None = None,
    output_dpi: int = 200,
    show: bool = False,
) -> plt.Figure:
    """Plot a grid of spatial maps, one per selected day.

    Each panel is a single-timestep Cartopy map rendered via
    :func:`src.viz.map_plotter.plot_map`.  Shared colorbar across all
    panels.

    Parameters
    ----------
    ds : xr.Dataset
        Multi-timestep dataset.
    meta : SourceMeta
    canonical_name : str
        Canonical variable to plot on each panel.
    time_indices : list[int]
        Which timestep indices to include.
    time_labels : list[str] or None
        Labels for each panel (e.g. ``"2023-01-01"``).  Auto-derived if
        None.
    level_idx : int
        Vertical level.
    ncols : int
        Number of columns in the grid.
    cmap : str
    figsize_per_panel : tuple
        ``(width, height)`` per panel.  Figure size is computed
        automatically.
    colorbar_label : str or None
        Default: ``"{display_label} ({units})"``.
    output_path : str or Path or None
    output_dpi : int
    show : bool

    Returns
    -------
    plt.Figure
    """
    n_panels = len(time_indices)
    nrows = int(np.ceil(n_panels / ncols))

    pw, ph = figsize_per_panel
    fig = plt.figure(figsize=(pw * ncols, ph * nrows))

    if time_labels is None:
        time_labels = [f"t={i}" for i in time_indices]

    if colorbar_label is None:
        colorbar_label = (f"{meta.display_label(canonical_name)} "
                          f"({meta.standard_units(canonical_name)})")

    # Determine global vmin/vmax for shared colorbar
    all_values = []
    for ti in time_indices:
        da_slice, _, _ = extract_field(ds, meta, canonical_name, ti, level_idx)
        all_values.append(da_slice.values[~np.isnan(da_slice.values)])
    if all_values:
        global_min = np.percentile(np.concatenate(all_values), 2)
        global_max = np.percentile(np.concatenate(all_values), 98)
    else:
        global_min, global_max = 0, 1

    import cartopy.crs as ccrs
    from matplotlib.colors import Normalize

    norm = Normalize(vmin=global_min, vmax=global_max)
    projection = ccrs.PlateCarree()

    for pi, ti in enumerate(time_indices):
        da_slice, lon, lat = extract_field(ds, meta, canonical_name, ti, level_idx)

        ax = fig.add_subplot(nrows, ncols, pi + 1, projection=projection)
        ax.coastlines(resolution="50m", linewidth=0.5)
        ax.set_extent(
            [float(lon.min()), float(lon.max()),
             float(lat.min()), float(lat.max())],
            crs=projection,
        )

        pcm = ax.pcolormesh(lon, lat, da_slice.values,
                            cmap=cmap, norm=norm,
                            transform=projection)

        ax.set_title(time_labels[pi], fontsize=9)

    # Shared colorbar
    cbar_ax = fig.add_axes([0.92, 0.08, 0.015, 0.84])
    cbar = fig.colorbar(pcm, cax=cbar_ax, label=colorbar_label)
    cbar.ax.tick_params(labelsize=7)

    fig.suptitle(
        f"{meta.source_name} — {meta.display_label(canonical_name)}",
        fontsize=12, fontweight="bold",
    )

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=output_dpi, bbox_inches="tight")

    if show:
        plt.show()

    return fig


# ---------------------------------------------------------------------------
# Comparison plot — ROMS vs CMEMS overlaid time series
# ---------------------------------------------------------------------------

def plot_comparison_timeseries(
    ts_a: TimeseriesResult,
    ts_b: TimeseriesResult,
    source_names: tuple = ("ROMS", "CMEMS"),
    *,
    title: str = "",
    ylabel: str | None = None,
    figsize: tuple = _DEFAULT_FIGSIZE,
    colors: tuple = ("tab:blue", "tab:orange"),
    output_path: str | Path | None = None,
    output_dpi: int = 200,
    show: bool = False,
) -> plt.Figure:
    """Overlay two time series (e.g. ROMS vs CMEMS) for comparison.

    Parameters
    ----------
    ts_a, ts_b : TimeseriesResult
        The two time series to compare.
    source_names : tuple[str, str]
        Display names for the two sources.
    title : str
    ylabel : str or None
    figsize : tuple
    colors : tuple[str, str]
        Colors for the two lines.
    output_path, output_dpi, show

    Returns
    -------
    plt.Figure
    """
    fig, ax = plt.subplots(figsize=figsize)

    if ylabel is None:
        ylabel = ts_a.units or ""

    # Source A
    x_a = ts_a.times if ts_a.times is not None else np.arange(ts_a.n)
    ax.plot(x_a, ts_a.values, color=colors[0], marker="o",
            markersize=4, linewidth=1.5, label=f"{source_names[0]}: {ts_a.label}")

    # Source B
    x_b = ts_b.times if ts_b.times is not None else np.arange(ts_b.n)
    ax.plot(x_b, ts_b.values, color=colors[1], marker="s",
            markersize=4, linewidth=1.5, label=f"{source_names[1]}: {ts_b.label}")

    ax.set_xlabel("Date")
    ax.set_ylabel(ylabel)
    ax.set_title(title or f"{source_names[0]} vs {source_names[1]} — {ts_a.label}")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)

    if ts_a.times is not None:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        fig.autofmt_xdate(rotation=30)

    fig.tight_layout()

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=output_dpi, bbox_inches="tight")

    if show:
        plt.show()

    return fig


# ---------------------------------------------------------------------------
# Multi-variable time series summary
# ---------------------------------------------------------------------------

def plot_multi_variable_timeseries(
    ds: xr.Dataset,
    meta: SourceMeta,
    variables: List[str],
    *,
    level_idx: int = 0,
    lat_range: tuple | None = None,
    lon_range: tuple | None = None,
    missing_indices: List[int] | None = None,
    ncols: int = 2,
    figsize: tuple = (14, 10),
    output_path: str | Path | None = None,
    output_dpi: int = 200,
    show: bool = False,
) -> plt.Figure:
    """Plot multiple canonical variables as a panel of time series subplots.

    Parameters
    ----------
    ds, meta : source dataset and metadata.
    variables : list[str]
        Canonical variable names.
    level_idx : int
    lat_range, lon_range : tuple or None
    missing_indices : list[int] or None
    ncols : int
    figsize : tuple
    output_path, output_dpi, show

    Returns
    -------
    plt.Figure
    """
    n_vars = len(variables)
    nrows = int(np.ceil(n_vars / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, squeeze=False)

    for i, var in enumerate(variables):
        r, c = i // ncols, i % ncols
        ax = axes[r, c]

        try:
            ts = extract_timeseries(
                ds, meta, var, level_idx,
                lat_range=lat_range, lon_range=lon_range,
            )
            plot_timeseries(
                ts, missing_indices=missing_indices, ax=ax,
                title=ts.label,
            )
        except Exception as exc:
            ax.text(0.5, 0.5, f"{var}\nSKIP: {exc}",
                    ha="center", va="center", transform=ax.transAxes,
                    fontsize=9, color="gray")
            ax.set_title(var, fontsize=9)

    # Hide unused axes
    for i in range(n_vars, nrows * ncols):
        r, c = i // ncols, i % ncols
        axes[r, c].set_visible(False)

    fig.suptitle(
        f"{meta.source_name} — Time Series Summary",
        fontsize=13, fontweight="bold",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.97])

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=output_dpi, bbox_inches="tight")

    if show:
        plt.show()

    return fig
