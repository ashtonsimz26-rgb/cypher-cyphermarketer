#!/usr/bin/env python3.12
"""E5 — one brief, two outputs. Zero LLM, zero network, zero spend.

Before E5 detect_hook picked a fact for the SCENE and the writer picked its own
for the LEAD, and nothing made those the same. The image could be about a collab
while the sentence was about a stash pocket: both true, both about the shoe, not
about the same thing.

The fallback is where this quietly breaks, so section 3 is the long one.
"""
import ast, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from research import story as ST
import backdrop as BD, daily_digest as DD

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

REPO = Path(__file__).resolve().parent.parent
DOSS = {"facts": [
    {"id": "f1", "tag": "silhouette_lineage", "text": "Built on the Dunk, designed by Peter Moore."},
    {"id": "f2", "tag": "collab_origin", "text": "A Supreme skate shop collaboration on Lafayette Street."},
    {"id": "f3", "tag": "cultural_moment", "text": "Made to mark the Chinese New Year."},
]}

print("\n=== 1. THE WRITER'S FACT DECIDES THE SCENE ===")
b = ST.brief(DOSS, "f3", lead="Marked the Chinese New Year with a candy box.")
ok(b["scene_key"] == "lunar_new_year" and b["source"] == "writer",
   "naming f3 gives the lunar scene, not the collab one: %s" % b["scene_key"])
b2 = ST.brief(DOSS, "f2", lead="A Supreme shop on Lafayette.")
# ★ UPDATED 2026-09-17: f2 now resolves on `skate`, its own activity word, not
# on `supreme`. The claim under test is unchanged — the WRITER'S fact decides
# the scene — but the brand no longer supplies the answer.
ok(b2["scene_key"] == "skate_basement" and b2["source"] == "writer",
   "naming f2 gives f2's scene, chosen by its activity not its brand: %s" % b2["scene_key"])
ok(b["scene_key"] != b2["scene_key"],
   "…so the SAME dossier yields different scenes depending on what was written")

print("\n=== 2. THE FACT NEVER REACHES THE PROMPT — NOW STRUCTURALLY ===")
btree = ast.parse((REPO / "backdrop.py").read_text())
for fname in ("scene_for", "build_prompt", "prompt_source"):
    fn = next(n for n in ast.walk(btree) if isinstance(n, ast.FunctionDef) and n.name == fname)
    args = [a.arg for a in fn.args.args] + [a.arg for a in fn.args.kwonlyargs]
    ok(not ({"hook_text", "fact", "fact_text", "dossier", "text"} & set(args)),
       "backdrop.%-13s(%s)" % (fname, ", ".join(args)))
ok(not any(isinstance(n, ast.FunctionDef) and n.name == "story_key" for n in ast.walk(btree)),
   "story_key is gone from backdrop — the one function that read fact text")
p = BD.build_prompt({"category": "Lifestyle", "year": 2005}, b2["scene_key"])
ok(not [t for t in BD.BRAND_TOKENS if t in p.lower().split("absolute constraints:")[0]],
   "a Supreme fact still yields a prompt with no brand token")

print("\n=== 3. THE FALLBACK IS LOUD, AND FIRES ON EVERY BAD INPUT ===")
for label, fid in (("no fact_id", None), ("bogus id", "f_nope"),
                   ("an id with no scene key", "f1")):
    fb = ST.brief(DOSS, fid, lead="x")
    ok(fb["fallback_fired"] and fb["source"] == "fallback",
       "%-24s -> fallback, key=%s" % (label, fb["scene_key"]))
empty = ST.brief({"facts": []}, "f1", lead="x")
ok(empty["source"] == "none" and empty["scene_key"] is None,
   "a dossier with no hookable fact yields source=none, not a crash")
ok(ST.brief(None, None)["source"] == "none", "no dossier at all is handled")

dsrc = (REPO / "daily_digest.py").read_text()
dtree = ast.parse(dsrc)
bo = next(n for n in ast.walk(dtree) if isinstance(n, ast.FunctionDef) and n.name == "build_one")
events = {n.value for n in ast.walk(bo) if isinstance(n, ast.Constant)
          and isinstance(n.value, str) and n.value == "brief_divergence"}
ok(events == {"brief_divergence"}, "build_one writes a brief_divergence row")
ok("fallback_fired" in ast.dump(bo) and "shared_tokens" in ast.dump(bo),
   "…carrying both the fallback flag and the token overlap")
ok("fact_id_claimed" in ast.dump(bo),
   "…and what the model CLAIMED, so an invalid id is visible, not just absent")

print("\n=== 4. THE DIVERGENCE HEURISTIC IS A MEASURE, NOT A GATE ===")
hi = ST.shared_tokens("Marked the Chinese New Year with a candy box",
                      "Made to mark the Chinese New Year.")
lo = ST.shared_tokens("A clean silhouette for the summer.",
                      "Made to mark the Chinese New Year.")
ok(hi >= 2 and lo == 0, "overlap separates an on-topic lead (%d) from an off-topic one (%d)" % (hi, lo))
ok(ST.shared_tokens("the and of a", "the and of a") == 0,
   "stopwords do not count as overlap")
returns = [n for n in ast.walk(bo) if isinstance(n, ast.Return)]
srcseg = dsrc[dsrc.index("_brief = ST.brief"):dsrc.index("_brief = ST.brief") + 1400]
ok("return None" not in srcseg,
   "nothing between resolving the brief and using it returns None — divergence "
   "is LOGGED, never a reason to drop the post")

print("\n=== 5. NO SPEND BEFORE THE BRIEF ===")
order = dsrc.index("_brief = ST.brief"), dsrc.index("BD.generate(")
ok(order[0] < order[1], "the brief is resolved BEFORE the only $0.04 call")
ok(dsrc.index("ok_lead") < order[0],
   "…and the lead gate runs before the brief, so a failed draft costs $0.00")

print("\n=== 6. THE CONTRACT EDIT IS SURGICAL ===")
from research import writer as W
c = W.FORMAT_CONTRACT
ok('"fact_id": "<id>"' in c, "the response shape names fact_id")
ok("is not a target, it is a ceiling" in c, "the length ceiling is untouched")
ok(W.LEAD_BUDGET == 202, "…and still 202")
ok("say                      not" in c, "the REGISTER table is untouched")
ok("THE ONE TEST THAT MATTERS" in c, "the swap test is untouched")
ok('{"lead": null, "body": null, "fact_id": null}' in c,
   "the silence case names fact_id too — otherwise the shape differs on the "
   "one path that matters most")

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
