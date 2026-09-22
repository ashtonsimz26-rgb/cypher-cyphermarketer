#!/usr/bin/env python3.12
"""The research.jsonl retraction covers EXACTLY the 368 resolver-test rows. Read-only.

★ INDEPENDENT OF THE TOOL THAT WROTE IT. research/retract_test_rows.py built the
retraction row; this suite re-derives the set with its OWN copy of the six
fingerprints, its OWN burst check and its OWN hashing, then requires the row to
match that set exactly — no more, no fewer. A test that imported the tool's
identify() would only prove the tool agrees with itself.

Scope is the lines BEFORE the retraction row. A genuine cypher_uri_malformed row
appended later is real and must NOT be retracted; it is out of scope here, not a
failure.
"""
import hashlib, json, shutil, sys, tempfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from research import ledger_read as LR  # noqa: E402

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

LEDGER = REPO / "ledger" / "research.jsonl"
lines = LEDGER.read_text(encoding="utf-8").splitlines()
parsed = [(i, json.loads(l)) for i, l in enumerate(lines, start=1)]
sha = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()

print("\n=== 1. exactly one retraction row ===")
ret = [(i, r) for i, r in parsed if r.get("event") == "retraction"]
ok(len(ret) == 1, "one retraction row (%d)" % len(ret))
if len(ret) != 1:
    print("\n%d FAILURE(S): %s" % (len(FAILS), FAILS)); sys.exit(1)
RL, R = ret[0]
scope = [(i, r) for i, r in parsed if i < RL]

print("\n=== 2. the set, re-derived independently ===")
FP = {("cypher_resolve_failed", "cypher://card/x/Rare", "RuntimeError: db down"),
      ("cypher_uri_malformed", "cypher://", "empty"),
      ("cypher_uri_malformed", "cypher://card/only_one_arg", "unknown kind 'card' or wrong arity (1)"),
      ("cypher_uri_malformed", "cypher://listing/x/y", "unknown kind 'listing' or wrong arity (2)"),
      ("cypher_uri_malformed", "cypher://serial/x/Rare/not_a_number", "serial is not a number"),
      ("cypher_uri_malformed", "cypher://card/a/b/c/d", "unknown kind 'card' or wrong arity (4)")}
EV = {e for e, _, _ in FP}
of_event = [(i, r) for i, r in scope if r.get("event") in EV]
mine = [(i, r) for i, r in of_event if (r["event"], r.get("uri"), r.get("reason")) in FP]
ok(len(of_event) == len(mine), "every %s row before the retraction matches a fingerprint "
   "(%d of %d)" % (sorted(EV), len(mine), len(of_event)))
ok(len(mine) == 368, "the re-derived set is 368 rows (%d)" % len(mine))
by = {}
for _, r in mine: by[r["event"]] = by.get(r["event"], 0) + 1
ok(by == {"cypher_uri_malformed": 305, "cypher_resolve_failed": 63},
   "305 malformed + 63 resolve_failed: %s" % by)

# the bare cypher:// rows: re-check the ONLY evidence they are test rows
five = {u for _, u, _ in FP} - {"cypher://"}
t = lambda r: datetime.fromisoformat(r["ts"])
bare_ok = bare_n = 0
for i, r in mine:
    if r.get("uri") != "cypher://":
        continue
    bare_n += 1
    near = {x.get("uri") for _, x in mine if abs((t(x) - t(r)).total_seconds()) < 30}
    bare_ok += five <= near
ok(bare_n == 61 and bare_ok == 61,
   "all %d bare cypher:// rows sit within 30 s of all five test-only URIs (%d)" % (bare_n, bare_ok))

print("\n=== 3. the retraction row lists EXACTLY that set, with correct hashes ===")
listed = {x["line"]: x["sha256"] for x in R.get("rows", [])}
ok(len(listed) == len(R.get("rows", [])) == 368, "368 distinct lines listed (%d)" % len(listed))
ok(set(listed) == {i for i, _ in mine}, "the listed lines ARE the re-derived set — no more, no fewer")
ok(all(listed[i] == sha(lines[i - 1]) for i in listed), "every listed hash matches its line's text")
ok(R.get("count") == 368 and R.get("by_event") == by, "count and per-event counts recorded")
ok(R.get("first_ts") == mine[0][1]["ts"] and R.get("last_ts") == mine[-1][1]["ts"], "time range recorded")
ok(all(R.get(k) for k in ("reason", "ruling", "rule")), "reason, ruling and rule recorded")
bare_txt = (R.get("evidence") or {}).get("bare_scheme_rows", "")
ok("COULD come from production" in bare_txt and "ONLY evidence" in bare_txt and "61" in bare_txt,
   "the bare cypher:// judgement call is recorded AS a judgement, with its basis")

print("\n=== 4. the shared reader skips exactly those rows ===")
live, every = LR.rows(), LR.rows(include_retracted=True)
ok(len(every) == len(lines), "rows(include_retracted=True) is the whole ledger (%d)" % len(every))
ok(len(every) - len(live) == 369, "rows() drops the 368 + the retraction row itself (%d)"
   % (len(every) - len(live)))
fp_live = sum((r.get("event"), r.get("uri"), r.get("reason")) in FP for r in live)
fp_after = sum((r.get("event"), r.get("uri"), r.get("reason")) in FP for i, r in parsed if i > RL)
ok(fp_live == fp_after, "fingerprint rows in the live view = those written AFTER the retraction "
   "(%d = %d) — every retracted one is gone" % (fp_live, fp_after))
ok(sum(r.get("event") == "goat_lookup" for r in live)
   == sum(r.get("event") == "goat_lookup" for _, r in parsed), "every real row is still in the live view")

print("\n=== 5. a rewritten ledger is REFUSED, never guessed at ===")
tmp = Path(tempfile.mkdtemp()) / "research.jsonl"; shutil.copy2(LEDGER, tmp)
tl = tmp.read_text(encoding="utf-8").splitlines()
first = min(listed); tl[first - 1] = tl[first - 1].replace("cypher://", "cypher:///")
tmp.write_text("\n".join(tl) + "\n", encoding="utf-8")
try:
    LR.retracted_lines(tmp); ok(False, "an edited retracted line should raise")
except LR.RetractionMismatch:
    ok(True, "editing one retracted line makes the reader raise RetractionMismatch")

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
