"""
One-time migration: config.yaml → registry.db (SQLite).

Seeds the ``datasets`` and ``overlays`` tables from ``config.yaml``.
Idempotent — skips when the registry is already populated, unless
``--force`` is passed (which rebuilds both tables from scratch).

Usage:
    cd D:\\ChatWithAI\\SCS_data
    D:\\PYTHON\\envs\\scs_marine\\python.exe tools/migrate_config_to_registry.py
    D:\\PYTHON\\envs\\scs_marine\\python.exe tools/migrate_config_to_registry.py --force
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core import registry
from src.core.config_reader import _CONFIG_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true",
        help="Rebuild the registry from config.yaml even if already populated.",
    )
    parser.add_argument(
        "--config", type=str, default=str(_CONFIG_PATH),
        help="Path to config.yaml (default: project config.yaml).",
    )
    args = parser.parse_args()

    n_ds, n_ov = registry.migrate_from_config(args.config, force=args.force)
    if n_ds == 0 and n_ov == 0:
        print("Registry already populated — nothing to migrate. "
              "Use --force to rebuild.")
    else:
        print(f"Migrated {n_ds} datasets and {n_ov} overlays "
              f"into {registry.REGISTRY_DB}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
