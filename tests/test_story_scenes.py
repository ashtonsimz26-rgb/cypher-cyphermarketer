#!/usr/bin/env python3.12
"""E2 + set_completion suite. Zero LLM, zero network, zero spend.

The claim under test is narrow and structural: THE PROMPT IS ASSEMBLED ONLY FROM
STRINGS IN backdrop.py. A hook fact chooses a KEY; the key selects a stem written
by hand in advance. That is why a Supreme shoe cannot put a box logo on a wall —
the word never reaches the model. Tests 3 and 4 prove it two ways: by asserting
no stem contains a proper noun, and by feeding brand-soaked facts through and
scanning the finished prompt.
"""
import ast, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import backdrop as BD, editorial, rails
from research import story as ST

def scene_of(row, dossier, fact_text=None):
    """E5: the caller resolves a KEY, then backdrop renders it. backdrop
    no longer has a parameter fact text could arrive in — see section 8."""
    key = ST.key_for_text(fact_text) if fact_text else \
        ST.brief(dossier, None)["scene_key"]
    return BD.scene_for(row, key)

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

REPO = Path(__file__).resolve().parent.parent

class Spend(AssertionError): pass
BD.generate = lambda *a, **k: (_ for _ in ()).throw(Spend("generate CALLED — $0.04"))

print("\n=== 1. THE STORY DECIDES; CATEGORY IS THE FALLBACK ===")
doss = {"facts": [{"tag": "cultural_moment",
                   "text": "Nike teams up with CLOT to celebrate the Chinese New Year"}]}
row = {"category": "Lifestyle", "year": 2009}
scene, source, why = scene_of(row, doss)
ok(source == "story:lunar_new_year", "a Chinese New Year fact picks the lunar scene: %s" % source)
ok(scene != BD.SCENES["Lifestyle"] + BD._era(row), "…and it is NOT the category scene")
ok(why == "", "backdrop returns NO fact text any more — it never saw one")

scene, source, _ = scene_of({"category": "Skateboarding", "year": 2015}, {"facts": []})
ok(source == "category:Skateboarding", "no story signal falls back to category: %s" % source)
scene, source, _ = scene_of({"category": "Nonsense", "year": 2015}, None)
ok(source == "default", "an unknown category falls back to the default: %s" % source)

print("\n=== 2. ONLY HOOK FACTS CHOOSE THE SCENE ===")
support = {"facts": [{"tag": "narrative_detail",
                      "text": "The box was a Chinese Candy Box packaging set"},
                     {"tag": "spec", "text": "Red and black leather upper, Tokyo-made"}]}
_, source, _ = scene_of({"category": "Lifestyle", "year": 2009}, support)
ok(source == "category:Lifestyle",
   "support and spec facts are IGNORED — they describe materials, not the story")

print("\n=== 3. NO STEM CAN CARRY A BRAND — CHECKED AGAINST THE SOURCE ===")
ok(all(not any(t in stem.lower() for t in BD.BRAND_TOKENS) for stem in BD.STORY_SCENES.values()),
   "no STORY_SCENES stem contains a brand token")
ok(all(not any(t in stem.lower() for t in BD.BRAND_TOKENS) for stem in BD.SCENES.values()),
   "no category SCENES stem contains a brand token either")
capitalised = {k: re.findall(r"(?<![.!?] )(?<!^)\b[A-Z][a-z]{2,}", v)
               for k, v in BD.STORY_SCENES.items()}
ok(not any(capitalised.values()),
   "no stem contains a proper noun at all: %s" % {k: v for k, v in capitalised.items() if v})

print("\n=== 4. BRAND-SOAKED FACTS CANNOT REACH THE PROMPT ===")
nasty = [
    ("Supreme's skate shop on Lafayette Street", "downtown_ny_2000s"),
    ("The Off-White x Nike collaboration for Paris fashion week", "atelier_night"),
    ("A Travis Scott release that was banned by the league", "locker_tunnel"),
    ("Grateful Dead bears on a psychedelic tour", "psychedelic_venue"),
]
for text, expect in nasty:
    d = {"facts": [{"tag": "collab_origin", "text": text}]}
    _, source, _ = BD.scene_for({"category": "Lifestyle", "year": 2018}, ST.key_for_text(text))
    p = BD.build_prompt({"category": "Lifestyle", "year": 2018}, ST.key_for_text(text))
    scene_part = p.lower().split("absolute constraints:")[0]
    leaked = [t for t in BD.BRAND_TOKENS if t in scene_part]
    ok(source == "story:%s" % expect and not leaked,
       "%-46s -> %-28s leaked=%s" % (text[:44], source, leaked or "none"))

print("\n=== 5. THE GUARD ITSELF WORKS, AND THE FALLBACK IS CLEAN ===")
try:
    BD.assert_no_brand("a street with a Nike store. " + BD.NEGATIVE_CONSTRAINTS)
    ok(False, "assert_no_brand should have raised")
except BD.BrandLeak as e:
    ok("nike" in str(e), "assert_no_brand raises BrandLeak naming the token")
