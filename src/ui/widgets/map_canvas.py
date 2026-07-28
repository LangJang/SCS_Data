"""
Cartopy map canvas embedded in a PyQt6 widget.

Provides :class:`MapCanvas` — a ``FigureCanvasQTAgg`` subclass that
renders 2-D oceanographic fields inside the SCS Marine Data Tool GUI.

Features:
- ``update_map()`` for fast field switching (reuses figure/axes)
- ``map_clicked`` signal for point-and-click time-series extraction
- ``region_selected`` signal for spatial subset bounding-box export
- Integrated ``NavigationToolbar2QT`` for zoom/pan/save
"""

from pathlib import Path
from typing import Optional

import numpy as np
import xarray as xr

import matplotlib
matplotlib.use("QtAgg")

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavToolbar

import cartopy.crs as ccrs
import cartopy.feature as cfeature

from PyQt6.QtWidgets import QVBoxLayout, QWidget
from PyQt6.QtCore import pyqtSignal, Qt


# ---------------------------------------------------------------------------
# Default style (mirrors src/viz/map_plotter.py)
# ---------------------------------------------------------------------------

DEFAULT_RCPARAMS = {"font.size": 11, "figure.dpi": 100}

for k, v in DEFAULT_RCPARAMS.items():
    matplotlib.rcParams.setdefault(k, v)


# ---------------------------------------------------------------------------
# MapCanvas
# ---------------------------------------------------------------------------

