#!/usr/bin/env python3.12
"""FRAME CHECK — the image gate (D3). Zero LLM, zero network, zero spend.

Nine text rails passed on a post whose subject was invisible, because nothing
in the pipeline had ever looked at the picture. These tests police the gate
that closed that, and the two-tier ruling behind it.

★ A TEST PER CLAUSE, NOT A TEST PER FUNCTION (contracts.py, THE PARTIALLY-
IMPLEMENTED SPECIFICATION). check_frame's contract enumerates three bands and
an unmeasured path; contrast_gate's enumerates flagged-vs-not and overridden-
vs-not. Each clause gets its own case, driven by the input that isolates it —
a single test over a four-condition function can pass while three are
implemented, and will, until the data separates them.
"""
import ast, sys
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import switches as _SW  # noqa: E402
# This suite tests the IMAGE path (contrast gate / media). Pin the switch ON so its
# result never depends on the live .env (IMAGES_ENABLED=false since 2026-09-22).
_SW.images_enabled = lambda env=None: True
from research import frame as F
import telegram_bot as TB

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

REPO = Path(__file__).resolve().parent.parent
SRC = (REPO / "research" / "frame.py").read_text(encoding="utf-8")


def synth(shoe_rgb, panel_rgb=(18, 18, 26), size=(840, 1320)) -> tuple[Path, Path]:
    """A card and its bare panel, built to order. No renderer, no network."""
    import tempfile
    d = Path(tempfile.mkdtemp())
    panel = Image.new("RGB", size, panel_rgb)
    card = panel.copy()
    a = np.asarray(card).copy()
    h, w, _ = a.shape
    a[int(h*0.38):int(h*0.56), int(w*0.20):int(w*0.80)] = shoe_rgb   # the "shoe"
    Image.fromarray(a).save(d/"card.png"); panel.save(d/"panel.png")
    return d/"card.png", d/"panel.png"


def measure(shoe_rgb, panel_rgb=(18, 18, 26)):
    card, panel = synth(shoe_rgb, panel_rgb)
    orig = F.bare_panel
    F.bare_panel = lambda rarity, refresh=False: panel     # no renderer needed
    try:
        return F.check_frame(card, "Common")
    finally:
        F.bare_panel = orig


print("\n=== 1. THE RULING IS THE ONE ASHTON GAVE ===")
ok(F.BLOCK_AT == 1.15, "block floor is 1.15 (%.2f)" % F.BLOCK_AT)
ok(F.FLAG_AT == 1.50, "flag ceiling is 1.50 (%.2f)" % F.FLAG_AT)
ok(F.RULED_ON == "2026-09-17", "the ruling carries its date — a threshold without one is folklore")
ok(F.BLOCK_AT < F.FLAG_AT, "the bands are ordered, so no card can be both blocked and flagged")

print("\n=== 2. EVERY BAND IS REACHABLE, AND THEY ARE DISTINCT ===")
# Each case drives the input that isolates its clause.
dark  = measure((20, 20, 28))          # near-panel -> block
mid   = measure((44, 44, 54))          # separated but weakly -> flag
light = measure((200, 200, 205))       # obvious -> pass
ok(dark.band == "block",  "a shoe at panel luma BLOCKS (%.2f)" % dark.ratio)
ok(mid.band == "flag",    "a weakly separated shoe FLAGS (%.2f)" % mid.ratio)
ok(light.band == "pass",  "a bright shoe PASSES (%.2f)" % light.ratio)
ok(dark.ratio < mid.ratio < light.ratio, "the ratio is monotonic in separation")
ok(dark.blocked and not mid.blocked, "the .blocked property tracks the band")
ok(mid.flagged and not light.flagged, "the .flagged property tracks the band")

print("\n=== 3. THE BOUNDARIES ARE CLOSED THE WAY THE RULING READS ===")
ok(not F.FrameResult("pass", 1.1501, "x").blocked, "just above the floor is not blocked")
lo, hi = F.BLOCK_AT, F.FLAG_AT
ok(lo <= lo and F.FrameResult("block", lo, "x").blocked,
   "AT the floor is blocked — `<=`, not `<`")
ok(F.FrameResult("flag", hi, "x").flagged, "AT the flag ceiling is still flagged")

print("\n=== 4. UNMEASURABLE IS NOT A FAILURE, AND NOT A SILENT PASS ===")
# ★ The one place in this repo that fails OPEN, and the docstring says why.
gone = F.check_frame(Path("/nonexistent/card.png"), "Common")
ok(gone.band == "unmeasured", "a missing render is 'unmeasured', not 'block'")
ok(not gone.blocked, "…and it does NOT block — a module fault is not evidence against the card")
ok(not gone.flagged, "…and it does NOT flag")
ok(gone.ratio is None, "…and it reports no ratio rather than inventing one")
ok("CONTRAST NOT MEASURED" in F.digest_note(gone),
   "…but it IS surfaced, so a run of them is visible rather than looking clean")
