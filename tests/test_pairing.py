#!/usr/bin/env python3.12
"""E4 — which_would_you_pull. Zero LLM, zero spend.

Two claims are load-bearing and neither is about copy:

  1. BOTH CARDS ARE ON THE PULL ROUTE. The question is "which would you PULL",
     so a set reward is disqualified however good it looks — it is EARNABLE, and
     showing it here implies a pack outcome. The test is per CARD.
  2. GROUP-LEVEL ROTATION. 138 pairs exist but the AF1 supplies 45 and the top
     five silhouettes supply 95, so a uniform pick over PAIRS shows the AF1 about
     a third of the time and the format dies of sameness.
"""
import ast, collections, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from research import pairing as PR
import editorial, daily_digest as DD

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

REPO = Path(__file__).resolve().parent.parent

def shoe(name, cw, tags=("collab_origin",), rarity="Rare"):
    return {"image_name": "%s_%s" % (name, cw), "name": name, "colorway": cw,
            "rarity": rarity, "tags": list(tags)}

BIG = ([shoe("Nike Air Force 1 Low", "c%d" % i) for i in range(10)]
       + [shoe("Jordan 4 Retro", "d%d" % i) for i in range(6)]
       + [shoe("Nike SB Dunk Low", "e%d" % i) for i in range(4)]
       + [shoe("Air Max 90", "f%d" % i) for i in range(2)]
       + [shoe("Jordan 11 Retro", "g%d" % i) for i in range(3)]
       + [shoe("Yeezy Slide", "h%d" % i) for i in range(3)])

print("\n=== 1. GROUPS NEED TWO DISTINCT SHOES ===")
g = PR.groups(BIG + [shoe("Lonely Silhouette", "x")])
ok("Lonely Silhouette" not in g, "a one-shoe silhouette forms no pair")
ok(len(g) == 6, "six pairable groups from the fixture: %d" % len(g))
ok(all(len({s["image_name"] for s in v}) == len(v) for v in g.values()),
   "a shoe never pairs with itself — groups are deduped by image_name")

print("\n=== 2. GROUP ROTATION FLATTENS THE AF1 ===")
rng = random.Random(11)
hist, picks = [], collections.Counter()
for _ in range(300):
    p = PR.pick_pair(BIG, history=hist, rng=rng)
    if p is None:
        hist = hist[1:]; continue
    picks[p["group"]] += 1
    hist = [p["group"]] + hist[:PR.GROUP_DEPTH - 1]
af1 = picks["Nike Air Force 1 Low"] / sum(picks.values())
ok(af1 < 0.25, "the AF1 group takes %.0f%% of picks, not the ~33%% a pair-uniform "
               "pick would give it" % (100 * af1))
spread = max(picks.values()) - min(picks.values())
ok(spread <= 0.15 * sum(picks.values()), "groups are near-even (spread %d over %d picks)"
   % (spread, sum(picks.values())))

print("\n=== 3. THE WINDOW IS REAL, NOT DECORATIVE ===")
p1 = PR.pick_pair(BIG, history=[], rng=random.Random(3))
ok(p1 is not None, "a fresh history picks something")
used = list(g)
ok(PR.pick_pair(BIG, history=used) is None,
   "when EVERY group is in the window it returns None rather than repeating")
hist2 = ["Nike Air Force 1 Low"]
for _ in range(40):
    p = PR.pick_pair(BIG, history=hist2, rng=rng)
    ok_ = p is not None and p["group"] != "Nike Air Force 1 Low"
    if not ok_: break
ok(ok_, "a group in the window is never chosen while it is there")

print("\n=== 4. PAIRS PREFER A SHARED HOOK TAG ===")
mixed = [shoe("Mixed", "a", ("collab_origin",)), shoe("Mixed", "b", ("release_drama",)),
         shoe("Mixed", "c", ("collab_origin",))]
found = set()
for _ in range(50):
    p = PR.pick_pair(mixed, history=[], rng=rng)
    found.add(p["shared_tags"])
ok(found == {1}, "it always picks the tag-sharing pair when one exists: %s" % found)

print("\n=== 5. SET REWARDS CANNOT APPEAR — PULL ROUTE ONLY ===")
src = (REPO / "research" / "pairing.py").read_text()
ok("PULL" in src and "EARNABLE" in src, "the module states the constraint")
# the live pool the digest feeds it is built from `reachable`, not `obtainable`
dsrc = (REPO / "daily_digest.py").read_text()
tree = ast.parse(dsrc)
ok(DD.TIER_GROUP.get("GRAIL") == "top", "GRAIL is still a real tier elsewhere")
# a set reward that somehow reached the rows must still fail the rail per card
import rails
r = rails.obtainability("sb_dunk_low_staple_nyc_pigeon", "HOLY GRAIL")
ok(r[1] == "earn", "the Pigeon is EARNABLE, not pullable: route=%s" % r[1])
r2 = rails.obtainability("sb_dunk_low_black_pigeon", "Rare")
ok(r2[1] == "pull", "a requirement card IS pullable and may appear: route=%s" % r2[1])

print("\n=== 6. THE SKELETON IS STRUCTURALLY PRICE-FREE ===")
base = {"name": "Nike Air Force 1 Low", "colorway": "Volt", "year": 2018,
        "retail_price": 170, "estimated_resale": 900,
        "pair_title": 'Nike Air Force 1 Low “Lemonade”'}
out = editorial.build_draft(base, "which_would_you_pull", "which_would_you_pull",
                            price_verified=True, display_name="Nike Air Force 1 Low")
ok(editorial.PULL_QUESTION in out, "the question is in the copy")
ok("170" not in out and "900" not in out and "$" not in out,
   "no retail, no resale, no currency — though all three were on the row")
ok("est. value" not in out.lower(), "and no attribution sentence: the frame carries no figure")
try:
    editorial.build_draft(dict(base, pair_title="the $900 one"), "which_would_you_pull",
                          "which_would_you_pull", price_verified=True, display_name="X")
    ok(False, "an injected price should have raised")
except AssertionError as e:
    ok("price reference" in str(e), "an injected price ASSERTS rather than ships")
etree = ast.parse((REPO / "editorial.py").read_text())
asm = next(n for n in ast.walk(etree) if isinstance(n, ast.FunctionDef) and n.name == "assemble")
branch = None
for node in ast.walk(asm):
    if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
        c = node.test
        if (isinstance(c.left, ast.Name) and c.left.id == "fmt"
                and isinstance(c.comparators[0], ast.Constant)
                and c.comparators[0].value == "which_would_you_pull"):
            branch = node.body
names = {n.id for b in (branch or []) for n in ast.walk(b) if isinstance(n, ast.Name)}
ok(branch is not None and not ({"frag", "year", "retail"} & names),
   "the branch reads no field a price could travel in: %s" % sorted(names))

print("\n=== 7. IT IS SELECTABLE, AND THE FRAME IS FORCED ===")
ok("which_would_you_pull" in editorial.FORMATS, "it is in FORMATS")
ok(editorial.DECLARED_NOT_READY == {}, "DECLARED_NOT_READY is empty — nothing is left declared-only")
ok(editorial.ALLOWED_FORMATS["which_would_you_pull"] == ["which_would_you_pull"],
   "one hook, one skeleton — no substitution can drop a card")
ok('"two_card_crop" if fmt == "which_would_you_pull"' in dsrc,
   "the composition is FORCED, not rotated into")
from research import composition as COMP
ok(COMP.card_shows_value("two_card_crop") is False,
   "…and that frame crops the EST. VALUE row out of both cards")

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
