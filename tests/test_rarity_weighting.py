#!/usr/bin/env python3.12
"""E3 — rarity weighting. Zero LLM, zero network for the statistics.

A weighting is a claim about a DISTRIBUTION, so it is tested by drawing a few
thousand times and measuring, not by asserting that the code contains a number.

The thing that must not regress is that it is a WEIGHTING and not a filter:
every obtainable candidate stays eligible. Section 3 proves that directly — over
many draws, every tier in the pool eventually comes first.
"""
import ast, collections, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import daily_digest as DD

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

REPO = Path(__file__).resolve().parent.parent
N = 4000

def pool(**counts):
    out = []
    for tier, n in counts.items():
        out += [{"image_name": "%s_%d" % (tier, i), "rarity": tier} for i in range(n)]
    return out

print("\n=== 1. THE RULED SHARES COME OUT ===")
P = pool(Legendary=10, Rare=33, Uncommon=14, Common=8)
grp = collections.Counter()
for _ in range(N):
    t = DD._weighted_order(P)[0]["rarity"]
    grp[DD.TIER_GROUP[t]] += 1
for g, target in (("top", 0.15), ("premium", 0.50), ("body", 0.35)):
    got = grp[g] / N
    ok(abs(got - target) < 0.03, "%-8s %5.1f%% vs target %4.0f%% (±3pt)" % (g, 100*got, 100*target))

print("\n=== 2. THE SHARE HOLDS WHEN THE POOL'S COMPOSITION CHANGES ===")
# A pool dominated by Legendary must still yield ~15% top — the weight is per
# GROUP, divided by that group's size, so composition cannot drag the share.
P2 = pool(Legendary=40, Rare=5, Uncommon=5)
grp2 = collections.Counter()
for _ in range(N):
    grp2[DD.TIER_GROUP[DD._weighted_order(P2)[0]["rarity"]]] += 1
ok(abs(grp2["top"]/N - 0.15) < 0.03,
   "40 Legendary vs 10 others still yields %.1f%% top" % (100*grp2["top"]/N))

print("\n=== 3. IT IS A WEIGHTING, NOT A FILTER ===")
seen = set()
for _ in range(N):
    seen.add(DD._weighted_order(P)[0]["rarity"])
ok(seen == {"Legendary", "Rare", "Uncommon", "Common"},
   "every tier in the pool comes first sometimes — nothing is excluded: %s" % sorted(seen))
ordered = DD._weighted_order(P)
ok(len(ordered) == len(P) and {r["image_name"] for r in ordered} == {r["image_name"] for r in P},
   "the order is a PERMUTATION — no candidate is dropped")

print("\n=== 4. THE TOP GROUP INCLUDES THE EARNABLE GRAILS ===")
ok(DD.TIER_GROUP["GRAIL"] == "top" and DD.TIER_GROUP["HOLY GRAIL"] == "top",
   "GRAIL and HOLY GRAIL share the top bucket with Legendary")
ok(DD.TIER_GROUP["Rare"] == "premium", "Rare is its own premium bucket")
ok(sum(DD.GROUP_TARGET_SHARE.values()) == 1.0,
   "the shares sum to 1: %s" % DD.GROUP_TARGET_SHARE)
P3 = pool(Legendary=10, GRAIL=2, Rare=33)
tiers = collections.Counter()
for _ in range(N):
    tiers[DD._weighted_order(P3)[0]["rarity"]] += 1
ok(tiers["GRAIL"] > 0, "an earnable GRAIL is drawable, not starved out: %d/%d" % (tiers["GRAIL"], N))

print("\n=== 5. DEGENERATE POOLS DO NOT CRASH ===")
ok(DD._weighted_order([]) == [], "an empty pool returns empty")
one = DD._weighted_order([{"image_name": "x", "rarity": "Rare"}])
ok(len(one) == 1, "a single candidate survives")
unk = DD._weighted_order([{"image_name": "y", "rarity": "Mythic"}])
ok(len(unk) == 1, "an UNKNOWN tier is not dropped — it falls to the body group")
ok(DD.TIER_GROUP.get("Mythic", "body") == "body", "…by default, never by an exception branch")

print("\n=== 6. THE POOL NO LONGER EXCLUDES SET REWARDS ===")
src = (REPO / "daily_digest.py").read_text()
tree = ast.parse(src)
fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "candidates")
sql = " ".join(n.value for n in ast.walk(fn)
               if isinstance(n, ast.Constant) and isinstance(n.value, str) and "select" in n.value)
ok("is_set_reward" not in sql,
   "the standout query no longer filters on is_set_reward — that flag kept the "
   "three tentpoles out of every digest")
ok("set_rewards" in sql and "set_requirements" in sql,
   "it proves the earn route from the tables instead")
ok("exists (select 1 from public.set_requirements" in sql,
   "including the empty-set guard, same as rails and goat_import")

print("\n=== 7. EVERY CANDIDATE'S TIER IS LOGGED ===")
logs = []
_rl = DD.run_log
DD.run_log = lambda **kw: logs.append(kw)
try:
    DD._weighted_order(P)      # no logging here by design
    ok(not logs, "_weighted_order itself logs nothing — it is a pure ordering")
finally:
    DD.run_log = _rl
names = {n.value for n in ast.walk(fn)
         if isinstance(n, ast.Constant) and n.value in ("candidate_tiers", "candidates_selected")}
ok(names == {"candidate_tiers", "candidates_selected"},
   "candidates() logs both the pool's tiers and the selection's: %s" % sorted(names))
ok("_tier_histogram" in src, "a histogram helper exists so the shape is stable across events")

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
