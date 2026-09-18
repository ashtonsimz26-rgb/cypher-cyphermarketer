#!/usr/bin/env python3.12
"""graph.py — the generated goal graph. Zero LLM, zero network, zero spend.

The generator exists because the hand-authored graph could not notice the
ledger moving underneath it. That is only an improvement if the generator
FAILS CLOSED: a source it cannot read must produce an absent claim, never a
zero and never a stale carry-forward. A generator that silently prints the
last-known number is worse than the transcription it replaced, because it
looks live.

So these tests do not check that it produces a graph. They check that it
REFUSES to produce numbers it did not measure, that the citation rule cannot
be violated by a future edit, and that it did not grow its own copy of the
obtainable-set SQL.
"""
import ast
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import graph as G

FAILS = []


def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c:
        FAILS.append(m)


REPO = Path(__file__).resolve().parent.parent
SRC = (REPO / "graph.py").read_text(encoding="utf-8")


def unverified_facts() -> dict:
    """Every fact absent — the total-source-failure case."""
    names = ("n_content", "impressions", "likes", "goal_events", "kind_split",
             "lifetime", "n_rails", "tier_ladder", "top_tier_pullable", "earnable",
             "frame_check_built")
    return {n: G.Fact(n, None, "test", False) for n in names}


def verified_facts(goal_events=0) -> dict:
    f = unverified_facts()
    f["n_content"] = G.Fact("n_content", 4, "test", True)
    f["impressions"] = G.Fact("impressions", 54, "test", True)
    f["likes"] = G.Fact("likes", 3, "test", True)
    f["goal_events"] = G.Fact("goal_events", goal_events, "test", True)
    f["lifetime"] = G.Fact("lifetime", {"rows": 22, "impressions": 204, "likes": 8},
                           "test", True)
    f["n_rails"] = G.Fact("n_rails", ["A"] * 9, "test", True)
    return f


def card_text(ir) -> str:
    return " || ".join(i for c in ir["cards"] for i in c["items"])


print("\n=== 1. AN UNREADABLE SOURCE IS NOT A ZERO ===")
rows, okflag = G.read_jsonl(Path("/nonexistent/metrics.jsonl"))
ok(rows == [] and okflag is False,
   "read_jsonl reports verified=False for a missing file, not an empty ledger")
ok(G.Fact("x", None, "s", False).verified is False, "Fact carries its own verification bit")
try:
    G.Fact("x", None, "s", False).require()
    ok(False, "require() must raise on an unverified fact")
except ValueError:
    ok(True, "require() raises rather than handing out an unmeasured value")

print("\n=== 2. AN UNVERIFIED FACT IS NEVER DRAWN AS A NUMBER ===")
ir, unver = G.build_ir(unverified_facts())
txt = card_text(ir)
ok("NOT VERIFIED" in txt, "the artifact states, in its own body, what it could not verify")
ok(len(unver) == len(unverified_facts()),
   "every unverified fact is reported (%d of %d)" % (len(unver), len(unverified_facts())))
goal_node = next(n for n in ir["nodes"] if n["id"] == "goal")
ok(goal_node["tag"] == "count: unverified",
   "the goal tag says 'unverified', never 'count: 0' (%s)" % goal_node["tag"])
ok("Agent record is 0 posts" not in txt and "0 impressions" not in txt,
   "no fabricated zero appears anywhere in the cards")
ev = next(n for n in ir["nodes"] if n["id"] == "evidence")
ok(ev["sublabel"].endswith("n=?"), "n is '?' when unmeasured, not 0 (%s)" % ev["sublabel"])

print("\n=== 3. ZERO AND UNVERIFIED ARE DIFFERENT CLAIMS ===")
ir0, _ = G.build_ir(verified_facts(goal_events=0))
g0 = next(n for n in ir0["nodes"] if n["id"] == "goal")
ok(g0["tag"] == "count: 0",
   "a MEASURED zero is drawn as 0 — absence of the event, not absence of data")
ok(g0["tag"] != goal_node["tag"],
   "…and is textually distinct from the unverified case")

print("\n=== 4. THE GOAL'S EXPIRY CLAUSE FIRES ON ITS OWN ===")
ir1, _ = G.build_ir(verified_facts(goal_events=1))
t1 = card_text(ir1)
ok("GOAL MET" in t1, "a non-zero goal event flips the card to GOAL MET")
ok("expires the day the first one lands" not in t1,
   "…and the pending-goal wording is gone, not left contradicting it")
ok("expires the day the first one lands" in card_text(ir0),
   "…while a zero count keeps the pending wording")

