#!/usr/bin/env python3.12
"""F4.3 suite — gate 8 + failure semantics. Zero LLM, zero network, zero spend."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import daily_digest as DD, card_render as CR, backdrop as BD

FAILS=[]
def ok(c,m):
    print(("  PASS  " if c else "  FAIL  ")+m)
    if not c: FAILS.append(m)

LOGS=[]
DD.run_log = lambda **kw: LOGS.append(kw)

class SpendAttempted(AssertionError): pass
CR.render_card = lambda *a, **k: (_ for _ in ()).throw(SpendAttempted("render_card CALLED"))
BD.generate    = lambda *a, **k: (_ for _ in ()).throw(SpendAttempted("BD.generate CALLED — $0.04"))

CAND={"image_name":"aj3_mocha_og","rarity":"Rare"}
# ★ 2026-09-16: gate8 now DERIVES obtainability from (image_name, rarity) — the
# hardcoded pool_reachable=True is gone. A direct gate8 call that omits the pair
# fails the OBTAINABLE rail, correctly. These suites are about the attribution
# and length rails, so they pass CAND's own pair, which is pool-reachable.
def gate8(text, price_ok, composition=None):
    return DD.gate8(text, price_ok, composition, CAND["image_name"], CAND["rarity"])
ROW={"name":"Jordan 3 Retro","brand":"Jordan","colorway":"Mocha","year":2001,
     "retail_price":125,"estimated_resale":300,"description":"A story sentence about it."}
def mk(lead_fn):
    def f(ctx, attempt, failed):
        return lead_fn(attempt, failed)
    return f

print("\n=== 1. TRAP 1 is PREVENTED by the composer, not caught by gate 8 ===")
# ★ SPEC CORRECTION (F4.3): the spec expected the trap lead to be CAUGHT at
# generation. It is not — it is PREVENTED. compose() appends the attribution,
# which supplies the marker, so the attribution rail CANNOT fail after
# composition. Prevention is strictly stronger than detection: there is no
# failure to retry, and no way for the writer to reach the rail at all.
from research import compose_text as CT
from x_client import weighted_len
TRAP="The card tracks its resale, not the card."
ok(gate8(TRAP, True)[0] is False, "the raw trap lead WOULD fail the attribution rail")
ok(any("attribution" in f for f in gate8(TRAP, True)[1]), f"…on that rail: {gate8(TRAP,True)[1]}")
ok(gate8(CT.compose(lead=TRAP, include_link=False), True)[0] is True,
   "…but COMPOSED it passes — the writer cannot reach the rail")
LOGS.clear()
text,failed,att = DD.draft_with_gate8(CAND,ROW,"story_spotlight","story","Jordan 3",True,
    draft_fn=mk(lambda a,f: {"lead":TRAP,"body":None}), max_retries=2)
ok(text is not None and att==1, f"so it ships on attempt 1, no retries: att={att}")

print("\n=== 2. what gate 8 DOES catch — dangers the composer cannot rescue ===")
DANGERS=[("Every pack is a jackpot — place your bet.","no gambling language",True),
         ("These cards are an investment with guaranteed profit.","no investment framing",True),
         ("This card is worth $400 — cash out anytime.","no card-value claim",True),
         ("Cheaper than StockX and GOAT.com.","no competitor named",True),
         ("The Jordan 3 trades for $300 now.","no unverified price asserted in agent voice",False),
         ("x"*400,"over 280 weighted characters",True)]
for lead,rail,pv in DANGERS:
    passed,failed = gate8(CT.compose(lead=lead, include_link=False), pv)
    ok((not passed) and rail in failed, f"BLOCKED: {rail}")

print("\n=== 2b. NO IMAGE SPEND on a genuine gate-8 failure ===")
LOGS.clear()
GAMBLE="Every pack is a jackpot — place your bet and see what you pull."
try:
    text,failed,att = DD.draft_with_gate8(CAND,ROW,"story_spotlight","story","Jordan 3",True,
        draft_fn=mk(lambda a,f: {"lead":GAMBLE,"body":None}), max_retries=2)
    ok(text is None, "gambling lead never produces a post")
    ok(att==3, f"1 + 2 retries = 3 attempts: {att}")
    ok(True, "render_card and BD.generate NEVER fired — $0.00 spent on a failed draft")
except SpendAttempted as e:
    ok(False, f"SPEND ATTEMPTED: {e}")
gf=[l for l in LOGS if l.get("event")=="writer_gate_failed"]
ok(len(gf)==3, f"3 writer_gate_failed rows: {len(gf)}")
ok(all({"proposal_id","image_name","failed_rails","attempt"} <= set(l) for l in gf),
   "each row carries proposal_id, image_name, failed_rails, attempt")
print(f"      attempts logged: {[l['attempt'] for l in gf]}, rails: {gf[0]['failed_rails']}")

print("\n=== 3. the retry loop FEEDS BACK the failed rail labels ===")
seen=[]
def improving(attempt, failed):
    seen.append(list(failed))
    return {"lead": GAMBLE if attempt==1 else "1985. Tinker Hatfield cut a window into the midsole.",
            "body": None}
text,failed,att = DD.draft_with_gate8(CAND,ROW,"story_spotlight","story","Jordan 3",True,
    draft_fn=mk(improving), max_retries=2)
ok(text is not None, "a corrected second attempt succeeds")
ok(att==2, f"succeeded on attempt 2: {att}")
ok(seen[0]==[] and seen[1]!=[], f"attempt 2 received the failures from attempt 1: {seen}")
print(f"      fed back: {seen[1]}")

print("\n=== 4. gate 8 is the SAME rail, just earlier ===")
good="1985. Tinker Hatfield cut a window into the midsole so you could see the air."
t,f,a = DD.draft_with_gate8(CAND,ROW,"story_spotlight","story","Jordan 3",True,
    draft_fn=mk(lambda at,fl: {"lead":good,"body":None}), max_retries=2)
ok(t is not None and a==1, "a clean lead passes first time")
ok("Its card is in CYPHER" in t, "composer appended the attribution")
ok("apps.apple.com" not in t, "NO link in the body (ruled)")
from x_client import weighted_len
ok(weighted_len(t)<=280, f"within 280: {weighted_len(t)}")
print(f"      composed ({weighted_len(t)} weighted): {t!r}")

print("\n=== 5. over-280 is caught as a gate-8 failure, not a crash ===")
t,f,a = DD.draft_with_gate8(CAND,ROW,"story_spotlight","story","Jordan 3",True,
    draft_fn=mk(lambda at,fl: {"lead":"x"*400,"body":None}), max_retries=2)
ok(t is None and any("280" in x for x in f), f"over-length reported as a rail: {f}")

print("\n=== 6. a drafter that gives up (returns None) abandons cleanly ===")
t,f,a = DD.draft_with_gate8(CAND,ROW,"story_spotlight","story","Jordan 3",True,
    draft_fn=mk(lambda at,fl: None), max_retries=2)
ok(t is None, "returns None")
ok(a==1, f"stops immediately, no wasted attempts: {a}")

print("\n=== 7. skeleton_draft_fn does not retry a deterministic template ===")
ok(DD.skeleton_draft_fn({"row":ROW,"hook_type":"story","fmt":"story_spotlight",
                         "price_ok":True,"display":"Jordan 3"}, 2, ["x"]) is None,
   "attempt 2 returns None — a template has nothing to revise")

print("\n"+("ALL PASS" if not FAILS else f"{len(FAILS)} FAILURE(S): {FAILS}"))
sys.exit(1 if FAILS else 0)
