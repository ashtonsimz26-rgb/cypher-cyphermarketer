#!/usr/bin/env python3.12
"""Rails-bar suite for the OBTAINABLE amendment. Zero LLM, zero network, zero spend.

Three things are proved here, in order of how badly they failed before:

  1. THE RAIL IS NOT INERT. Both call sites used to pass the literal
     `pool_reachable=True`, so the check could not fail however wrong the card
     was. Reachability was real but guaranteed UPSTREAM; the rail was decoration.
     An inert rail is worse than no rail because it is trusted. Test 1 scans the
     AST for the literal so it can never come back.
  2. EACH DOOR SEPARATELY. The digest by AST, the poller by a live call — the
     same discipline as the human_copy_required gate, because "a rail goes on
     every door" (d6e900d) and a rail proved at one door proves nothing at the
     other.
  3. THE SET PATH IS PROVEN, NEVER ASSUMED. Empty requirement lists, unreachable
     requirements, stale caches and the is_set_reward flag all fail closed.
"""
import ast, json, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rails

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

REPO = Path(__file__).resolve().parent.parent
PULL = ("sb_dunk_low_black_pigeon", "Rare")
EARN = ("sb_dunk_low_staple_nyc_pigeon", "HOLY GRAIL")
DARK = ("nike_nike_air_force_1_low_off_white_moma", "HOLY GRAIL")

def blob(generated=None, routes=None, pairs=None):
    return {"generated_at": (generated or datetime.now(timezone.utc)).isoformat(),
            "reachable_pairs": pairs if pairs is not None else ["%s|%s" % PULL],
            "routes": routes if routes is not None else {
                "%s|%s" % EARN: {"set_name": "Nike SB x Staple", "requirements": [
                    {"image_name": "sb_dunk_low_black_pigeon", "reachable": True},
                    {"image_name": "sb_dunk_low_purple_pigeon", "reachable": True},
                    {"image_name": "sb_dunk_low_staple_panda_pigeon", "reachable": True}]}}}

print("\n=== 1. THE INERT LITERAL CANNOT COME BACK ===")
for f in ("daily_digest.py", "telegram_bot.py", "rails.py"):
    src = (REPO / f).read_text()
    hits = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "pool_reachable":
                    hits.append(ast.dump(kw.value)[:40])
    ok(not hits, "%s passes no pool_reachable= argument at all (%s)" % (f, hits or "none"))

print("\n=== 2. DOOR 1 — THE DIGEST (by AST) ===")
dd = ast.parse((REPO / "daily_digest.py").read_text())
g8 = next(n for n in ast.walk(dd) if isinstance(n, ast.FunctionDef) and n.name == "gate8")
args = [a.arg for a in g8.args.args] + [a.arg for a in g8.args.kwonlyargs]
ok("image_name" in args and "rarity" in args, "gate8 takes image_name and rarity: %s" % args)
cd_kw = set()
for node in ast.walk(g8):
    if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "check_draft":
        cd_kw = {k.arg for k in node.keywords}
ok({"image_name", "rarity"} <= cd_kw, "gate8 forwards the pair to check_draft: %s" % sorted(cd_kw))
dwg = next(n for n in ast.walk(dd) if isinstance(n, ast.FunctionDef) and n.name == "draft_with_gate8")
calls = [n for n in ast.walk(dwg) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "gate8"]
ok(len(calls) == 2, "draft_with_gate8 calls gate8 twice (found %d)" % len(calls))
ok(all(len(c.args) >= 5 for c in calls),
   "BOTH gate8 calls pass the pair — the bare-text retry is not a hole")
b1 = next(n for n in ast.walk(dd) if isinstance(n, ast.FunctionDef) and n.name == "build_one")
ok(any(getattr(n.func, "attr", "") == "obtainability"
       for n in ast.walk(b1) if isinstance(n, ast.Call)),
   "build_one proves obtainability itself, before any spend")
ok("is_set_reward" in ast.dump(b1) and '_route != "earn"' in (REPO / "daily_digest.py").read_text(),
   "build_one's set-reward guard is CONDITIONAL on the earn route, not absolute")

print("\n=== 3. DOOR 2 — THE POLLER (by live call) ===")
import telegram_bot as TB
rails.SET_ROUTES = Path(tempfile.mkdtemp()) / "_set_routes.json"
rails.SET_ROUTES.write_text(json.dumps(blob()))

good = {"style_code": None, "image_name": PULL[0], "rarity": PULL[1]}
okg, failed = TB.rails_gate("A post about the real pair's resale market.", good)
ok(okg, "a pool-reachable pair passes at the poller: %s" % [c.name for c in failed])

nopair = {"style_code": None, "image_name": PULL[0]}          # pre-amendment ctx
okn, failed = TB.rails_gate("A post about the real pair's resale market.", nopair)
ok(not okn and any(c.name == "OBTAINABLE" for c in failed),
   "a proposal stored WITHOUT rarity fails OBTAINABLE closed at the poller")

okx, failed = TB.rails_gate("A post about the real pair's resale market.", None)
ok(not okx and any(c.name == "OBTAINABLE" for c in failed),
   "a missing rails_ctx fails OBTAINABLE closed — never permissive")

print("\n=== 4. THE TWO ROUTES ===")
r = blob()
ok(rails.obtainability(*PULL, r)[1] == "pull", "a pool-reachable pair routes 'pull'")
ok(rails.obtainability(*EARN, r)[1] == "earn", "a set reward with all requirements routes 'earn'")
ok(rails.obtainability(*DARK, r)[0] is False, "a dark card is refused")
ok(rails.obtainability(None, None, r)[0] is False, "no pair supplied is refused, not assumed")