ok(BD.assert_no_brand(BD.build_prompt({"category": "Lifestyle", "year": 2015}, None)) is None,
   "NEGATIVE_CONSTRAINTS saying 'no swooshes' is not itself a leak")

print("\n=== 6. NEGATIVE_CONSTRAINTS IS STILL STRUCTURAL ===")
src = (REPO / "backdrop.py").read_text()
tree = ast.parse(src)
bp = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "build_prompt")
ok("NEGATIVE_CONSTRAINTS" in ast.dump(bp),
   "build_prompt concatenates NEGATIVE_CONSTRAINTS itself, not the caller")
for d in (None, {"facts": []}, {"facts": [{"tag": "collab_origin", "text": "Supreme"}]}):
    p = BD.build_prompt({"category": "Lifestyle", "year": 2015}, ST.brief(d, None)["scene_key"])
    ok(p.endswith(BD.NEGATIVE_CONSTRAINTS), "every path ends in the constraints block")

print("\n=== 6b. backdrop HAS NO PARAMETER A FACT COULD ARRIVE IN (E5) ===")
# ★ The property that outlives the coherence fix. Asserted by AST, the same way
# the set_completion branch is asserted never to touch `frag`.
btree = ast.parse((REPO / "backdrop.py").read_text())
for fname in ("scene_for", "build_prompt", "prompt_source"):
    fn = next(n for n in ast.walk(btree) if isinstance(n, ast.FunctionDef) and n.name == fname)
    args = [a.arg for a in fn.args.args] + [a.arg for a in fn.args.kwonlyargs]
    bad = [a for a in args if a in ("hook_text", "fact", "fact_text", "dossier", "text")]
    ok(not bad, "backdrop.%-13s takes %s — no fact/text/dossier parameter" % (fname, args))
ok(not any(isinstance(n, ast.FunctionDef) and n.name == "story_key" for n in ast.walk(btree)),
   "backdrop no longer defines story_key — it moved to research/story.py")
ok(not any(isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant)
           and n.slice.value == "facts" for n in ast.walk(btree)),
   "no code in backdrop reads a dossier's `facts` list")

print("\n=== 7. set_completion IS SELECTABLE, NOT MERELY DECLARED ===")
ok("set_completion" in editorial.FORMATS, "it is in FORMATS")
ok(editorial.ALLOWED_FORMATS["set_completion"] == ["set_completion"],
   "the earn hook has exactly ONE skeleton — no story format may voice it")
ht, why = editorial.detect_hook({"set_name": "Nike SB x Staple"}, source="drop_correspondent",
                                price_verified=True, headline="a headline", earn_route=True)
ok(ht == "set_completion", "earn_route outranks even a same-day drop headline: %s" % ht)
ht2, _ = editorial.detect_hook({"year": 2005, "retail_price": 65, "estimated_resale": 3000,
                                "description": "x"}, source="", price_verified=True)
ok(ht2 != "set_completion", "a normal card never gets the set hook: %s" % ht2)

print("\n=== 8. THE SKELETON IS INCAPABLE OF PULL LANGUAGE ===")
base = {"name": "Nike SB Dunk Low", "colorway": "Staple NYC Pigeon", "year": 2005,
        "retail_price": 300, "set_name": "Nike SB x Staple",
        "set_requirements": ["Black Pigeon", "Purple Pigeon", "Staple Panda Pigeon"]}
out = editorial.build_draft(base, "set_completion", "set_completion",
                            price_verified=False, display_name="Nike SB Dunk Low")
ok(editorial.SET_ROUTE_PHRASE in out.lower(), "the route phrase is in the copy")
low = out.lower()
ok(not any(m in low for m in rails.PULL_MARKERS), "no pull marker in the output")
bad = dict(base, set_name="Pull It From A Pack")
try:
    editorial.build_draft(bad, "set_completion", "set_completion",
                          price_verified=False, display_name="X")
    ok(False, "injected pull language should have raised")
except AssertionError as e:
    ok("pull language" in str(e), "an injected pull phrase ASSERTS rather than ships")
# By AST, not regex: find assemble()'s set_completion branch and assert `frag` —
# the one slot carrying arbitrary prose — is not referenced anywhere inside it.
etree = ast.parse((REPO / "editorial.py").read_text())
asm = next(n for n in ast.walk(etree)
           if isinstance(n, ast.FunctionDef) and n.name == "assemble")
branch = None
for node in ast.walk(asm):
    if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
        c = node.test
        if (isinstance(c.left, ast.Name) and c.left.id == "fmt"
                and isinstance(c.comparators[0], ast.Constant)
                and c.comparators[0].value == "set_completion"):
            branch = node.body
ok(branch is not None, "found assemble()'s set_completion branch in the AST")
names = {n.id for b in (branch or []) for n in ast.walk(b) if isinstance(n, ast.Name)}
ok("frag" not in names,
   "the set_completion branch never references `frag` — it has no free-text slot: %s"
   % sorted(names))

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
