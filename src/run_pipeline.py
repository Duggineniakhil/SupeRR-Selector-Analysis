"""Pipeline entrypoint. Run from the project root with:  python -I src/run_pipeline.py [stage ...]

Stages: ingest (T1), clean (T2), state (T3). Default: all.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # our own src/ only (-I drops it)

import clean  # noqa: E402
import ingest  # noqa: E402
import state  # noqa: E402
from common import load_config  # noqa: E402

STAGES = {"ingest": ingest.run, "clean": clean.run, "state": state.run}

if __name__ == "__main__":
    cfg = load_config()
    todo = sys.argv[1:] or list(STAGES)
    for s in todo:
        print(f"== {s}")
        res = STAGES[s](cfg)
        if s == "state":
            sys.stdout.buffer.write(("\n".join(res[2]) + "\n").encode("utf-8"))
