#!/usr/bin/env python3.12
"""R1 — fact-level sensitivity suite.

The claim is UNREACHABILITY, so the assertions are corpus-wide and structural:
not "the flagged fact did not appear this time" but "no flagged fact can appear
in any of the three surfaces, for any dossier on disk".
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from research import dossier as D

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

DOSSIERS = Path(__file__).resolve().parent.parent / "data" / "dossiers"

print("\n=== 1. the filter is POSITIVE ===")
ok(D.WRITER_REACHABLE_SENSITIVITIES == frozenset({"none"}),
   "WRITER_REACHABLE_SENSITIVITIES == {'none'}")
ok(D.writer_reachable({"sensitivity": "none"}), "'none' is reachable")
ok(D.writer_reachable({}), "a fact with no sensitivity key defaults reachable")
ok(not D.writer_reachable({"sensitivity": "medical_detail"}), "medical_detail is NOT reachable")
# the point of a positive filter: a value nobody anticipated is excluded too
ok(not D.writer_reachable({"sensitivity": "some_value_nobody_anticipated"}),
   "an UNANTICIPATED value is excluded by construction, not by blocklist")

print("\n=== 2. THE CORPUS — no flagged fact reaches any of the three surfaces ===")
files = sorted(DOSSIERS.glob("*.json"))
flagged_total, leaks, missing_key = 0, [], 0
for f in files:
    d = json.loads(f.read_text())
    reach = {x["id"] for x in D.hook_facts(d)} | {x["id"] for x in D.support_facts(d)} \
            | {x["id"] for x in D.lineage_facts(d)}
    for fact in d["facts"]:
        if "sensitivity" not in fact:
            missing_key += 1
        if fact.get("sensitivity", "none") != "none":
            flagged_total += 1
            if fact["id"] in reach:
                leaks.append((d["image_name"], fact["id"], fact["tag"]))
ok(len(files) > 0, "%d dossiers on disk" % len(files))
ok(missing_key == 0, "every fact carries a sensitivity key (%d missing)" % missing_key)
ok(flagged_total > 0, "%d flagged fact(s) exist to test against" % flagged_total)
ok(not leaks, "0 flagged facts in hook_facts/support_facts/lineage_facts (leaks: %s)" % leaks)

print("\n=== 3. the named fact — aj13's medication count ===")
d13 = json.loads((DOSSIERS / "aj13_doernbecher.json").read_text())
med = [f for f in d13["facts"] if f.get("sensitivity") == "medical_detail"]
ok(len(med) == 1, "exactly one medical_detail fact on aj13_doernbecher")
if med:
    ok("pills" in med[0]["text"], "it is the medication fact: %s..." % med[0]["text"][:58])
    ids = {x["id"] for x in D.hook_facts(d13)} | {x["id"] for x in D.support_facts(d13)} \
          | {x["id"] for x in D.lineage_facts(d13)}
    ok(med[0]["id"] not in ids, "it reaches NONE of hook/support/lineage")
    ok(med[0] in d13["facts"], "it is STILL IN THE DOSSIER as a record — reach removed, not the record")
    print("      aj13 support bucket now: %s" % [f["id"] for f in D.support_facts(d13)])

print("\n=== 4. filtered BEFORE ranking, so the bucket does not silently shrink ===")
# the flagged fact is by construction the highest-scoring one (numbers are
# double-weighted), so a filter applied after ranking would cost a slot.
spec_all = [f for f in d13["facts"] if f.get("tag") == "spec"]
ok(len(D.support_facts(d13)) == min(D.MAX_SUPPORT_FACTS,
                                    len([f for f in spec_all if D.writer_reachable(f)])),
   "support bucket is full to the cap from REACHABLE facts only")

print("\n=== 5. a flagged fact can never be a hook CANDIDATE — via build() ===")
saved = D._FACT_SENS
D._FACT_SENS = {"unit_test_shoe": {"Nike banned the shoe in 1985.": "medical_detail"}}
snap = {"name": "Air Jordan 1 Retro 'Test'", "release_year": 2020, "designer": None,
        "story_html": "<p>Nike banned the shoe in 1985. A rubber outsole delivers grip.</p>"}
cat = {"silhouette": "Air Jordan 1", "colorway": "Black", "name": "Air Jordan 1", "year": 2020}
d = D.build("unit_test_shoe", cat, snap, {})
banned = [f for f in d["facts"] if "banned" in f["text"]][0]
ok(banned["tag"] == "release_drama", "the sentence IS a hookable tag (%s)" % banned["tag"])
ok(banned["sensitivity"] == "medical_detail", "and it is flagged")
ok(banned["id"] not in d["hook_candidates"], "yet it is NOT a hook candidate")
ok(d["usable"] is False, "and the dossier is not usable on it")
D._FACT_SENS = saved

print("\n=== 6. the loader is LOUD — failing open is the danger ===")
def raises(entry, why):
    D._FACT_SENS = None
    blob = json.dumps({"facts": [entry]})
    orig = D.FACT_SENSITIVITY.read_text()
    try:
        D.FACT_SENSITIVITY.write_text(blob)
        D.fact_sensitivity()
        ok(False, why)
    except ValueError as e:
        ok(True, "%s -> ValueError: %s" % (why, str(e)[:64]))
    finally:
        D.FACT_SENSITIVITY.write_text(orig)
        D._FACT_SENS = None
base = {"image_name": "x", "sensitivity": "medical_detail", "text": "t", "approved_by": "ashton"}
raises({**base, "approved_by": "claude"}, "an entry the AGENT approved")
raises({**base, "approved_by": ""}, "an entry with no approver")
raises({**base, "sensitivity": "none"}, "a flag set to a REACHABLE sensitivity (a no-op)")
D.fact_sensitivity()          # reload the real file

print("\n=== 7. flags are keyed by TEXT, not by positional fact id ===")
blob = json.loads(D.FACT_SENSITIVITY.read_text())
ok(all("text" in e for e in blob["facts"]), "every entry carries the fact text")
ok(all("id" not in e and "fact_id" not in e for e in blob["facts"]),
   "no entry is keyed by a positional id (ids shift when the tagger changes)")
ok(all(e.get("approved_by") == D.SENSITIVITY_APPROVER for e in blob["facts"]),
   "every entry is approved by %s" % D.SENSITIVITY_APPROVER)

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