class MapCanvas(FigureCanvasQTAgg):
    """Cartopy map widget for interactive oceanographic data browsing.

    Embeds a single Cartopy :class:`~cartopy.mpl.geoaxes.GeoAxes` inside a
    PyQt6 widget.  Call :meth:`update_map` to switch between variables,
    time steps, or depth levels.

    Signals
    -------
    map_clicked : (lon: float, lat: float)
        Emitted when the user clicks on the map.  Connect to a slot that
        opens a time-series popup for the clicked location.
    region_selected : (lon_min, lon_max, lat_min, lat_max)
        Emitted when the user drags a rectangle on the map.  Connect to a
        slot that records the bounding box for spatial subset export.
    """

    map_clicked = pyqtSignal(float, float)
    region_selected = pyqtSignal(float, float, float, float)

    DEFAULT_FIGSIZE = (8, 6)
    DEFAULT_CMAP = "Spectral_r"

    def __init__(
        self,
        parent: QWidget | None = None,
        figsize: tuple[float, float] = DEFAULT_FIGSIZE,
        projection: ccrs.Projection | None = None,
    ) -> None:
        # ---- Figure & Axes ----
        self._fig = Figure(figsize=figsize)
        self._projection = projection or ccrs.PlateCarree()
        self._ax = self._fig.add_subplot(111, projection=self._projection)

        # Draw initial coastline / land
        self._ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
        self._ax.add_feature(cfeature.LAND, facecolor="0.9")

        # Placeholder banner (centered, like ERDDAP "Please wait...")
        self._placeholder = self._fig.text(
            0.5, 0.5,
            "Select a variable from the data tree to begin.\n"
            "Use the time and depth sliders to explore different layers.",
            ha="center", va="center", fontsize=14,
            color="0.4", style="italic",
            bbox={"facecolor": "white", "edgecolor": "0.7",
                  "boxstyle": "round,pad=0.6", "alpha": 0.85},
        )

        self._fig.tight_layout()

        super().__init__(self._fig)
        self.setParent(parent)

        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        # ---- Click event ----
        self.mpl_connect("button_press_event", self._on_click)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_loading(self, variable_label: str = "") -> None:
        """Display a 'please wait' banner before rendering begins."""
        text = f"Loading {variable_label} ...\nPlease wait — generating map."
        if hasattr(self, "_placeholder") and self._placeholder is not None:
            self._placeholder.set_text(text)
            self._placeholder.set_visible(True)
        self.draw_idle()

    def update_map(
        self,
        da: xr.DataArray,
        lon: np.ndarray | None = None,
        lat: np.ndarray | None = None,
        *,
        title: str = "",
        cmap: str = "",
        unit: str = "",
        extent: tuple[float, float, float, float] | None = None,
    ) -> None:
        """Replace the current map with a new 2-D field.

        Completely replaces the axes to avoid colorbar accumulation
        (which caused the map to shrink on each redraw).  Uses
        ``rasterized=True`` on the data mesh for smooth window resize.

        Parameters
        ----------
        extent : (west, east, south, north) or None
            If provided, zoom the map to this geographic extent.
        """
        # Resolve coordinates
        if lon is None:
            lon = _auto_coord(da, {"lon", "longitude", "long", "lon_rho"})
        if lat is None:
            lat = _auto_coord(da, {"lat", "latitude", "lat_rho"})

        cmap = cmap or self.DEFAULT_CMAP

        # Hide the placeholder banner
        if hasattr(self, "_placeholder") and self._placeholder is not None:
            self._placeholder.set_visible(False)

        # ---- Remove ALL old axes (main + colorbar from previous renders) ----
        for ax in list(self._fig.axes):
            self._fig.delaxes(ax)
        self._ax = self._fig.add_subplot(111, projection=self._projection)

        self._ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
        self._ax.add_feature(cfeature.LAND, facecolor="0.9")
        gl = self._ax.gridlines(linewidth=0.3, alpha=0.5, draw_labels=False)
        gl.top_labels = False
        gl.right_labels = False

        # ---- Draw mesh (rasterized = bitmap, fast resize) ----
        mesh = self._ax.pcolormesh(
            lon, lat, da.values,
            shading="auto",
            cmap=cmap,
            transform=ccrs.PlateCarree(),
            rasterized=True,
        )

        # ---- Colorbar ----
        cb_kw = {"shrink": 0.75}
        if unit:
            cb_kw["label"] = unit
        self._fig.colorbar(mesh, ax=self._ax, **cb_kw)

        # ---- Title ----
        self._ax.set_title(title, fontsize=13)

        # ---- Zoom to extent ----
        if extent is not None:
            self._ax.set_extent(extent, crs=ccrs.PlateCarree())

        # Re-attach rectangle selector (new axes = new selector)
        self._connect_rectangle_selector()

        self._fig.tight_layout()
        self.draw_idle()

    # ------------------------------------------------------------------
    # Overlay scatter (point data on top of map)
    # ------------------------------------------------------------------

    def add_overlay_scatter(self, df, clear_first: bool = True) -> None:
        """Add scatter + pie overlay from a fishery DataFrame.

        Single-record locations → scatter point (size ∝ catch_kg).
        Multi-record locations → pie chart (Wedge patches, size ∝ total catch).

        Parameters
        ----------
        df : pd.DataFrame
            Must have ``lon``, ``lat``, ``species``, ``catch_kg``.
        clear_first : bool
            Remove any previous overlay before drawing.
        """
        import matplotlib.patches as mpatches
        from matplotlib.patches import Wedge

        if clear_first:
            self._clear_overlay()

        if df is None or len(df) == 0:
            return

        species_list = sorted(df["species"].unique())
        cmap = matplotlib.colormaps.get_cmap("tab10")
        colors = {s: cmap(i % 10) for i, s in enumerate(species_list)}

        # Base radius in degrees — scales with catch
        grouped = df.groupby(["lat", "lon"])
        max_total = grouped["catch_kg"].sum().max()
        min_total = grouped["catch_kg"].sum().min()
        base_radius = 0.02  # degrees (~2 km)

        artists: list = []
        for (lat, lon), group in grouped:
            n_spp = len(group)
            total_kg = group["catch_kg"].sum()
            # Radius scales 0.02° → 0.12° based on total catch
            if max_total > min_total:
                frac = (total_kg - min_total) / (max_total - min_total + 1)
            else:
                frac = 0.5
            radius = base_radius + 0.10 * frac

            if n_spp == 1:
                # ---- Single species: scatter point ----
                row = group.iloc[0]
                sp = row["species"]
                size = 30 + 70 * frac
                sc = self._ax.scatter(
                    [lon], [lat],
                    s=size,
                    c=[colors[sp]],
                    alpha=0.75, edgecolors="k", linewidth=0.3,
                    transform=ccrs.PlateCarree(),
                    zorder=10,
                )
                artists.append(sc)
            else:
                # ---- Multi-species: pie chart via Wedges ----
                pie_sizes = group["catch_kg"].values.astype(float)
                pie_colors = [colors[sp] for sp in group["species"]]
                cumsum = np.cumsum(pie_sizes)
                total = cumsum[-1]
                angles = 2 * np.pi * cumsum / total
                start_angle = 90  # top

                for i in range(len(pie_sizes)):
                    theta1 = start_angle - 360 * (cumsum[i - 1] / total if i > 0 else 0)
                    theta2 = start_angle - 360 * (cumsum[i] / total)
                    wedge = Wedge(
                        (lon, lat),
                        r=radius,
                        theta1=theta2,
                        theta2=theta1,
                        facecolor=pie_colors[i],
                        edgecolor="k",
                        linewidth=0.2,
                        alpha=0.85,
                        transform=ccrs.PlateCarree(),
                        zorder=10,
                    )
                    self._ax.add_patch(wedge)
                    artists.append(wedge)

        # Legend — proxy Patch handles
        legend_handles = [
            mpatches.Patch(color=colors[sp], label=sp)
            for sp in species_list
        ]
        leg = self._fig.legend(
            handles=legend_handles,
            title="Species",
            loc="center right",
            fontsize=7,
            title_fontsize=8,
            markerscale=0.5,
            framealpha=0.9,
            ncols=1,
            bbox_to_anchor=(-0.02, 0.5),
        )
        self._overlay_artists = artists
        self._overlay_legend = leg
        self._fig.subplots_adjust(left=0.18)
        self.draw_idle()

    def clear_overlay(self) -> None:
        """Remove scatter overlay from the map."""
        self._clear_overlay()
        self.draw_idle()

    def _clear_overlay(self) -> None:
        """Internal: remove scatter artists, Wedge patches, and legend."""
        if hasattr(self, "_overlay_artists"):
            for artist in self._overlay_artists:
                if isinstance(artist, list):
                    for a in artist:
                        a.remove()
                else:
                    artist.remove()
            self._overlay_artists = []
        if hasattr(self, "_overlay_legend") and self._overlay_legend is not None:
            self._overlay_legend.remove()
            self._overlay_legend = None
            self._fig.subplots_adjust(left=0.125)  # reset margin

    # ------------------------------------------------------------------
    # Navigation toolbar (for external embedding)
    # ------------------------------------------------------------------

    def create_toolbar(self, parent: QWidget) -> NavToolbar:
        """Return a ``NavigationToolbar2QT`` wired to this canvas."""
        return NavToolbar(self, parent)

    # ------------------------------------------------------------------
    # Rectangle selector
    # ------------------------------------------------------------------

    def _connect_rectangle_selector(self) -> None:
        """Install a matplotlib RectangleSelector on the axes."""
        from matplotlib.widgets import RectangleSelector

        self._rect_selector = RectangleSelector(
            self._ax, self._on_rect_select,
            useblit=True,
            button=[1],                # left mouse button
            minspanx=5, minspany=5,
            spancoords="pixels",
            interactive=False,
        )

    def _on_rect_select(self, eclick, erelease) -> None:
        """Emit :attr:`region_selected` from the selector bbox."""
        lon_min = min(eclick.xdata, erelease.xdata)
        lon_max = max(eclick.xdata, erelease.xdata)
        lat_min = min(eclick.ydata, erelease.ydata)
        lat_max = max(eclick.ydata, erelease.ydata)
        self.region_selected.emit(lon_min, lon_max, lat_min, lat_max)

    # ------------------------------------------------------------------
    # Click → lon, lat
    # ------------------------------------------------------------------

    def _on_click(self, event) -> None:
        """Forward map clicks to :attr:`map_clicked`.

        Ignores clicks on toolbar buttons and navigation events.
        """
        # Only left-click in data space (not toolbar, not None coords)
        if event.button != 1:
            return
        if event.xdata is None or event.ydata is None:
            return
        if self._fig.canvas.toolbar is not None and self._fig.canvas.toolbar.mode != "":
            return  # user is panning / zooming
        self.map_clicked.emit(float(event.xdata), float(event.ydata))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _auto_coord(da: xr.DataArray, candidates: set[str]) -> np.ndarray:
    """Return the coordinate array matching one of *candidates*."""
    for name in candidates:
        if name in da.coords:
            return da[name].values
        if name in da.dims:
            return da[name].values
    raise KeyError(
        f"Cannot auto-detect coordinate from candidates {candidates}. "
        f"Available coords: {list(da.coords)}."
    )
