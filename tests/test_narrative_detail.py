#!/usr/bin/env python3.12
"""narrative_detail suite (H4 A+B).

Proves the GUARANTEE, not the happy path: a support fact CANNOT become a hook.
The repo's discipline is that a structural claim is proved by showing the shape
cannot be expressed — so the assertions here are about membership and about
what comes back from build(), never about a case happening not to occur.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from research import dossier as D
from research import selector as SEL

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

print("\n=== 1. the tag exists, and is SUPPORT-ONLY by membership ===")
ok("narrative_detail" in D.ALL_TAGS, "narrative_detail is in ALL_TAGS")
ok("narrative_detail" not in D.HOOKABLE_TAGS, "narrative_detail is NOT in HOOKABLE_TAGS")
ok("narrative_detail" in D.SUPPORT_TAGS, "narrative_detail is in the support bucket")
ok("spec" in D.SUPPORT_TAGS, "spec is still in the support bucket")
# the confusable neighbour: selector.NARRATIVE_HOOK_TAGS is the HOOK filter.
ok("narrative_detail" not in SEL.NARRATIVE_HOOK_TAGS,
   "narrative_detail is NOT in selector.NARRATIVE_HOOK_TAGS (the near-name-collision)")

print("\n=== 2. a narrative_detail fact cannot become a hook — via build() ===")
snap = {"name": "Air Jordan 3 Retro 'Test'", "release_year": 2020, "designer": None,
        "story_html": "<p>Designed by Tinker Hatfield, the model is built to the "
                      "original 1988 specs. A rubber outsole delivers grip.</p>"}
cat = {"silhouette": "Air Jordan 3", "colorway": "Black", "name": "Air Jordan 3",
       "year": 2020}
d = D.build("unit_test_shoe", cat, snap, {})
tags = {f["id"]: f["tag"] for f in d["facts"]}
ok("narrative_detail" in tags.values(), "the Hatfield sentence is tagged narrative_detail: %s" % tags)
nd = [i for i, t in tags.items() if t == "narrative_detail"]
ok(all(i not in d["hook_candidates"] for i in nd), "no narrative_detail id in hook_candidates")
ok(d["hook_candidates"] == [], "no hooks at all from this story")
ok(d["usable"] is False, "a narrative_detail fact does NOT make a dossier usable")

print("\n=== 3. support_facts carries both tags, ranked together ===")
sup = D.support_facts(d)
ok(any(f["tag"] == "narrative_detail" for f in sup), "narrative_detail reaches support_facts")
ok(all(f["tag"] in D.SUPPORT_TAGS for f in sup), "support_facts contains only support tags")
ok(all(f["tag"] not in D.HOOKABLE_TAGS for f in sup), "no support fact is hookable")
scores = [D.distinctiveness(f["text"]) for f in sup]
ok(scores == sorted(scores, reverse=True), "ranked by distinctiveness, descending: %s" % scores)

print("\n=== 4. the placement exclusion — an entity is not enough ===")
ok(D.is_narrative_detail("Kanye West tapped industry legends for the adidas 700 MNVN."),
   "person as actor -> narrative_detail")
ok(not D.is_narrative_detail("A rubberized Cactus Jack patch adorns the tongue."),
   "collaborator as a logo on a part of the shoe -> stays spec")
ok(D.is_narrative_detail("A '94' embroidered on the lateral heel is a nod to Supreme's founding year."),
   "placement PLUS provenance -> narrative_detail (the nod is the part worth telling)")
ok(not D.is_narrative_detail("The upper features an off-white leather base with black overlays."),
   "'off-white' the COLOUR does not match 'Off-White' the label (case-sensitivity)")
ok(D.is_narrative_detail("Off-White reworked the silhouette for a second Nike collection."),
   "'Off-White' the LABEL does match (capitalised) -> narrative_detail")
ok(not D.is_narrative_detail("A polyurethane midsole packs a visible Air-sole unit in the heel."),
   "pure materials copy -> stays spec")

print("\n=== 5. (B)(i) the exclusiv\\w+ word-boundary fix ===")
ok(D.tag_sentence("The colorway launched exclusively in Japan in 2001.") == "release_drama",
   "'exclusively' now reaches release_drama")
ok(D.tag_sentence("A limited exclusive release.") == "release_drama",
   "'exclusive' still reaches it")

print("\n=== 6. (B)(ii) patient / syndrome / disease -> cultural_moment ===")
AJ13 = ("Part of the 2015 Doernbecher collection, this Air Jordan 13 Retro 'DB' was "
        "designed by John Charles, an 11-year-old Crohn's Disease patient.")
AJ8 = ("Designed by Caden Lampert who battles with a life-threatening autoimmune disease "
       "known as Guillain-Barre syndrome, the vibrant sneaker features a Hyper Blue upper.")
ok(D.tag_sentence(AJ13) == "cultural_moment", "the AJ13 child designer is a HOOK, not a spec")
ok(D.tag_sentence(AJ8) == "cultural_moment", "the AJ8 child designer is a HOOK, not a spec")
# The ruled trade: \bdisease\b ONLY, never \bdiseas\w+. The plural is therefore
# not matched. Asserted so the narrowing is visible rather than folklore.
ok(D.tag_sentence("The coating resists diseases carried on the road.") != "cultural_moment",
   "'diseases' is NOT matched — \\bdisease\\b only, as ruled")

print("\n=== 7. the vocabulary is reviewable DATA, and the loader is loud ===")
for p in (D.NARRATIVE_ENTITIES, D.NARRATIVE_MARKERS):
    ok(p.exists(), "%s exists" % p.name)
    blob = json.loads(p.read_text())
    lists = {k: v for k, v in blob.items() if not k.startswith("_")}
    ok(bool(lists), "%s has at least one curated list" % p.name)
    ok(all(isinstance(v, list) and v and all(isinstance(t, str) and t.strip() for t in v)
           for v in lists.values()),
       "%s: every list is non-empty strings" % p.name)
v = D.narrative_vocab()
ok(v["counts"]["entities"] > 30, "entity vocabulary loaded: %s" % v["counts"])
_saved = D._VOCAB
D._VOCAB = None
try:
    D._load_list({"people": []}, "people", D.NARRATIVE_ENTITIES)
    ok(False, "an empty curated list raises")
except ValueError as e:
    ok(True, "an empty curated list raises ValueError: %s" % str(e)[:60])
D._VOCAB = _saved

print("\n=== 8. THE LIVE CORPUS — no narrative_detail fact is a hook anywhere ===")
bad, nd_total, files = [], 0, 0
for f in sorted((Path(__file__).resolve().parent.parent / "data" / "dossiers").glob("*.json")):
    dd = json.loads(f.read_text())
    files += 1
    hooks = set(dd.get("hook_candidates") or [])
    for fact in dd.get("facts", []):
        if fact["tag"] == "narrative_detail":
            nd_total += 1
            if fact["id"] in hooks:
                bad.append((dd["image_name"], fact["id"]))
ok(files > 0, "%d dossiers on disk" % files)
ok(not bad, "0 narrative_detail facts in hook_candidates across the corpus (found %d)" % len(bad))
print("      narrative_detail facts in the live corpus: %d" % nd_total)

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
