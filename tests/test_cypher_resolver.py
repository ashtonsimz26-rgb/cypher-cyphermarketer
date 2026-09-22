#!/usr/bin/env python3.12
"""cypher:// — a first-party source. OFFLINE: replays a recorded fixture.

The sources rule is UNCHANGED: a moment still needs a non-empty sources[] and
every term is still checked against a fetched document. What widened is what a
source may BE. The design claim under test is that nothing downstream is
special — outcome, found/missing, numeric matching and the cache are inherited
from the HTTP path rather than reimplemented beside it.

★ OFFLINE BY DEFAULT (2026-09-17). These sections test what the RENDERER
produces given rows, so the rows can be a recording: tests/fixtures/cypher_sql.json,
captured from live by tests/record_cypher_fixture.py. Re-record when the
resolver's SQL changes. A hand-written fixture would test the assumption rather
than the renderer, so it is a recording and never hand-edited.

★ TWO SECTIONS LEFT, and they did not move because they CANNOT:
  * privacy  -> tests/test_cypher_privacy_live.py
  * rarity   -> tests/test_rarity_vocab_live.py
Both assert agreement with the LIVE database — a real owner absent from a real
document, and the code's casing map matching the live schema's two vocabularies.
Against a fixture each becomes true by construction and could never fail again.
They skip loudly (exit 77) rather than passing when the DB is unreachable.

Why the split at all: this suite hit Supabase and timed out under load, read as
a FAILURE, and passed on re-run. An intermittently failing suite teaches people
to re-run rather than to read, which is how a real failure gets waved through.
"""
import ast, json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from research import verify as V

# ── the recording, replayed ─────────────────────────────────────────────────
_FIX = json.loads((Path(__file__).resolve().parent / "fixtures"
                   / "cypher_sql.json").read_text(encoding="utf-8"))


def _replay(q: str):
    """★ FAILS LOUD ON A MISS. A fixture that silently returns [] for an
    unrecorded query would turn every new code path into a fake NOT MINTED —
    a passing test over a query nobody recorded. Re-record instead."""
    k = " ".join(q.split())
    if k not in _FIX:
        raise KeyError("no recorded rows for: %s\n  -> re-run "
                       "tests/record_cypher_fixture.py" % k[:120])
    return _FIX[k]


# ★ KEEP THE REAL FUNCTION. Section 5 tests the READ-ONLY assert that lives in
# _cypher_sql itself, and swapping it for the replayer would delete the thing
# under test — the check would "pass" on the replayer's KeyError for entirely
# the wrong reason. The assert is a precondition on the statement text and
# fires before any database call, so exercising it offline is honest.
_REAL_CYPHER_SQL = V._cypher_sql

V._cypher_sql = _replay
V.CACHE_DIR = Path(tempfile.mkdtemp())      # never answer from a stale disk cache
# ★ THE LEDGER IS SCRATCH (2026-09-22). This suite feeds resolve_cypher malformed
# URIs and a fake "db down", and verify.py ledgers both — so until this line, every
# run appended SIX fake rows to the REAL ledger/research.jsonl (368 by the time it
# was noticed). The suite asserts at the end that its rows landed HERE, and that
# the real ledger did not grow.
_REAL_RESEARCH = Path(__file__).resolve().parent.parent / "ledger" / "research.jsonl"
_REAL_N0 = _REAL_RESEARCH.read_text().count("\n") if _REAL_RESEARCH.exists() else 0
V.LEDGER = Path(tempfile.mkdtemp()) / "research.jsonl"

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

REPO = Path(__file__).resolve().parent.parent
CARD   = "cypher://card/aj4_sb_varsity_red/GRAIL"
SET    = "cypher://set/Nike%20x%20Jordan%204%20SB"
SERIAL = "cypher://serial/aj4_sb_varsity_red/GRAIL/1"

print("\n=== 1. THE THREE KINDS RESOLVE ===")
for uri, must in ((CARD, ["CYPHER CATALOG CARD", "GRAIL", "10000"]),
                  (SET, ["CYPHER SET", "aj4_sb_navy", "aj4_sb_pine_green"]),
                  (SERIAL, ["CYPHER SERIAL", "set_reward", "2026-06-23"])):
    t = V.fetch_text(uri)
    ok(t and all(m in t for m in must), "%-46s -> %d chars" % (uri.split("//")[1][:44], len(t)))

print("\n=== 2. SAME SHAPE AS THE HTTP PATH — CALLERS BRANCH IDENTICALLY ===")
r = V.verify_fact(SERIAL, ["set_reward"], ["1", "10000"])
ok(set(r) == {"outcome", "ok", "fetched", "found", "missing", "url", "cached", "reason"},
   "the returned dict has exactly the HTTP path's keys: %s" % sorted(r))