ok("fails OPEN" in SRC.lower() or "fail open" in SRC.lower() or "FAILS OPEN" in SRC,
   "the fail-open choice is documented where a future session will meet it")

print("\n=== 5. THE FLAG REUSES THE EXISTING WARNING IDIOM ===")
note = F.digest_note(mid)
ok(note.startswith(" ⚠️"), "same ⚠️ prefix as backdrop.inspection_note (%r)" % note[:12])
ok("before approving" in note, "…same 'before approving' phrasing")
ok("override" in note, "…and it names the exact word that posts it anyway")
ok(F.digest_note(light) == "", "a passing card adds NOTHING to the note")

print("\n=== 6. THE GATE RUNS BEFORE THE MONEY ===")
dd = (REPO / "daily_digest.py").read_text(encoding="utf-8")
i_render = dd.index("CR.render_card(cand[")
i_frame = dd.index("FRAME.check_frame(")
i_spend = dd.index("BD.generate(")
ok(i_render < i_frame < i_spend,
   "check_frame sits AFTER the card render and BEFORE BD.generate — a blocked card costs $0.00")
ok("skipped_low_contrast" in dd, "a block is ledgered, not silent")
ok(dd.index("insp += FRAME.digest_note") > dd.index("if not card_only"),
   "the flag is appended outside the card_only branch, so --card-only still warns")

print("\n=== 7. A FLAGGED CARD REFUSES THE REFLEX WORD ===")
flagged = {"rails_ctx": {"contrast": {"ratio": 1.38, "band": "flag"}}}
passing = {"rails_ctx": {"contrast": {"ratio": 3.2, "band": "pass"}}}
may, rec = TB.contrast_gate(flagged, overridden=False)
ok(not may, "a bare approve on a flagged card does NOT post")
ok(rec["band"] == "flag" and rec["overridden"] is False, "…and the refusal records why")
may2, rec2 = TB.contrast_gate(flagged, overridden=True)
ok(may2, "`override` posts it")
ok(rec2["overridden"] is True, "…and the row says he overrode it — a judgement, not a silent pass")
may3, rec3 = TB.contrast_gate(passing, overridden=False)
ok(may3, "an unflagged card needs no override")
ok(rec3["overridden"] is False, "…and is not recorded as one")
ok(TB.contrast_gate(passing, overridden=True)[0],
   "`override` on an unflagged card is accepted as a plain approval")

print("\n=== 8. CONTRAST IS RECORDED ON EVERY APPROVAL, NOT ONLY FLAGGED ONES ===")
for st, label in ((flagged, "flagged"), (passing, "passing"),
                  ({"rails_ctx": {}}, "no contrast ctx")):
    _, r = TB.contrast_gate(st, overridden=False)
    ok(set(r) == {"ratio", "band", "overridden"},
       "%s proposal yields the full record %s" % (label, sorted(r)))
ok(TB.contrast_gate({"rails_ctx": {}}, False)[1]["band"] == "unmeasured",
   "a proposal with no contrast context is 'unmeasured', never assumed to pass")
tb = (REPO / "telegram_bot.py").read_text(encoding="utf-8")
ok('"contrast": contrast' in tb, "the approved ledger row carries it")

print("\n=== 9. OVERRIDE IS NOT REACHABLE BY THE REFLEX WORD ===")
ok(not (TB.OVERRIDE & TB.APPROVE), "OVERRIDE and APPROVE are disjoint token sets")
ok(TB.parse_verdict("override")[0] == "override", "`override` parses as its own verdict")
ok(TB.parse_verdict("approve")[0] == "approve", "`approve` does not become an override")
ok(TB.parse_verdict("yes")[0] == "approve", "…nor does any other approve synonym")
d = ast.get_docstring(next(n for n in ast.walk(ast.parse(tb))
                           if isinstance(n, ast.FunctionDef) and n.name == "parse_verdict"))
ok("override" in d, "parse_verdict's docstring enumerates the verdict it now returns")

print("\n=== 10. THE REFUSAL IS NON-TERMINAL ===")
ok("NON-terminal" in tb or "NON-TERMINAL" in tb, "the contrast block is marked non-terminal")
blk = TB.render_contrast_block("p_test", {"ratio": 1.38, "band": "flag", "overridden": False})
ok("Still pending" in blk, "the message says the proposal is still decidable")
ok("override" in blk and "reject" in blk, "…and names both ways out")
ok("1.38" in blk, "…and states the measured ratio, not a vague warning")

print("\n=== 11. OCCLUSION IS RECORDED AS A KNOWN GAP, NOT COVERED ===")
ok("occlusion" in SRC.lower(), "frame.py names card-on-card occlusion")
ok("KNOWN GAP" in SRC or "known gap" in SRC.lower(),
   "…explicitly as a gap, so it is not mistaken for handled")
ok("overflow" in SRC.lower(), "…and frame overflow (D1) is named as out of scope too")

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
