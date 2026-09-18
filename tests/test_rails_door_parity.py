#!/usr/bin/env python3.12
"""The two rails doors return the SAME verdict for the SAME proposal. Zero LLM,
zero network, zero spend.

★★ WHY THIS SUITE EXISTS. rails.check_draft() runs at two doors: gate 8 at draft
time (daily_digest) and rails_gate at approve time (telegram_bot). Each derived
the card_shows_value input for itself. G2 (13834d0, 09-11) taught the draft door
to compute it from the composition; the approve door kept a literal True. From
then until 2026-09-18 the same text on the same card PASSED at draft and FAILED
at approval on every composition that crops the EST. VALUE row out — shoe_crop,
shoe_only, two_card_crop, 3 of 9 — while a docstring at EACH door asserted the
two matched. p_34f18679da found it.

Every earlier rails defect in this repo was a rail that never ran. This one ran
at both doors and disagreed. The fix put both doors on one helper
(composition.rails_card_shows_value); that makes drift unlikely. This suite is
what makes it DETECTED: it states the property that was missing — draft-time and
approve-time verdicts are equal — and checks it across every composition, both
kinds of text, and both ways a proposal can have stored its composition.

The rail itself did not change. Section 3 proves it: a composition that shows
the value row still fails without attribution, at BOTH doors.
"""
import ast, json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import daily_digest as DD            # noqa: E402
import telegram_bot as TB            # noqa: E402
from research import composition as COMP  # noqa: E402

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

# A real, reachable (image_name, rarity) pair — p_34f18679da's — so OBTAINABLE
# passes at both doors and the only rail in play is the one under test.
IMAGE, RARITY = "jordan_1_retro_low_og_shadow", "Uncommon"
TEXTS = {
    "no_attribution":   "Swarovski crystals set into the grey leather Swoosh on the AJ1 Low 'Shadow'.",
    "with_attribution": "Swarovski crystals set into the grey leather Swoosh on the AJ1 Low 'Shadow' — the real pair.",
}
VALUE_RAIL = "card image w/ value figure carries real-sneaker attribution"
ALL = list(COMP.COMPOSITIONS)

def draft_verdict(text, comp):
    passed, failed = DD.gate8(text, price_ok=False, composition=comp,
                              image_name=IMAGE, rarity=RARITY)
    return passed, sorted(failed)

def approve_verdict(text, comp, stored):
    """stored='ctx' — composition inside rails_ctx (post-2026-09-18 proposals);
       stored='row' — only on the top-level row (pre-change proposals);
       stored='none' — recorded nowhere (CLI-driven / pre-R6)."""
    ctx = {"image_name": IMAGE, "rarity": RARITY}
    if stored == "ctx": ctx["composition"] = comp
    row_comp = comp if stored == "row" else None
    passed, failed = TB.rails_gate(text, ctx, row_comp)
    return passed, sorted(c.label for c in failed)

print("\n=== 0. THE REGISTRY IS WHAT THIS SUITE THINKS IT IS ===")
ok(len(ALL) == 9, "9 compositions registered (%d) — a new one is covered automatically" % len(ALL))
cropping = sorted(c for c in ALL if not COMP.card_shows_value(c))
ok(cropping == ["shoe_crop", "shoe_only", "two_card_crop"],
   "the value-cropping set is exactly the 3 the bug hit: %s" % cropping)

print("\n=== 1. THE PROPERTY — same proposal, same verdict, at both doors ===")
for comp in ALL:
    for tname, text in TEXTS.items():
        d = draft_verdict(text, comp)
        for stored in ("ctx", "row"):
            a = approve_verdict(text, comp, stored)
            ok(d == a, "%-14s %-17s stored=%-4s draft=%s approve=%s"
               % (comp, tname, stored, d[0], a[0]))

print("\n=== 2. FAIL-CLOSED DEFAULTS AGREE TOO ===")
for tname, text in TEXTS.items():
    d = draft_verdict(text, None)
    a = approve_verdict(text, None, "none")
    ok(d == a, "composition MISSING, %s: both doors fall back to True and agree" % tname)
    d = draft_verdict(text, "angled")                  # retired, unregistered
    a = approve_verdict(text, "angled", "ctx")
    ok(d == a, "composition UNKNOWN ('angled'), %s: both fail closed and agree" % tname)
ok(COMP.rails_card_shows_value(None) is True, "missing composition -> True (require attribution)")
ok(COMP.rails_card_shows_value("angled") is True, "unregistered composition -> True (require attribution)")

print("\n=== 3. THE RAIL WAS NOT WEAKENED ===")
for comp in ALL:
    shows = COMP.card_shows_value(comp)
    d_pass, d_failed = draft_verdict(TEXTS["no_attribution"], comp)
    a_pass, a_failed = approve_verdict(TEXTS["no_attribution"], comp, "ctx")
    if shows:
        ok(VALUE_RAIL in d_failed and VALUE_RAIL in a_failed,
           "%-14s shows the value row -> unattributed text FAILS at both doors" % comp)
    else:
        ok(d_pass and a_pass,
           "%-14s crops the value row -> unattributed text PASSES at both doors" % comp)
for comp in ALL:
    ok(draft_verdict(TEXTS["with_attribution"], comp)[0]
       and approve_verdict(TEXTS["with_attribution"], comp, "ctx")[0],
       "%-14s attributed text passes at both doors" % comp)

print("\n=== 4. THE REAL PROPOSAL THAT FOUND IT ===")
row = next((json.loads(l) for l in open(REPO / "ledger/proposals.jsonl")
            if '"p_34f18679da"' in l and '"proposed"' in l), None)
if row:
    ctx = row["rails_ctx"]
    ok("composition" not in ctx, "p_34f18679da is pre-change: composition only on the top-level row")
    d = DD.gate8(row["text"], price_ok=False, composition=row["composition"],
                 image_name=ctx["image_name"], rarity=ctx["rarity"])[0]
    a = TB.rails_gate(row["text"], ctx, row["composition"])[0]
    ok(d is True and a is True,
       "p_34f18679da (shoe_crop): draft=%s approve=%s — was True/False before the fix" % (d, a))
else:
    print("  SKIP  p_34f18679da not in this ledger")

print("\n=== 5. NEITHER DOOR DERIVES THE INPUT FOR ITSELF ===")
# The fix is one helper called from both doors. A literal, or a second local
# derivation, is exactly how the doors drifted — so forbid both, structurally.
for fname in ("telegram_bot.py", "daily_digest.py"):
    tree = ast.parse((REPO / fname).read_text())
    kw = [k for n in ast.walk(tree) if isinstance(n, ast.Call)
          for k in n.keywords if k.arg == "card_shows_value"]
    ok(kw and not any(isinstance(k.value, ast.Constant) for k in kw),
       "%s: no check_draft call passes card_shows_value as a literal" % fname)
    local = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") == "card_shows_value"
             and getattr(n.func.value, "id", "") == "COMP"]
    ok(not local, "%s: never calls COMP.card_shows_value directly for rails "
                  "(uses rails_card_shows_value) — %d direct call(s)" % (fname, len(local)))

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
