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


def md_table(df, index: bool = True, floatfmt: str = "{:.2f}") -> str:
    """Minimal DataFrame → GitHub markdown table (avoids the tabulate dependency)."""
    import pandas as pd

    d = df.reset_index() if index else df
    def fmt(v):
        if isinstance(v, float):
            return "" if pd.isna(v) else floatfmt.format(v)
        return str(v)
    cols = [str(c) for c in d.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(fmt(v) for v in row) + " |" for row in d.itertuples(index=False)]
    return "\n".join(lines)
