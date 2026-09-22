#!/usr/bin/env python3.12
"""A verdict posts text it can NAME — never text the system substitutes. Zero LLM,
zero network, zero spend: every posting surface is stubbed and recorded.

★★ WHY THIS SUITE EXISTS. On 2026-09-18 Ashton ran tweak -> edit -> contrast flag
-> override on p_34f18679da. `override` called decide() with final_text=None, and
decide() posted st["text"] — the ORIGINAL DRAFT — because the edit that hit the
contrast gate had never been stored as the proposal's text. It would have
published the machine's words in place of the operator's, with no error and no
trace, on a surface where posts cannot be retracted. A second defect (the contrast
message was not a reply address, so the override never routed) is the only reason
it did not post.

The rule, ruled: `override` means POST WHAT YOU JUST SHOWED ME. Extended to its
own logic: a bare verdict after a refused edit names no text, so it is REFUSED
rather than falling back to the draft. Section 6 is the property: across every
path here, the posted text is always one the operator sent or was shown on the
contrast message — never the draft once an edit exists.
"""
import json, shutil, sys, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import switches as _SW  # noqa: E402
# This suite tests the IMAGE path (contrast gate / media). Pin the switch ON so its
# result never depends on the live .env (IMAGES_ENABLED=false since 2026-09-22).
_SW.images_enabled = lambda env=None: True
import telegram_bot as TB  # noqa: E402

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

DRAFT = "Swarovski crystals set into the grey leather Swoosh and heel on the AJ1 Retro Low OG 'Shadow'."
EDIT = "This Jordan 1 low has " + DRAFT
CTX = {"image_name": "jordan_1_retro_low_og_shadow", "rarity": "Uncommon",
       "composition": "shoe_crop", "contrast": {"ratio": 1.325, "band": "flag"}}

POSTED, SENT = [], []
def stub():
    POSTED.clear(); SENT.clear()
    def send_text(e, text, reply_to=None, parse_mode=None):
        SENT.append(text); return {"message_id": 5000 + len(SENT)}
    TB.send_text = send_text
    TB.X.posts_last_24h = lambda: 0
    TB.X.load_env = lambda p: {}
    TB.X.ledger_append = lambda r: None
    TB.X.upload_media = lambda p, env: "m"
    def create_tweet(text, mids, env):
        POSTED.append(text); return {"status": 201, "raw": json.dumps({"data": {"id": "1"}})}
    TB.X.create_tweet = create_tweet

def fresh(rows=()):
    TB.PROPOSAL_LEDGER = Path(tempfile.mkdtemp()) / "p.jsonl"
    TB.ledger({"event": "proposed", "proposal_id": "p", "text": DRAFT, "image": "i.png",
               "message_id": 10, "rails_ctx": CTX})
    for r in rows: TB.ledger({"proposal_id": "p", **r})
    stub()

def rows():
    return [json.loads(l) for l in TB.PROPOSAL_LEDGER.read_text().splitlines()]

def ev(name):
    return [r for r in rows() if r["event"] == name]

print("\n=== 1. THE p_34f18679da PATH — edit, contrast flag, override ===")
fresh()
TB.decide({}, "p", "approve", EDIT, 11)                      # edit -> contrast flag
cb = ev("contrast_blocked")
ok(len(cb) == 1 and cb[0]["text"] == EDIT, "contrast_blocked records the EXACT text it blocked")
ok(cb[0]["edited"] is True, "…and says it was an edit")
ok("Text held for override" in SENT[-1] and EDIT in SENT[-1],
   "the contrast message QUOTES the text override will post")
ok(POSTED == [], "nothing posted by the flag")
TB.decide({}, "p", "approve", None, 12, overridden=True)      # override
ok(POSTED == [EDIT], "override posts EXACTLY the edit: %r" % (POSTED[0][:40] if POSTED else None))
ap = ev("approved")[0]
ok(ap["final_text"] == EDIT and ap["edited"] is True, "approved row: final_text = the edit, edited=True")
ok(ap["contrast"] == {"ratio": 1.325, "band": "flag", "overridden": True},
   "approved row carries {ratio, band, overridden: true} as ruled")
ok(ev("posted")[0]["final_text"] == EDIT, "posted row final_text = the edit")

print("\n=== 2. LEGACY ROWS (pre-fix contrast_blocked carries no text) ===")
fresh([{"event": "edit_received", "original_text": DRAFT, "edited_text": EDIT, "diff": []},
       {"event": "contrast_blocked", "contrast": {"ratio": 1.325, "band": "flag",
                                                  "overridden": False}, "edited": True}])
TB.decide({}, "p", "approve", None, 12, overridden=True)
ok(POSTED == [EDIT], "edited legacy block -> text recovered from the edit_received before it")
fresh([{"event": "contrast_blocked", "contrast": {"ratio": 1.325, "band": "flag",
                                                  "overridden": False}, "edited": False}])