print("\n=== 5. THE SET PATH IS PROVEN, NEVER ASSUMED ===")
empty = blob(routes={"%s|%s" % EARN: {"set_name": "Empty Set", "requirements": []}})
res = rails.obtainability(*EARN, empty)
ok(res[0] is False and "zero requirement" in res[2],
   "a set with ZERO requirement rows is refused — all([]) is True and must not qualify")
part = blob(routes={"%s|%s" % EARN: {"set_name": "Nike SB x Staple", "requirements": [
    {"image_name": "a", "reachable": True}, {"image_name": "b", "reachable": False}]}})
res = rails.obtainability(*EARN, part)
ok(res[0] is False and "not pool-reachable" in res[2],
   "one unreachable requirement sinks the whole set — both halves, every time")

print("\n=== 6. CACHE FRESHNESS FAILS CLOSED, AND SAYS WHY ===")
cases = [
    ("missing", None),
    ("unreadable", "{not json"),
    ("undated", json.dumps({"routes": {}, "reachable_pairs": []})),
    ("stale", json.dumps(blob(datetime.now(timezone.utc) - timedelta(days=8)))),
]
for label, content in cases:
    if content is None:
        rails.SET_ROUTES = Path(tempfile.mkdtemp()) / "_absent.json"
    else:
        rails.SET_ROUTES = Path(tempfile.mkdtemp()) / "_set_routes.json"
        rails.SET_ROUTES.write_text(content)
    got, why = rails.load_set_routes()
    ok(got is None and bool(why), "a %s cache fails closed with a reason: %r" % (label, why[:58]))
rails.SET_ROUTES = Path(tempfile.mkdtemp()) / "_set_routes.json"
rails.SET_ROUTES.write_text(json.dumps(blob(datetime.now(timezone.utc) - timedelta(days=6))))
got, why = rails.load_set_routes()
ok(got is not None, "a 6-day-old cache still qualifies (N=%d)" % rails.FRESHNESS_DAYS)

print("\n=== 7. THE ROUTE OBLIGATIONS ATTACH ONLY ON 'EARN' ===")
r = blob()
def names(text, pair, **kw):
    cs = rails.check_draft(text, card_shows_value=False, price_verified=True,
                           image_name=pair[0], rarity=pair[1], routes=r, **kw)
    return {c.name: c.passed for c in cs}

n = names("Complete the set and the Pigeon is yours.", EARN)
ok(n.get("SET_ROUTE_STATED") and n.get("NO_PULL_IMPLICATION"), "a correct earn post passes both")
n = names("The NYC Pigeon is in CYPHER.", EARN)
ok(n.get("SET_ROUTE_STATED") is False, "an earn post that does not state the route FAILS")
n = names("Complete the set — or just pull it from a pack.", EARN)
ok(n.get("NO_PULL_IMPLICATION") is False, "an earn post implying a pack pull FAILS")
n = names("Can't cop? Pull it.", PULL)
ok("SET_ROUTE_STATED" not in n and "NO_PULL_IMPLICATION" not in n,
   "a PULL post carries neither obligation — the widening is not a new burden")

print("\n=== 8. RAIL NAMES ARE STABLE, AND NOT ORDINALS ===")
cs = rails.check_draft("x", card_shows_value=False, price_verified=True,
                       image_name=EARN[0], rarity=EARN[1], routes=r)
got = [c.name for c in cs]
expected = {"NO_GAMBLING", "NO_INVESTMENT_FRAMING", "NO_CARD_VALUE_CLAIM",
            "NO_COMPETITOR_NAMED", "OBTAINABLE", "VALUE_FIGURE_ATTRIBUTED",
            "NO_UNVERIFIED_PRICE", "SET_ROUTE_STATED", "NO_PULL_IMPLICATION"}
ok(set(got) == expected, "the rail set is exactly the documented names: %s" % sorted(set(got) ^ expected))
ok(len(got) == len(set(got)), "names are unique")
ok(not any(ch.isdigit() for n_ in got for ch in n_), "no name carries an ordinal: %s" % got)
ok(all(isinstance(c, rails.Rail) and c._fields == ("name", "label", "passed", "note") for c in cs),
   "every check is a Rail(name, label, passed, note)")

print("\n=== 9. THE FLAG DISAGREES WITH THE TABLE — PINNED ===")
# state/ is gitignored: the cache is DERIVED and the digest rebuilds it every
# run. This section needs the real one, so it demands it rather than skipping —
# a pin that quietly stops running is the inert-rail problem in test form.
LIVE = REPO / "state" / "_set_routes.json"
assert LIVE.exists(), (
    "state/_set_routes.json is missing. It is derived and gitignored; rebuild it with:\n"
    "    python3.12 -c \"import sys; sys.path.insert(0,'.'); "
    "import daily_digest as D; D.refresh_set_routes()\"")
live = json.loads(LIVE.read_text())
flagged, routes_ = set(live["flagged_is_set_reward"]), set(live["routes"])
ok(flagged - routes_ == {"aj4_sb_varsity_red|Legendary"},
   "catalog_cards.is_set_reward flags a pair set_rewards does not name: %s" % sorted(flagged - routes_))
ok(len(flagged) == 4 and len(routes_) == 3,
   "pinned: 4 flagged pairs, 3 real rewards (got %d/%d)" % (len(flagged), len(routes_)))
ok(rails.obtainability("aj4_sb_varsity_red", "Legendary", live)[0] is False,
   "the flagged-but-unearnable pair is REFUSED — the table decides, never the flag")
ok(rails.obtainability("aj4_sb_varsity_red", "GRAIL", live)[1] == "earn",
   "the pair set_rewards DOES name is earnable")

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