print("\n=== 5. THE CITATION RULE IS STRUCTURAL, NOT REMEMBERED ===")
s = G.cite_lifetime(204, 8, 22, 4)
ok("204" in s and "8" in s and "22" in s and "4" in s,
   "cite_lifetime returns totals AND the split in one string")
ok("which only 4 are agent content" in s,
   "…the split is in the same sentence, per SOUL.md § THE GOAL")
lit = [n for n in ast.walk(ast.parse(SRC))
       if isinstance(n, ast.Constant) and n.value in (204, 8)]
ok(not lit, "no lifetime figure is hardcoded anywhere in graph.py")
ok(card_text(ir0).count("204") <= 1,
   "the total is rendered at most once, and only via cite_lifetime")

print("\n=== 6. NO SECOND COPY OF THE OBTAINABLE SET ===")
# daily_digest: "written out four times in three files ... three chances for
# one of them to drift". A copy here would be the fifth.
ok("with reachable as" not in SRC.lower(),
   "graph.py does not redefine REACHABLE_CTE")
ok("set_rewards" not in SRC or "earnable as" not in SRC.lower(),
   "graph.py does not redefine EARNABLE_CTE")
ok("dd.REACHABLE_CTE" in SRC and "dd.OBTAINABLE_CTE" in SRC,
   "…it imports both from daily_digest instead")

print("\n=== 7. THE MEASURED NUMBERS ARE NOT IN THE SOURCE ===")
for n in (54, 150, 135):
    hits = [x for x in ast.walk(ast.parse(SRC))
            if isinstance(x, ast.Constant) and x.value == n]
    ok(not hits, "%d is measured, never typed into graph.py" % n)

print("\n=== 8. A FAILED DELIVERY CANNOT BE REPORTED AS SUCCESS ===")
d = next(n for n in ast.walk(ast.parse(SRC))
         if isinstance(n, ast.FunctionDef) and n.name == "deliver")
raises = [n for n in ast.walk(d) if isinstance(n, ast.Raise)]
ok(len(raises) >= 2, "deliver() raises on a bad receipt and on a non-zero exit (%d)" % len(raises))
ok("returncode != 0" in SRC and 'out.get("ok")' in SRC,
   "…it checks BOTH the exit code and the receipt's ok flag")

print("\n=== 9. THE IR IT EMITS IS SCHEMA-SHAPED ===")
for ir_x in (ir, ir0, ir1):
    json.dumps(ir_x)
ok(ir0["schema_version"] == 2 and ir0["diagram_type"] == "workflow",
   "emits workflow schema v2")
ok(ir0["meta"]["quality_profile"] == "showcase", "requests the showcase bar")
ids = [n["id"] for n in ir0["nodes"]]
ok(len(ids) == len(set(ids)), "node ids are unique")
edge_ends = {e["from"] for e in ir0["edges"]} | {e["to"] for e in ir0["edges"]}
ok(edge_ends <= set(ids), "every edge endpoint resolves to a node")

print("\n=== 10. IT WRITES ONLY WHERE IT DECLARES ===")
# The earlier version of this section tested for the STRING "posts.jsonl" and
# failed on a read-only constant. Presence is not a write path — that is the
# same conflation contracts.py calls permission-vs-presence. Test the calls.
WRITE_OPS = ("write_text", "write_bytes", "unlink", "rmdir", "touch", "rename")
tree = ast.parse(SRC)
writes = []
for n in ast.walk(tree):
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
        tgt = ast.unparse(n.func.value)
        if n.func.attr in WRITE_OPS:
            writes.append((n.func.attr, tgt))
        elif n.func.attr == "open":
            mode = n.args[0].value if (n.args and isinstance(n.args[0], ast.Constant)) else "r"
            if "a" in str(mode) or "w" in str(mode):
                writes.append(("open:" + str(mode), tgt))
ALLOWED = {"IR_PATH", "GRAPH_LEDGER", "a.out"}
bad = [w for w in writes if w[1].split(".")[0] not in ALLOWED]
ok(not bad, "every write targets IR_PATH / GRAPH_LEDGER only (stray: %s)" % bad)
ok(any(t.startswith("GRAPH_LEDGER") for _, t in writes),
   "…and the append-only graph ledger is one of them")
ok(not [w for w in writes if "METRICS" in w[1]],
   "metrics.jsonl is read, never written — the evidence it measures stays untouched")
ok("profile" not in {t.split(".")[0] for _, t in writes},
   "profile/ is cited, never edited — SOUL and memory are Ashton's to change")
ok("POSTS" not in SRC and "PROPOSALS" not in SRC,
   "no unused ledger handles left implying capability the module lacks")

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
