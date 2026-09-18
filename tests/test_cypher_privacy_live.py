#!/usr/bin/env python3.12
"""cypher:// — NO USER IS EVER IDENTIFIED. Reads the live DB; spends nothing.

★ THIS SUITE CANNOT BE MOVED OFFLINE, and that is the point. Its claim is that
the REAL owner of a REAL serial does not appear in the REAL rendered document.
Against a fixture it would assert that a fake owner id is absent from a document
rendered from that same fixture — true by construction, and therefore a check
that cannot fail. That is the exact shape contracts.py catalogues.

So it stays live, and when the database is unreachable it SKIPS rather than
passing. A privacy check that quietly passed because nothing ran is worse than
no privacy check.
"""
import ast, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _live import require_db
require_db()

from research import verify as V

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

REPO = Path(__file__).resolve().parent.parent
SERIAL = "cypher://serial/aj4_sb_varsity_red/GRAIL/1"

print("\n=== NO USER IS EVER IDENTIFIED (live) ===")
t = V.fetch_text(SERIAL)
import daily_digest as DD
rows = DD._sql("select owner_id from public.owned_cards "
               "where image_name='aj4_sb_varsity_red' and serial_int=1;")
ok(bool(rows), "the fixture serial exists in the live table (else this proves nothing)")
if rows:
    owner = rows[0]["owner_id"]
    ok(owner not in t, "the owner_id of serial #1 is absent from the rendered document")
ok(not any(c in t for c in ("owner_id", "user_id", "@")),
   "no owner/user column or address appears at all")

# Structural half — kept HERE beside the live half so the two cannot drift apart.
src = (REPO / "research" / "verify.py").read_text()
fn = next(n for n in ast.walk(ast.parse(src))
          if isinstance(n, ast.FunctionDef) and n.name == "resolve_cypher")
sql = " ".join(n.value for n in ast.walk(fn)
               if isinstance(n, ast.Constant) and isinstance(n.value, str))
ok("owner_id" not in sql and "user_id" not in sql,
   "no resolver SQL selects an owner column — never fetched, not merely unprinted")

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
