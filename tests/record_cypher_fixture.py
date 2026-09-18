#!/usr/bin/env python3.12
"""Record every cypher:// SQL the OFFLINE resolver suite needs, once, from live.

Run this when the resolver's queries change:  python3.12 tests/record_cypher_fixture.py

★ The fixture is a RECORDING, never hand-written. A hand-written fixture is an
assumption about what the database returns, and the suite would then test the
assumption rather than the renderer.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from research import verify as V

FIX = Path(__file__).resolve().parent / "fixtures" / "cypher_sql.json"
rec, orig = {}, V._cypher_sql


def taping(q: str):
    rows = orig(q)
    rec[" ".join(q.split())] = rows
    return rows


# ★ The URL cache must be bypassed or fetch_text answers from disk and the
# recording captures nothing. state/url_cache is exactly the thing that made the
# first recording return one query.
import tempfile
V.CACHE_DIR = Path(tempfile.mkdtemp())
V._cypher_sql = taping
for uri in ("cypher://card/aj4_sb_varsity_red/GRAIL",
            "cypher://set/Nike%20x%20Jordan%204%20SB",
            "cypher://serial/aj4_sb_varsity_red/GRAIL/1",
            "cypher://serial/aj4_sb_varsity_red/GRAIL/9999"):
    V.fetch_text(uri)
V._cypher_sql = orig
FIX.parent.mkdir(parents=True, exist_ok=True)
FIX.write_text(json.dumps(rec, indent=1, sort_keys=True, default=str), encoding="utf-8")
print("recorded %d queries -> %s" % (len(rec), FIX))
