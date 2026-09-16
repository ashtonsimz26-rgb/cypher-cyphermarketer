#!/usr/bin/env python3.12
"""
pairing.py — pair selection for `which_would_you_pull` (E4).

SOUL has named this format since the beginning and it has NEVER been produced.
It is the only format in the rotation that asks the reader for a response, and
the account's reply/quote/bookmark count is zero, so it is the only format
pointed at the number that matters.

★★ BOTH CARDS MUST BE ON THE **PULL** ROUTE. Not merely obtainable — pullable.
The question is literally "which would you PULL", so a set reward is disqualified
however good it looks: it is EARNABLE, and showing it here would imply a pack
outcome, which is the claim SOUL's obtainability rule forbids. The test is per
CARD, so a reachable card beside an earnable one fails on the second card even
though the post is "about" the first.

THE PAIRING RULE (ruled 2026-09-16): same silhouette, different colorway, and
where possible sharing a hook tag so one sentence can frame both.

★ GROUP-LEVEL ROTATION, and why it is not optional. 138 viable pairs exist, but
`Nike Air Force 1 Low` supplies 45 of them and the top five silhouettes supply
95. A uniform pick over PAIRS shows the AF1 about a third of the time, and the
format dies of sameness the way everything else here has. So the silhouette
GROUP is chosen first with a no-repeat window, and only then a pair within it.

★ SILHOUETTE NAMES ARE NOT NORMALISED HERE. The catalog spells the SB Dunk 22
ways and the AF1 four, which is a CATALOG defect reported to CPA on 2026-09-16.
Normalising in marketing code would hide it behind a workaround, so this module
groups on the catalog's `name` VERBATIM and accepts the smaller pairing space —
138 is the conservative floor and it is ample.
"""
from __future__ import annotations
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
RUNS = HERE / "ledger" / "runs.jsonl"

GROUP_DEPTH = 5              # no silhouette group repeats within this many pair posts
MIN_GROUP_SIZE = 2           # a "pair" needs two distinct shoes


def recent_groups(depth: int = GROUP_DEPTH, path: Path | None = None) -> list[str]:
    """Silhouette groups used by the last `depth` two-card drafts, newest first.

    From the append-only LEDGER, never from a one-slot state file — the same
    lesson rotation.py records: a depth-1 memory can only enforce "differ from
    the previous one", which an alternation satisfies forever.
    """
    p = path or RUNS
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("event") in ("draft_built", "draft_proposed") and r.get("pair_group"):
            out.append(r["pair_group"])
    return list(reversed(out))[:depth]


def groups(rows: list[dict]) -> dict[str, list[dict]]:
    """Silhouette name -> its distinct shoes. Only groups that can form a pair."""
    g: dict[str, dict[str, dict]] = {}
    for r in rows:
        name = (r.get("name") or "").strip()
        if not name or not r.get("image_name"):
            continue
        g.setdefault(name, {})[r["image_name"]] = r
    return {k: list(v.values()) for k, v in g.items() if len(v) >= MIN_GROUP_SIZE}


def _shared_tags(a: dict, b: dict) -> int:
    return len(set(a.get("tags") or ()) & set(b.get("tags") or ()))


def pick_pair(rows: list[dict], history: list[str] | None = None,
              rng: random.Random | None = None) -> dict | None:
    """Choose a silhouette group, then a pair inside it. None when nothing fits.

    Returns {"group", "a", "b", "shared_tags", "eligible_groups"}.

    None is a normal outcome and must stay one: on a day when every group has
    been used recently, the correct answer is a different format, not a repeat.
    """
    rng = rng or random
    hist = recent_groups() if history is None else history
    g = groups(rows)
    if not g:
        return None
    fresh = {k: v for k, v in g.items() if k not in set(hist)}
    pool = fresh or {}
    if not pool:
        # Every group is in the window. Do NOT fall back to the full set — that
        # would make the window decorative. Say no and let the digest pick
        # another format.
        return None
    group = rng.choice(sorted(pool))
    shoes = pool[group]
    # Prefer a pair that shares a hook tag: 113 of the 138 live pairs do, and a
    # shared tag is what lets ONE sentence frame both cards instead of two.
    best, best_score = None, -1
    for i in range(len(shoes)):
        for j in range(i + 1, len(shoes)):
            sc = _shared_tags(shoes[i], shoes[j])
            if sc > best_score:
                best, best_score = (shoes[i], shoes[j]), sc
    if best is None:
        return None
    a, b = best
    if rng.random() < 0.5:
        a, b = b, a                      # which card sits left is not a judgement
    return {"group": group, "a": a, "b": b, "shared_tags": best_score,
            "eligible_groups": len(pool)}
