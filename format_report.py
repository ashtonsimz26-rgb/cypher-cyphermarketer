#!/usr/bin/env python3.12
"""
format_report.py — weekly FORMAT performance. Shape only, never subject.

v1.3 ruling (2026-09-09): the agent may measure and report which FORMATS
perform and adjust format rotation accordingly. It may NOT select SUBJECTS by
heat, trend velocity or engagement potential. This report is the measuring half
of that ruling, and the restriction is STRUCTURAL rather than conventional —
GROUP_DIMENSIONS is a positive filter, the same discipline as
editorial.ALLOWED_FEEDBACK_CODES. A dimension enters the aggregation key only
by being in that frozenset. Adding "image_name", "hook_type", "brand" or any
shoe identifier here would convert this into topic-selection-by-engagement,
which is the objective v1.3 rejected.

hook_type is RECORDED but NOT grouped (ruling C2): format is shape, hook_type
leans subject.

LEDGER COMPLETENESS (ruling R3): posts.jsonl covers 5 of the 22 posts on
@appCYPHERR — the other 17 were hand-posted outside the agent. "Our posts"
here means AGENT-POSTED content, scoped explicitly via in_post_ledger, never
silently "the ones we logged".
"""
from __future__ import annotations
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
METRICS = HERE / "ledger" / "metrics.jsonl"
POSTS = HERE / "ledger" / "posts.jsonl"
RUNS = HERE / "ledger" / "runs.jsonl"
PROPOSALS = HERE / "ledger" / "proposals.jsonl"
LABELS = HERE / "data" / "post_format_labels.json"

# ── THE POSITIVE FILTER ──────────────────────────────────────────────────────
# Shape, not subject. Do not widen without a ruling.
GROUP_DIMENSIONS = frozenset({"format"})

# Below this many posts in a format, the report REFUSES to rank. With 3:1
# across four posts, "story_spotlight outperforms price_journey" would be noise
# wearing a number. Ranking is a claim about relative performance; n=4 cannot
# support one.
MIN_N_FOR_RANKING = 5


def _read(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def load_labels() -> dict:
    try:
        return json.loads(LABELS.read_text())
    except Exception:
        return {}


def format_of(tweet_id: str, posted_rows: list[dict], labels: dict) -> tuple[str | None, str, str]:
    """(format, method, confidence). Denormalised row first, hand label second."""
    for r in posted_rows:
        if r.get("tweet_id") == tweet_id and r.get("format"):
            return r["format"], "denormalised", "exact"
    lab = labels.get(tweet_id)
    if lab:
        return lab.get("format"), lab.get("method", "hand"), lab.get("confidence", "unknown")
    return None, "unresolved", "none"


def aggregate(days: int | None = 7) -> dict:
    metrics = _read(METRICS)
    posted = [r for r in _read(POSTS) if r.get("event") == "posted"]
    labels = load_labels()

    # R3: agent-posted only, stated explicitly.
    rows = [m for m in metrics if m.get("in_post_ledger")]
    excluded = [m for m in metrics if not m.get("in_post_ledger")]

    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        rows = [m for m in rows
                if datetime.fromisoformat(m["created_at"].replace("Z", "+00:00")) >= cutoff]

    buckets: dict[tuple, list[dict]] = defaultdict(list)
    announcements, unresolved = [], []
    for m in rows:
        if m.get("kind") == "announcement":       # own category (ruling C3)
            announcements.append(m); continue
        if m.get("kind") != "content":
            continue
        fmt, method, conf = format_of(m["tweet_id"], posted, labels)
        if not fmt:
            unresolved.append(m); continue
        m = {**m, "_format": fmt, "_method": method, "_confidence": conf}
        key = tuple(sorted((d, m["_format"]) for d in GROUP_DIMENSIONS))
        buckets[key].append(m)
    return {"buckets": buckets, "announcements": announcements,
            "unresolved": unresolved, "excluded_non_agent": excluded,
            "window_days": days}


def _stat(rows: list[dict], field: str) -> tuple[float, int, int]:
    vals = [r[field] for r in rows if r.get(field) is not None]
    if not vals:
        return 0.0, 0, 0
    return sum(vals) / len(vals), min(vals), max(vals)


def render(agg: dict) -> str:
    L = []
    w = agg["window_days"]
    L.append("CYPHERMARKETER — FORMAT PERFORMANCE (%s)" % (
        "last %d days" % w if w else "all time"))
    L.append("=" * 62)
    L.append("Grouped by: %s  (structural — subject dimensions cannot enter)"
             % ", ".join(sorted(GROUP_DIMENSIONS)))
    L.append("")

    buckets = agg["buckets"]
    if not buckets:
        L.append("  No agent-posted content in this window. That is a valid outcome.")
    for key, rows in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        fmt = dict(key)["format"]
        n = len(rows)
        imp, ilo, ihi = _stat(rows, "impressions")
        lik, _, _ = _stat(rows, "likes")
        eng, _, _ = _stat(rows, "engagements")
        L.append("  %-18s n=%d" % (fmt, n))
        L.append("      impressions  mean %5.1f   range %d-%d" % (imp, ilo, ihi))
        L.append("      likes        mean %5.1f" % lik)
        L.append("      engagements  mean %5.1f" % eng)
        methods = {r["_method"] for r in rows}
        L.append("      attribution  %s" % ", ".join(sorted(methods)))
        L.append("")

    # ── the n-floor: state n, refuse to rank below it ────────────────────────
    L.append("-" * 62)
    ranked = [(dict(k)["format"], v) for k, v in buckets.items()]
    under = [f for f, v in ranked if len(v) < MIN_N_FOR_RANKING]
    if under:
        L.append("NO RANKING. %s below the n=%d floor (%s)." % (
            "Formats" if len(under) > 1 else "Format", MIN_N_FOR_RANKING,
            ", ".join("%s n=%d" % (f, len(v)) for f, v in ranked if f in under)))
        L.append("A relative-performance claim needs more posts than this. The")
        L.append("means above are descriptive only — do NOT read them as a ranking.")
    else:
        order = sorted(ranked, key=lambda kv: -_stat(kv[1], "impressions")[0])
        L.append("RANKING by mean impressions (all formats at or above n=%d):"
                 % MIN_N_FOR_RANKING)
        for f, v in order:
            L.append("  %-18s n=%d  mean impressions %5.1f"
                     % (f, len(v), _stat(v, "impressions")[0]))

    if agg["announcements"]:
        a = agg["announcements"]
        imp, lo, hi = _stat(a, "impressions")
        L.append("")
        L.append("ANNOUNCEMENTS (own category — not a format, never in format stats)")
        L.append("  n=%d  impressions mean %5.1f  range %d-%d" % (len(a), imp, lo, hi))

    if agg["unresolved"]:
        L.append("")
        L.append("UNRESOLVED FORMAT: %d post(s) — not counted in any bucket."
                 % len(agg["unresolved"]))
    if agg["excluded_non_agent"]:
        L.append("")
        L.append("SCOPE: %d post(s) on the account are NOT agent-posted and are"
                 % len(agg["excluded_non_agent"]))
        L.append("excluded (ruling R3). posts.jsonl is not the whole timeline.")
    return "\n".join(L)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Weekly format performance report")
    ap.add_argument("--days", type=int, default=7, help="window; 0 = all time")
    a = ap.parse_args()
    print(render(aggregate(a.days or None)))
