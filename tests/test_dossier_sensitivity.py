#!/usr/bin/env python3.12
"""R2 — dossier-level human_copy_required suite.

The claim is that a flagged dossier cannot reach a generator through ANY path.
The digest's pool is built straight from Supabase and never calls
selector.eligibility(), so "the selector refuses it" is not the same claim as
"it cannot be proposed" — both are asserted separately, on purpose.
"""
import ast, json, sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from research import dossier as D
from research import selector as SEL

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

# ★ PINNED ON PURPOSE. This list is the reviewed set; adding a flag must be a
# deliberate edit here as well as in the curated file, so no flag appears
# without someone changing the suite that asserts it.
FLAGGED = ("aj8_doernbecher", "aj13_doernbecher",
           "nike_kobe_6_protro_mambacita_sweet_sixteen")

print("\n=== 1. the filter is POSITIVE, same position as PROPOSABLE_SENSITIVITIES ===")
from research import moments as MOM
ok(D.PROPOSABLE_DOSSIER_SENSITIVITIES == frozenset({"none"}),
   "PROPOSABLE_DOSSIER_SENSITIVITIES == {'none'}")
ok(MOM.PROPOSABLE_SENSITIVITIES == frozenset({"none"}),
   "mirrors moments.PROPOSABLE_SENSITIVITIES == {'none'}")
ok(D.dossier_proposable("a_shoe_with_no_entry_at_all"),
   "an unflagged dossier is proposable")
for n in FLAGGED:
    ok(not D.dossier_proposable(n), "%s is NOT proposable" % n)

print("\n=== 2. an UNANTICIPATED sensitivity is excluded by construction ===")
saved = D._DOSSIER_SENS
D._DOSSIER_SENS = dict(saved or {})
D._DOSSIER_SENS["synthetic_shoe"] = {"sensitivity": "a_value_nobody_anticipated",
                                     "approved_by": "ashton"}
ok(not D.dossier_proposable("synthetic_shoe"),
   "a value no branch was written for is excluded, not defaulted in")
D._DOSSIER_SENS = saved

print("\n=== 3. THE DIGEST PATH — build_one gates before anything else ===")
src = (ROOT / "daily_digest.py").read_text()
tree = ast.parse(src)
fn = next(n for n in ast.walk(tree)
          if isinstance(n, ast.FunctionDef) and n.name == "build_one")
body = [n for n in fn.body if not isinstance(n, ast.Expr)]      # skip the docstring
first = body[0]
ok(isinstance(first, ast.If) and "dossier_proposable" in ast.unparse(first.test),
   "the FIRST statement in build_one is the dossier_proposable gate")
ok(ast.unparse(first).count("return None") >= 1, "it returns None when not proposable")
# and it must come before the catalog fetch, which is where spend begins
idx_gate = src.index("dossier_proposable(cand[\"image_name\"])")
idx_fetch = src.index("row = CR.fetch_card(cand[\"image_name\"]")
ok(idx_gate < idx_fetch, "the gate precedes CR.fetch_card — no DB round trip, no spend")
ok("candidates(" in src and "eligibility" not in src.split("def candidates")[1][:1200],
   "candidates() does NOT go through selector.eligibility — hence the separate gate")

print("\n=== 4. THE SELECTOR PATH — every lane, not just the general one ===")
sel_src = (ROOT / "research/selector.py").read_text()
for lane, anchor in (("eligibility", "def eligibility"),
                     ("_anniversary_pass", "def _anniversary_pass"),
                     ("_moment_lane", "def _moment_lane")):
    seg = sel_src.split(anchor, 1)[1].split("\ndef ", 1)[0]
    ok("dossier_proposable" in seg, "%s applies the filter" % lane)
rd = SEL.load_release_dates()
for n in FLAGGED:
    d = SEL.load_dossier(n)
    el = SEL.eligibility(n, date(2026, 9, 12), dossier=d, day_has_moment=True,
                         release_dates=rd)
    ok(el is None, "%s is ineligible even on a moment day with a usable dossier "
                   "(usable=%s)" % (n, bool(d and d.get("usable"))))

print("\n=== 5. a flagged dossier never comes back from select(), on any day ===")
pool = sorted(p.stem for p in (ROOT / "data/dossiers").glob("*.json"))
hits = []
for i in range(0, 366, 7):                       # sampled year, all lanes live
    from datetime import timedelta
    day = date(2026, 1, 1) + timedelta(days=i)
    c = SEL.select(day, pool, release_dates=rd)
    if c and c.get("image_name") in FLAGGED:
        hits.append((day.isoformat(), c["image_name"], c["lane"]))
ok(not hits, "0 selections of a flagged dossier across 53 sampled days (%s)" % hits)

print("\n=== 6. approved human copy RAISES rather than falling through ===")
saved = D._DOSSIER_SENS
D._DOSSIER_SENS = dict(saved or {})
D._DOSSIER_SENS["aj13_doernbecher"] = {"sensitivity": "human_copy_required",
                                       "approved_by": "ashton",
                                       "human_copy": "John Charles was 11 when he designed this.",
                                       "human_copy_approved_by": "ashton"}
try:
    D.dossier_proposable("aj13_doernbecher")
    ok(False, "approved copy with no shipping lane raises")
except NotImplementedError as e:
    ok(True, "raises NotImplementedError rather than handing the shoe to the writer")
    ok("NOT BUILT" in str(e), "the message says the lane is not built")
D._DOSSIER_SENS = saved

print("\n=== 7. the curated file is human-approved data ===")
blob = json.loads(D.DOSSIER_SENSITIVITY.read_text())
ents = {k: v for k, v in blob["dossiers"].items() if not k.startswith("_")}
ok(set(ents) == set(FLAGGED), "the flagged set is exactly the reviewed set (%d): %s"
   % (len(ents), sorted(ents)))
ok(all(e["approved_by"] == D.SENSITIVITY_APPROVER for e in ents.values()),
   "every entry approved by %s" % D.SENSITIVITY_APPROVER)
ok(all(e.get("human_copy") is None for e in ents.values()),
   "no human copy exists yet — so none of these shoes post, which is correct")
ok(all(len(e.get("_why", "")) > 40 for e in ents.values()), "every entry carries a reason")
D._DOSSIER_SENS = None
orig = D.DOSSIER_SENSITIVITY.read_text()
try:
    D.DOSSIER_SENSITIVITY.write_text(json.dumps(
        {"dossiers": {"x": {"sensitivity": "human_copy_required", "approved_by": "claude"}}}))
    D.dossier_sensitivity()
    ok(False, "an entry the AGENT approved raises")
except ValueError as e:
    ok(True, "an entry the AGENT approved raises ValueError: %s" % str(e)[:60])
finally:
    D.DOSSIER_SENSITIVITY.write_text(orig)
    D._DOSSIER_SENS = None
    D.dossier_sensitivity()

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
