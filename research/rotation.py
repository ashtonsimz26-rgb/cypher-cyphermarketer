#!/usr/bin/env python3.12
"""
rotation.py — depth-3 variety across five axes (F4.5).

WHY DEPTH 3, AND WHY FROM THE LEDGER.
state/last_format.json holds ONE value, overwritten each time. That depth-1
memory is why two formats alternated for 28 drafts and why every proposal
looked like the last: a one-slot memory can only ever enforce "differ from the
immediately previous one", which a two-element alternation satisfies forever.
History lives in the append-only ledger; read it there.

A proposal must differ from EACH of the last three on at least MIN_AXES axes.
"""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
RUNS = HERE / "ledger" / "runs.jsonl"

AXES = ("format", "hook_type", "brand", "composition", "scene")
DEPTH = 3
MIN_AXES = 2


def recent(depth: int = DEPTH, path: Path | None = None) -> list[dict]:
    """The last `depth` proposed drafts, newest first, from the ledger."""
    p = path or RUNS
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("event") in ("draft_proposed", "draft_built"):
            rows.append({a: r.get(a) for a in AXES})
    return list(reversed(rows))[:depth]


def differs_enough(cand: dict, prior: dict, min_axes: int = MIN_AXES) -> tuple[bool, int]:
    """Count axes that differ. A None on either side counts as NOT differing —
    unknown history must not be mistaken for variety."""
    n = sum(1 for a in AXES
            if cand.get(a) is not None and prior.get(a) is not None
            and cand.get(a) != prior.get(a))
    return n >= min_axes, n


def is_varied(cand: dict, history: list[dict] | None = None,
              min_axes: int = MIN_AXES) -> tuple[bool, str]:
    """True when `cand` differs from EVERY one of the last three on >= min_axes."""
    hist = recent() if history is None else history
    for i, prior in enumerate(hist):
        ok, n = differs_enough(cand, prior, min_axes)
        if not ok:
            return False, ("too similar to proposal -%d (%d/%d axes differ)"
                           % (i + 1, n, min_axes))
    return True, "differs from the last %d on >= %d axes" % (len(hist), min_axes)
