#!/usr/bin/env python3.12
"""cypher:// — BOTH RARITY VOCABULARIES RESOLVE. Reads the live DB; spends nothing.

catalog_cards uses the sneaker_rarity ENUM (mixed case); owned_cards is TEXT
under a CHECK constraint (UPPER). They agree on GRAIL and HOLY GRAIL and differ
on the other four, so testing a GRAIL proves nothing about the rest.

★ THIS SUITE CANNOT BE MOVED OFFLINE EITHER. What it checks is that the code's
casing map still matches the LIVE schema's two vocabularies. A fixture would
freeze exactly the thing at risk of drifting — it would pass forever, including
on the day someone changes the enum. Skips rather than passes when the DB is
unreachable.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _live import require_db
require_db()

from research import verify as V
import daily_digest as DD

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

print("\n=== BOTH RARITY VOCABULARIES RESOLVE (live) ===")
row = DD._sql("select image_name, rarity, serial_int from public.owned_cards "
              "where rarity='LEGENDARY' and serial_int is not null limit 1;")
ok(bool(row), "a minted LEGENDARY exists to test against (else this proves nothing)")
if row:
    r0 = row[0]
    for spelling in ("Legendary", "LEGENDARY"):
        t = V.fetch_text("cypher://serial/%s/%s/%s"
                         % (r0["image_name"], spelling, r0["serial_int"]))
        ok("CYPHER SERIAL" in t and "NOT MINTED" not in t,
           "a minted LEGENDARY resolves as %-10s (not a false NOT MINTED)" % spelling)
        ok("serial_cap" in t, "…and its serial_cap joins (catalog casing on serial_caps)")

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
