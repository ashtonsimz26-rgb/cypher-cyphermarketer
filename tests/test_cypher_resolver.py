#!/usr/bin/env python3.12
"""cypher:// — a first-party source. Reads the live DB; spends nothing.

The sources rule is UNCHANGED: a moment still needs a non-empty sources[] and
every term is still checked against a fetched document. What widened is what a
source may BE. The design claim under test is that nothing downstream is
special — outcome, found/missing, numeric matching and the cache are inherited
from the HTTP path rather than reimplemented beside it.

Section 4 is the one that is not about correctness: a serial's OWNER is a
private individual, and no rendered document may identify them.
"""
import ast, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from research import verify as V

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
_orig = V._cypher_sql
try:
    V._cypher_sql = lambda q: (_ for _ in ()).throw(RuntimeError("db down"))
    V.CACHE_DIR = Path(tempfile.mkdtemp())          # no cached copy to fall back on
    r = V.verify_fact("cypher://card/x/Rare", ["anything"])
    ok(r["outcome"] == "unverified" and not r["fetched"],
       "a database that cannot be reached returns unverified: %s" % r["outcome"])
    ok(r["outcome"] != "contradicted", "…and never contradicted — silence is not evidence")
finally:
    V._cypher_sql = _orig

print("\n=== 4. NO USER IS EVER IDENTIFIED ===")
t = V.fetch_text(SERIAL)
# the real owner of serial #1, fetched independently — it must NOT be in the doc
import daily_digest as DD
owner = DD._sql("select owner_id from public.owned_cards "
                "where image_name='aj4_sb_varsity_red' and serial_int=1;")[0]["owner_id"]
ok(owner not in t, "the owner_id of serial #1 is absent from the rendered document")
ok(not any(c in t for c in ("owner_id", "user_id", "@")),
   "no owner/user column or address appears at all")
src = (REPO / "research" / "verify.py").read_text()
tree = ast.parse(src)
fn = next(n for n in ast.walk(tree)
          if isinstance(n, ast.FunctionDef) and n.name == "resolve_cypher")
sql = " ".join(n.value for n in ast.walk(fn)
               if isinstance(n, ast.Constant) and isinstance(n.value, str))
ok("owner_id" not in sql and "user_id" not in sql,
   "no resolver SQL selects an owner column — it is never fetched, not merely unprinted")

print("\n=== 5. READ-ONLY, AND NARROW ON PURPOSE ===")
try:
    V._cypher_sql("update public.owned_cards set serial_int=99;")
    ok(False, "a write should have been refused")
except AssertionError:
    ok(True, "_cypher_sql asserts the statement starts with select")
for bad in ("cypher://", "cypher://card/only_one_arg", "cypher://listing/x/y",
            "cypher://serial/x/Rare/not_a_number", "cypher://card/a/b/c/d"):
    ok(V.resolve_cypher(bad) == "", "malformed refused: %-42s" % bad)
kinds = {n.value for n in ast.walk(fn)
         if isinstance(n, ast.Constant) and n.value in ("card", "set", "serial")}
ok(kinds == {"card", "set", "serial"}, "exactly three kinds, no query language: %s" % sorted(kinds))

print("\n=== 6. A MISSING ROW IS A DOCUMENT, NOT A FAILURE ===")
t = V.fetch_text("cypher://serial/aj4_sb_varsity_red/GRAIL/9999")
ok("NOT MINTED" in t, "an unminted serial renders a document saying so")
r = V.verify_fact("cypher://serial/aj4_sb_varsity_red/GRAIL/9999", ["set_reward"])
ok(r["outcome"] == "contradicted",
   "…so a claim about it is CONTRADICTED (the db answered), not unverified")

print("\n=== 7. ONE DISPATCH POINT ===")
ft = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "fetch_text")
ok(any(isinstance(n, ast.Call) and getattr(n.func, "id", "") == "resolve_cypher"
       for n in ast.walk(ft)), "fetch_text is the only caller of resolve_cypher")
calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
         and getattr(n.func, "id", "") == "resolve_cypher"]
ok(len(calls) == 1, "…and it is called exactly once in the module (%d)" % len(calls))

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
