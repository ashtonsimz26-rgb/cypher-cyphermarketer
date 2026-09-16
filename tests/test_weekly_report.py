#!/usr/bin/env python3.12
"""E6 — the weekly report, honest by construction. Zero LLM, zero network.

The load-bearing claim is section 1: the pipeline signals NEVER touch
metrics.jsonl. "GRAIL posts get more impressions" would be
subject-selection-by-performance wearing a different column name, and a positive
filter on the engagement key would not stop it, because the join would happen in
a different function. So the separation is asserted structurally.
"""
import ast, json, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import format_report as FR

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

REPO = Path(__file__).resolve().parent.parent
TREE = ast.parse((REPO / "format_report.py").read_text())

def fn(name):
    return next(n for n in ast.walk(TREE) if isinstance(n, ast.FunctionDef) and n.name == name)

print("\n=== 1. THE SIGNALS CANNOT SEE ENGAGEMENT ===")
for name in ("pipeline_signals", "render_signals"):
    names = {n.id for n in ast.walk(fn(name)) if isinstance(n, ast.Name)}
    ok("METRICS" not in names,
       "%s never references METRICS — engagement and subject cannot be joined" % name)
ok("METRICS" in {n.id for n in ast.walk(fn("aggregate")) if isinstance(n, ast.Name)},
   "…while aggregate() does, so the separation is real and not vacuous")

print("\n=== 2. FORMAT ONLY IN THE AGGREGATION KEY ===")
ok(FR.GROUP_DIMENSIONS == frozenset({"format"}), "GROUP_DIMENSIONS is exactly {format}")
ok(not ({"image_name", "hook_type", "brand", "tier", "colorway"} & FR.GROUP_DIMENSIONS),
   "no subject dimension is in it")
ok(isinstance(FR.GROUP_DIMENSIONS, frozenset), "…and it cannot be widened at runtime")

print("\n=== 3. EVERY SECTION STATES n AND REFUSES BELOW ITS FLOOR ===")
for k, need in FR.MIN_N.items():
    ok(FR._floor(k, need - 1) is not None, "%-12s refuses at n=%d" % (k, need - 1))
    ok(FR._floor(k, need) is None, "%-12s speaks at n=%d" % (k, need))
    msg = FR._floor(k, 0)
    ok("n=0" in msg and str(need) in msg,
       "…and the refusal names both the count and the floor: %r" % msg[:52])

print("\n=== 4. THE REPORT CAN SAY NOTHING AND STOP ===")
empty_agg = {"buckets": {}, "announcements": [], "unresolved": [],
             "excluded_non_agent": [], "window_days": 7}
empty_sig = {"n_proposals": 0, "n_rejects": 0, "n_briefs": 0, "n_runs": 3}
ok(FR.nothing_to_report(empty_agg, empty_sig), "a truly empty week reports nothing")
ok(not FR.nothing_to_report(dict(empty_agg, unresolved=[{"x": 1}]), empty_sig),
   "an unresolved post is enough to report")
ok(not FR.nothing_to_report(empty_agg, dict(empty_sig, n_rejects=1)),
   "a single rejection is enough to report")
ok(not FR.nothing_to_report(empty_agg, dict(empty_sig, n_proposals=1)),
   "a single draft is enough to report")

print("\n=== 5. NO HEADING IS PRINTED WITH NOTHING UNDER IT ===")
# NOTE: weekly(7) short-circuits to the R4 one-liner today, because the
# denominator fix in section 6 left the 7-day window with nothing in it. So the
# heading check runs against the ALL-TIME report, which is the one that has
# buckets. Checking the empty window would have tested nothing.
out = FR.weekly(None)
lines = out.splitlines()
ranked = [i for i, l in enumerate(lines) if l.startswith("RANKING by mean impressions")]
for i in ranked:
    ok(i + 1 < len(lines) and lines[i + 1].strip() != "",
       "the ranking heading always has a line under it")
ok("NO RANKING" in out or "Nothing is ranked, and that is the finding" in out,
   "the report says why it is not ranking")
ok("do NOT read them as a ranking" in out,
   "…and warns that the descriptive means are not one")
seven = FR.weekly(7)
ok("Nothing worth reporting this week" in seven,
   "an empty 7-day window is ONE LINE, not a page (R4)")
ok(len(seven.splitlines()) <= 4, "…%d lines" % len(seven.splitlines()))

print("\n=== 6. THE DIVERGENCE DENOMINATOR EXCLUDES PRE-E5 DRAFTS ===")
sig = FR.pipeline_signals(None)
ok(sig["pre_e5_drafts"] > 0, "there ARE drafts predating the contract: %d" % sig["pre_e5_drafts"])
ok(sig["n_briefs"] == 0,
   "…and none of them counts as a brief — 0%% over n=36 would read as a mechanism "
   "working perfectly when it did not exist")
allt = FR.weekly(None)
ok("predate the fact_id contract" in allt, "the exclusion is STATED, not silent")

print("\n=== 7. THE TIER SECTION MEASURES THE RULED TARGETS ===")
import daily_digest as DD
ok(DD.GROUP_TARGET_SHARE == {"top": 0.15, "premium": 0.50, "body": 0.35},
   "the report reads E3's targets rather than restating them: %s" % DD.GROUP_TARGET_SHARE)
src = (REPO / "format_report.py").read_text()
ok("GROUP_TARGET_SHARE" in src and "TIER_GROUP" in src,
   "…so a change to the weighting cannot leave the report claiming the old one")

print("\n=== 8. THE WINDOW IS A REAL FILTER ===")
now = datetime.now(timezone.utc)
rows = [{"ts": (now - timedelta(days=d)).isoformat(), "d": d} for d in (1, 3, 9, 30)]
ok([r["d"] for r in FR._window(rows, 7)] == [1, 3], "7 days keeps the recent two")
ok(len(FR._window(rows, None)) == 4, "days=None keeps everything")
ok(FR._window([{"ts": "not-a-date"}], 7) == [], "an unparseable ts is dropped, not crashed on")

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