TB.decide({}, "p", "approve", None, 12, overridden=True)
ok(POSTED == [DRAFT], "un-edited legacy block -> it showed the draft, override posts the draft")
fresh([{"event": "contrast_blocked", "contrast": {"ratio": 1.325, "band": "flag",
                                                  "overridden": False}, "edited": True}])
TB.decide({}, "p", "approve", None, 12, overridden=True)
ok(POSTED == [], "edited legacy block with NO recoverable text -> override REFUSES, posts nothing")
ok(ev("bare_verdict_refused") and ev("bare_verdict_refused")[0]["why"] ==
   "contrast_blocked_text_unrecoverable", "…and says why on the ledger")

print("\n=== 3. THE REAL LEDGER — the queued override, replayed on a copy ===")
real = REPO / "ledger/proposals.jsonl"
if real.exists() and '"p_34f18679da"' in real.read_text():
    TB.PROPOSAL_LEDGER = Path(tempfile.mkdtemp()) / "p.jsonl"
    shutil.copy(real, TB.PROPOSAL_LEDGER); stub()
    st = TB.proposal_state()["p_34f18679da"]
    if st["status"] == "pending":
        TB.decide({}, "p_34f18679da", "approve", None, 1, overridden=True)
        ok(POSTED and POSTED[0].startswith("This Jordan 1 low has"),
           "p_34f18679da override posts Ashton's edit, not the draft")
    else:
        print("  SKIP  p_34f18679da is %s — the replay only applies while pending" % st["status"])
else:
    print("  SKIP  p_34f18679da not in this ledger")

print("\n=== 4. A BARE VERDICT AFTER A REFUSED EDIT NAMES NO TEXT -> REFUSED ===")
for verdict_kw, label in (({}, "approve"), ({"overridden": True}, "override")):
    fresh()
    TB.decide({}, "p", "approve", "x " * 200, 11)            # too long: refused edit
    TB.decide({}, "p", "approve", None, 12, **verdict_kw)
    ok(POSTED == [], "bare `%s` after a too-long edit posts NOTHING (not the draft)" % label)
    r = ev("bare_verdict_refused")
    ok(r and r[-1]["verdict"] == label, "…bare_verdict_refused recorded for %s" % label)
    ok("tweak" in SENT[-1], "…and the reply points at tweak")
fresh()
TB.decide({}, "p", "approve", "Place your bet on the grey Swoosh.", 11)   # rails-refused edit
TB.decide({}, "p", "approve", None, 12)
ok(POSTED == [], "bare approve after a RAILS-refused edit posts nothing either")

print("\n=== 5. UNCHANGED PATHS STAY UNCHANGED ===")
fresh(); CTX_OK = dict(CTX, contrast={"ratio": 3.0, "band": "ok"})
TB.PROPOSAL_LEDGER.write_text(""); TB.ledger({"event": "proposed", "proposal_id": "p",
    "text": DRAFT, "image": "i.png", "message_id": 10, "rails_ctx": CTX_OK})
TB.decide({}, "p", "approve", None, 12)
ok(POSTED == [DRAFT], "bare approve with no edits posts the draft, as before")
ok(ev("approved")[0]["edited"] is False, "…edited=False")
TB.PROPOSAL_LEDGER.write_text(""); TB.ledger({"event": "proposed", "proposal_id": "p",
    "text": DRAFT, "image": "i.png", "message_id": 10, "rails_ctx": CTX_OK}); POSTED.clear()
TB.decide({}, "p", "approve", EDIT, 12)
ok(POSTED == [EDIT], "an `edit:` that passes posts the edit, as before")
fresh([{"event": "contrast_blocked", "contrast": {"ratio": 1.325, "band": "flag",
       "overridden": False}, "edited": True, "text": "Place your bet on the grey Swoosh."}])
TB.decide({}, "p", "approve", None, 12, overridden=True)
ok(POSTED == [] and ev("rails_blocked"),
   "override skips ONLY the contrast gate — the held text still goes through the rails")

print("\n=== 6. THE PROPERTY — never the draft once an edit exists ===")
# Every scenario above that involved an edit either posted the operator's own words
# or posted nothing. Re-state it over a sweep so a future path is covered too.
for label, seq in {
    "edit->flag->override":     [("edit", EDIT), ("override", None)],
    "edit->flag->approve":      [("edit", EDIT), ("approve", None)],
    "longedit->approve":        [("edit", "x " * 200), ("approve", None)],
    "longedit->override":       [("edit", "x " * 200), ("override", None)],
    "flag->edit->flag->override": [("approve", None), ("edit", EDIT), ("override", None)],
}.items():
    fresh()
    edits = []
    for kind, t in seq:
        if kind == "edit":
            edits.append(t); TB.decide({}, "p", "approve", t, 1)
        else:
            TB.decide({}, "p", "approve", None, 1, overridden=(kind == "override"))
    ok(all(p in edits for p in POSTED) and DRAFT not in POSTED,
       "%-28s posted=%s" % (label, [p[:18] for p in POSTED] or "nothing"))

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