ok(r["outcome"] == "verified" and r["ok"] and r["fetched"], "a supported claim verifies: %s" % r["outcome"])
r2 = V.verify_fact(SERIAL, ["pack_open"])
ok(r2["outcome"] == "contradicted" and r2["missing"] == ["pack_open"],
   "an unsupported term contradicts, with the term named: %s" % r2["missing"])
r3 = V.verify_fact(CARD, [], ["10000"])
ok(r3["outcome"] == "verified", "numeric_terms work through the same matcher")
r4 = V.verify_fact(CARD, [], ["1000"])
ok(r4["outcome"] == "contradicted",
   "…separator-aware: 1000 is NOT satisfied by 10000")

print("\n=== 3. UNREACHABLE IS 'unverified', NEVER 'contradicted' ===")
_orig = V._cypher_sql          # the replayer, restored after the mock
try:
    V._cypher_sql = lambda q: (_ for _ in ()).throw(RuntimeError("db down"))
    V.CACHE_DIR = Path(tempfile.mkdtemp())          # no cached copy to fall back on
    r = V.verify_fact("cypher://card/x/Rare", ["anything"])
    ok(r["outcome"] == "unverified" and not r["fetched"],
       "a database that cannot be reached returns unverified: %s" % r["outcome"])
    ok(r["outcome"] != "contradicted", "…and never contradicted — silence is not evidence")
finally:
    V._cypher_sql = _orig

# Section 4 (privacy) lives in tests/test_cypher_privacy_live.py — it needs the
# real database or it proves nothing. See this module's header.

print("\n=== 5. READ-ONLY, AND NARROW ON PURPOSE ===")
try:
    _REAL_CYPHER_SQL("update public.owned_cards set serial_int=99;")
    ok(False, "a write should have been refused")
except AssertionError:
    ok(True, "the REAL _cypher_sql asserts the statement starts with select")
except KeyError:
    ok(False, "the replayer answered — section 5 must exercise the real guard")
for bad in ("cypher://", "cypher://card/only_one_arg", "cypher://listing/x/y",
            "cypher://serial/x/Rare/not_a_number", "cypher://card/a/b/c/d"):
    ok(V.resolve_cypher(bad) == "", "malformed refused: %-42s" % bad)
_fn = next(n for n in ast.walk(ast.parse((REPO / "research" / "verify.py").read_text()))
           if isinstance(n, ast.FunctionDef) and n.name == "resolve_cypher")
kinds = {n.value for n in ast.walk(_fn)
         if isinstance(n, ast.Constant) and n.value in ("card", "set", "serial")}
ok(kinds == {"card", "set", "serial"}, "exactly three kinds, no query language: %s" % sorted(kinds))

print("\n=== 6. A MISSING ROW IS A DOCUMENT, NOT A FAILURE ===")
t = V.fetch_text("cypher://serial/aj4_sb_varsity_red/GRAIL/9999")
ok("NOT MINTED" in t, "an unminted serial renders a document saying so")
r = V.verify_fact("cypher://serial/aj4_sb_varsity_red/GRAIL/9999", ["set_reward"])
ok(r["outcome"] == "contradicted",
   "…so a claim about it is CONTRADICTED (the db answered), not unverified")

print("\n=== 6b. THE CASING MAP ITSELF (pure; the LIVE half is separate) ===")
# The live half — that this map still matches the schema's two vocabularies —
# is tests/test_rarity_vocab_live.py. These three are pure functions and belong
# with the offline suite.
ok(V._rarity_for("owned_cards", "Rare") == "RARE", "Rare -> RARE for owned_cards")
ok(V._rarity_for("catalog_cards", "RARE") == "Rare", "RARE -> Rare for catalog_cards")
ok(V._rarity_for("owned_cards", "HOLY GRAIL") == "HOLY GRAIL", "the two top tiers are unchanged")

print("\n=== 7. ONE DISPATCH POINT ===")
tree = ast.parse((REPO / "research" / "verify.py").read_text())
ft = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "fetch_text")
ok(any(isinstance(n, ast.Call) and getattr(n.func, "id", "") == "resolve_cypher"
       for n in ast.walk(ft)), "fetch_text is the only caller of resolve_cypher")
calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
         and getattr(n.func, "id", "") == "resolve_cypher"]
ok(len(calls) == 1, "…and it is called exactly once in the module (%d)" % len(calls))

print("\n=== 8. NOTHING REACHED THE REAL LEDGER ===")
_scratch = V.LEDGER.read_text().splitlines() if V.LEDGER.exists() else []
ok(sum('"cypher_uri_malformed"' in l for l in _scratch) == 5
   and sum('"cypher_resolve_failed"' in l for l in _scratch) == 1,
   "the suite's 5 malformed + 1 resolve_failed rows landed in SCRATCH (%d rows)" % len(_scratch))
_n1 = _REAL_RESEARCH.read_text().count("\n") if _REAL_RESEARCH.exists() else 0
ok(_n1 == _REAL_N0, "the real ledger/research.jsonl did not grow (%d -> %d lines)" % (_REAL_N0, _n1))

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
