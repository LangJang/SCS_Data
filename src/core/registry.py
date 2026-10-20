"""
SQLite metadata registry for datasets and overlays.

Replaces the dataset/overlay sections of ``config.yaml`` with a single-file
SQLite database so that every data registration is "equal" (平权) and
re-importing an existing name *updates* the row instead of appending a
duplicate (no pollution from repeated edits).

Schema
------
``datasets`` — one row per gridded NetCDF dataset.  List-valued fields are
stored as JSON text.  ``file_layout`` / ``time_axis`` / ``date_pattern`` are
the "read template" that tells the GUI how time is structured:

- ``file_layout``: ``single`` (one file) | ``directory`` (folder + glob)
- ``time_axis``:   ``none`` (no time dim) | ``internal`` (time dim inside the
  file) | ``per_file`` (one timestep per file, date in filename)
- ``date_pattern``: strptime-style filename date pattern (only ``per_file``)

``overlays`` — one row per point-data layer (fishery CSV / station xlsx).
The heterogeneous extra keys (keywords, summary, station_*) live in a single
JSON ``payload`` column so they round-trip losslessly.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from src.core.paths import REGISTRY_DB, SCS_DATA_DIR


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_DATASET_COLS = (
    "name", "source", "keywords", "variables",
    "default_resolution", "available_resolutions",
    "lon_min", "lon_max", "lat_min", "lat_max",
    "time_start", "time_end", "time_frequency",
    "vertical_type", "vertical_layers", "vertical_range", "depth_values",
    "path", "file_pattern",
    "hidden", "file_layout", "time_axis", "date_pattern",
)

_DDL = """
CREATE TABLE IF NOT EXISTS datasets (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    name                  TEXT    NOT NULL UNIQUE,
    source                TEXT    NOT NULL DEFAULT '',
    keywords              TEXT    NOT NULL DEFAULT '[]',
    variables             TEXT    NOT NULL DEFAULT '[]',
    default_resolution    REAL    NOT NULL DEFAULT 0.1,
    available_resolutions TEXT    NOT NULL DEFAULT '[]',
    lon_min               REAL    NOT NULL DEFAULT -180,
    lon_max               REAL    NOT NULL DEFAULT 180,
    lat_min               REAL    NOT NULL DEFAULT -90,
    lat_max               REAL    NOT NULL DEFAULT 90,
    time_start            TEXT    NOT NULL DEFAULT '',
    time_end              TEXT    NOT NULL DEFAULT '',
    time_frequency        TEXT    NOT NULL DEFAULT '',
    vertical_type         TEXT    NOT NULL DEFAULT '',
    vertical_layers       INTEGER NOT NULL DEFAULT 0,
    vertical_range        TEXT    NOT NULL DEFAULT '[]',
    depth_values          TEXT    NOT NULL DEFAULT '[]',
    path                  TEXT    NOT NULL DEFAULT '',
    file_pattern          TEXT    NOT NULL DEFAULT '',
    hidden                INTEGER NOT NULL DEFAULT 0,
    file_layout           TEXT    NOT NULL DEFAULT 'single',
    time_axis             TEXT    NOT NULL DEFAULT 'internal',
    date_pattern          TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS overlays (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    label   TEXT    NOT NULL UNIQUE,
    type    TEXT    NOT NULL DEFAULT 'fishery',
    path    TEXT    NOT NULL DEFAULT '',
    payload TEXT    NOT NULL DEFAULT '{}'
);
"""


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    """Open a connection and ensure the schema exists."""
    conn = sqlite3.connect(str(REGISTRY_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    conn.execute("PRAGMA user_version = 1")
    return conn


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _json_dumps(value) -> str:
    if value is None:
        return "[]"
    return json.dumps(value, ensure_ascii=False)


def _json_loads(text) -> Optional[object]:
    if not text:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _abs_path(p: str) -> str:
    """Return an absolute path string, resolving relative paths against the
    project root (so registry lookups no longer depend on the process cwd)."""
    path = Path(p)
    if path.is_absolute():
        return str(path)
    return str(SCS_DATA_DIR / path)


# ---------------------------------------------------------------------------
# DatasetConfig bridging (lazy import to avoid a circular import)
# ---------------------------------------------------------------------------

def _raw_to_dataset(raw: dict):
    from src.core.config_reader import DatasetConfig
    return DatasetConfig(raw)


def _cfg_to_values(cfg) -> tuple:
    return (
        cfg.name, cfg.source,
        _json_dumps(cfg.keywords), _json_dumps(cfg.variables),
        cfg.default_resolution, _json_dumps(cfg.available_resolutions),
        cfg.lon_min, cfg.lon_max, cfg.lat_min, cfg.lat_max,
        cfg.time_start, cfg.time_end, cfg.time_frequency,
        cfg.vertical_type, cfg.vertical_layers,
        _json_dumps(cfg.vertical_range), _json_dumps(cfg.depth_values),
        _abs_path(cfg.path), cfg.file_pattern,
        int(bool(cfg.hidden)), cfg.file_layout, cfg.time_axis, cfg.date_pattern,
    )


def row_to_dataset(row: sqlite3.Row):
    """Build a :class:`DatasetConfig` from a ``datasets`` row."""
    raw = {
        "name": row["name"],
        "source": row["source"],
        "keywords": _json_loads(row["keywords"]) or [],
        "variables": _json_loads(row["variables"]) or [],
        "resolution": {
            "default": row["default_resolution"],
            "available": _json_loads(row["available_resolutions"]) or [],
        },
        "spatial": {
            "lon": {"min": row["lon_min"], "max": row["lon_max"]},
            "lat": {"min": row["lat_min"], "max": row["lat_max"]},
        },
        "temporal": {
            "start": row["time_start"],
            "end": row["time_end"],
            "frequency": row["time_frequency"],
        },
        "vertical": {
            "type": row["vertical_type"],
            "layers": row["vertical_layers"],
            "range": _json_loads(row["vertical_range"]) or [],
            "depth_values": _json_loads(row["depth_values"]) or [],
        },
        "path": row["path"],
        "file_pattern": row["file_pattern"],
        "hidden": bool(row["hidden"]),
        "file_layout": row["file_layout"],
        "time_axis": row["time_axis"],
        "date_pattern": row["date_pattern"],
    }
    return _raw_to_dataset(raw)


def row_to_overlay(row: sqlite3.Row) -> dict:
    """Reconstruct an overlay dict (label/type/path + JSON payload keys)."""
    payload = _json_loads(row["payload"]) or {}
    entry = {"label": row["label"], "type": row["type"], "path": row["path"]}
    if isinstance(payload, dict):
        entry.update(payload)
    return entry


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def list_datasets(include_hidden: bool = True) -> List:
    """Return all registered datasets (optionally excluding hidden ones)."""
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM datasets ORDER BY id").fetchall()
        result = [row_to_dataset(r) for r in rows]
        if not include_hidden:
            result = [d for d in result if not d.hidden]
        return result
    finally:
        conn.close()


def list_overlays() -> List[dict]:
    """Return all registered overlays."""
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM overlays ORDER BY id").fetchall()
        return [row_to_overlay(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Writes (upsert on unique name/label)
# ---------------------------------------------------------------------------

def insert_dataset(raw: dict, conn: Optional[sqlite3.Connection] = None) -> int:
    """Insert or update a dataset row from a DatasetConfig-shaped *raw* dict."""
    cfg = _raw_to_dataset(raw)
    values = _cfg_to_values(cfg)

    cols = ", ".join(_DATASET_COLS)
    placeholders = ", ".join("?" for _ in _DATASET_COLS)
    set_clause = ", ".join(
        f"{c} = excluded.{c}" for c in _DATASET_COLS if c != "name"
    )
    sql = (
        f"INSERT INTO datasets ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT(name) DO UPDATE SET {set_clause}"
    )

    own = conn is None
    if own:
        conn = _connect()
    try:
        cur = conn.execute(sql, values)
        if own:
            conn.commit()
        return cur.lastrowid
    finally:
        if own:
            conn.close()


def insert_overlay(raw: dict, conn: Optional[sqlite3.Connection] = None) -> int:
    """Insert or update an overlay row from an overlay *raw* dict."""
    label = raw["label"]
    otype = raw.get("type", "fishery")
    path = raw.get("path", "")
    payload = {k: v for k, v in raw.items() if k not in ("label", "type", "path")}
    values = (label, otype, _abs_path(path), _json_dumps(payload))

    own = conn is None
    if own:
        conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO overlays (label, type, path, payload) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(label) DO UPDATE SET "
            "type = excluded.type, path = excluded.path, payload = excluded.payload",
            values,
        )
        if own:
            conn.commit()
        return cur.lastrowid
    finally:
        if own:
            conn.close()


# ---------------------------------------------------------------------------
# Migration / seeding
# ---------------------------------------------------------------------------

def migrate_from_config(yaml_path: str | Path, force: bool = False) -> tuple[int, int]:
    """Seed the registry from ``config.yaml`` (idempotent).

    Skips when the ``datasets`` table is already populated unless *force*.
    Only ``datasets`` and ``overlays`` move; ``preset_regions`` and
    ``color_styles`` remain YAML-only.
    """
    conn = _connect()
    try:
        count = conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
        if count and not force:
            return (0, 0)

        if force:
            conn.execute("DELETE FROM overlays")
            conn.execute("DELETE FROM datasets")

        with open(yaml_path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

        n_ds = n_ov = 0
        for d in raw.get("datasets", []):
            insert_dataset(d, conn=conn)
            n_ds += 1
        for ov in raw.get("overlays", []):
            insert_overlay(ov, conn=conn)
            n_ov += 1

        conn.commit()
        return (n_ds, n_ov)
    finally:
        conn.close()


def ensure_seeded(yaml_path: str | Path) -> None:
    """Seed from *yaml_path* on first run (when the registry is empty)."""
    if not Path(yaml_path).exists():
        return
    conn = _connect()
    try:
        count = conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
    finally:
        conn.close()
    if count == 0:
        migrate_from_config(yaml_path, force=False)
