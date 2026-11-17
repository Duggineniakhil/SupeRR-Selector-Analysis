"""Shared helpers: project paths and config loading."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def path(cfg: dict, key: str) -> Path:
    p = ROOT / cfg["paths"][key]
    if key != "raw":
        p.mkdir(parents=True, exist_ok=True)
    return p
