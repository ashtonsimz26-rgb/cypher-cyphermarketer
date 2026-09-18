#!/usr/bin/env python3.12
"""Earn-route dossiers + disk health. Zero LLM, zero network, zero spend.

reachable_shoes() decides which shoes ever get a dossier, and it was the
pool-reachable set. The earn route unlocked three cards it had never seen, so
the three best cards in the catalog would have fallen back to a category
scene — the exact failure E2 was built to fix.

The dangerous way to widen it is "top tier". That would admit 63 cards nobody
can obtain. Test 2 asserts the widening is by SET REWARD and nothing else.
"""
import ast, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import daily_digest as DD, backdrop as BD
from research import story as ST
from research import selector as SEL, dossier as DOS

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

REPO = Path(__file__).resolve().parent.parent
REWARDS = ("sb_dunk_low_gratefuldead_orange", "sb_dunk_low_staple_nyc_pigeon",
           "aj4_sb_varsity_red")

print("\n=== 1. THE WIDENING IS BY SET REWARD, PROVED IN THE SQL ===")
# The SQL LITERAL only — not the docstring. Scanning the whole function makes
# prose explaining "the 63 GRAIL cards stay out" look like a tier filter, which
# is a test that fails on its own explanation.
gtree = ast.parse((REPO / "research" / "goat_import.py").read_text())
rs = next(n for n in ast.walk(gtree)
          if isinstance(n, ast.FunctionDef) and n.name == "reachable_shoes")
sql = " ".join(n.value for n in ast.walk(rs)
               if isinstance(n, ast.Constant) and isinstance(n.value, str)
               and "select" in n.value.lower())
ok(bool(sql), "found the SQL literal in reachable_shoes")
ok("set_rewards" in sql, "the query reads set_rewards, the TABLE")
ok("is_set_reward" not in sql, "it does NOT read the catalog flag, which disagrees with it")
ok("GRAIL" not in sql and "rarity::text in" not in sql,
   "the SQL never names a TIER — earn means earn, not top tier")
ok("exists (select 1 from public.set_requirements" in sql,
   "a set with ZERO requirement rows is excluded — the vacuous-truth guard, in SQL")
ok("reward_rarity" in sql,
   "it joins on the reward's own (image_name, rarity) pair, not the image alone")

print("\n=== 2. THE 63 UNOBTAINABLE TOP-TIER CARDS STAY OUT ===")
live = json.loads((REPO / "state" / "_set_routes.json").read_text())
rewards = {k.split("|")[0] for k in live["routes"]}
ok(len(rewards) == 3, "exactly 3 set rewards exist: %s" % sorted(rewards))
have = {p.stem for p in (REPO / "data" / "dossiers").glob("*.json")}
# every dossier that exists must be obtainable: pool-reachable, or a set reward
reach_imgs = {k.split("|")[0] for k in live["reachable_pairs"]}
strays = have - reach_imgs - rewards
ok(not strays, "no dossier exists for a shoe that is neither reachable nor a reward: %s" % sorted(strays)[:5])

print("\n=== 3. WHAT CAME BACK FOR THE THREE ===")
for n in REWARDS:
    p = REPO / "data" / "dossiers" / ("%s.json" % n)
    if not p.exists():
        print("  ----  %-34s NO DOSSIER (no style_code -> GOAT never queried)" % n)
        continue
    d = json.loads(p.read_text())
    hooks = [f for f in d.get("facts", []) if f.get("tag") in SEL.NARRATIVE_HOOK_TAGS]
    key = ST.brief(d, None)["scene_key"]
    ok(SEL.has_narrative_hook(d) and DOS.dossier_proposable(n) and key is not None,
       "%-34s %d hook(s), story key %s" % (n, len(hooks), key))

print("\n=== 4. THE SCENE NO LONGER FALLS BACK FOR THEM ===")
for n, expect in (("sb_dunk_low_gratefuldead_orange", "story:psychedelic_venue"),
                  ("sb_dunk_low_staple_nyc_pigeon", "story:winter_side_street")):
    d = json.loads((REPO / "data" / "dossiers" / ("%s.json" % n)).read_text())
    _, source, _ = BD.scene_for({"category": "Skateboarding", "year": 2005},
                                ST.brief(d, None)["scene_key"])
    ok(source == expect, "%-34s -> %s" % (n, source))

print("\n=== 5. DISK HEALTH SPEAKS TO TELEGRAM, NOT ONLY THE LOG ===")
import telegram_bot as TB
sent, logs = [], []
_st, _rl, _df = TB.send_text, DD.run_log, DD.disk_free_gb
TB.send_text = lambda e, t, *a, **k: sent.append(t)
DD.run_log = lambda **kw: logs.append(kw)
try:
    DD.disk_free_gb = lambda: 5.0
    DD.disk_health("digest")
    ok(not sent, "above the floor: logged, printed, NOT sent")
    ok(any(l.get("event") == "disk_free" for l in logs), "…but always ledgered")
    DD.disk_free_gb = lambda: 0.42
    DD.disk_health("digest")
    ok(len(sent) == 1 and "0.42 GB" in sent[0], "below the floor: one Telegram line with the number")
    def boom(*a, **k): raise RuntimeError("telegram down")
    TB.send_text = boom
    DD.disk_health("digest")
    ok(any(l.get("event") == "disk_alert_failed" for l in logs),
       "a Telegram failure is ledgered and does NOT kill the run")
finally:
    TB.send_text, DD.run_log, DD.disk_free_gb = _st, _rl, _df
ok(DD.DISK_FLOOR_GB == 1.0, "the floor is 1 GB as ruled")
tree = ast.parse((REPO / "daily_digest.py").read_text())
mn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "main")
ok(any(getattr(c.func, "id", "") == "disk_health" for c in ast.walk(mn) if isinstance(c, ast.Call)),
   "main() actually calls it — a health check nothing invokes is the inert-rail shape")

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
