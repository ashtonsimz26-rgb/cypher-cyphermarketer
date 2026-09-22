#!/usr/bin/env python3.12
"""IMAGES_ENABLED — the one image switch (2026-09-22). Zero LLM, zero network, zero spend.

Ashton asked for proposals to go TEXT ONLY, reversibly, by one setting. What this
suite holds, section by section:

  1. the switch parses strictly — a typo reads as DISABLED, never as "images on"
  2. with images off, build_one makes a complete proposal while EVERY image
     function (card render, Frame Check, both backdrop providers, compositor)
     is stubbed to RAISE — so any call would fail this suite — and the Frame
     Check skip is RECORDED, not silent
  3. the Telegram proposal goes out as sendMessage (never sendPhoto) and still
     carries the proposal id, the draft and the reply grammar
  4. approve / override / edit: / reject / tweak all still work, and posting
     sends NO media (upload_media stubbed to raise)
  5. an IMAGE proposal made before the switch flipped posts text-only after it,
     and the posted row says so (text_only + the drafted composition)
  6. flipping the switch back ON restores the image path: sendPhoto, one media
     upload, the drafted composition on the posted row
  7. rotation and the format report take the new value without crashing and
     without counting it as an image composition

The rails side (draft door == approve door for text_only) lives in
test_rails_door_parity.py beside the other compositions, where it belongs.
"""
import json, sys, tempfile
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import switches as SW                      # noqa: E402
import daily_digest as DD                  # noqa: E402
import telegram_bot as TB                  # noqa: E402
import x_client as X                       # noqa: E402
import format_report as FR                 # noqa: E402
from research import composition as COMP   # noqa: E402
from research import rotation as ROT       # noqa: E402

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

TMP = Path(tempfile.mkdtemp())
# A real reachable pair (the parity suite's) so the OBTAINABLE rail passes for
# real, and a lead that needs no attribution once no card is shown.
IMAGE, RARITY = "jordan_1_retro_low_og_shadow", "Uncommon"
LEAD = "Swarovski crystals set into the grey leather Swoosh on the AJ1 Low 'Shadow'."

class ImageCall(AssertionError):
    pass
def forbid(name):
    def _f(*a, **k):
        raise ImageCall("image function called with IMAGES_ENABLED=false: %s" % name)
    return _f

REAL_SWITCH = SW.images_enabled
def set_images(on: bool):
    SW.images_enabled = (lambda env=None: on)

# ══ 1. the switch parses strictly ════════════════════════════════════════════
print("\n=== 1. IMAGES_ENABLED parsing ===")
ok(REAL_SWITCH({}) is SW.IMAGES_ENABLED_DEFAULT is True, "absent -> the code default (True)")
for v in ("false", "FALSE", "0", "no", "off", " false "):
    ok(REAL_SWITCH({"IMAGES_ENABLED": v}) is False, "%r -> disabled" % v)
for v in ("true", "True", "1", "yes", "on"):
    ok(REAL_SWITCH({"IMAGES_ENABLED": v}) is True, "%r -> enabled" % v)
for v in ("flase", "", "maybe", "2"):
    ok(REAL_SWITCH({"IMAGES_ENABLED": v}) is False,
       "typo %r -> DISABLED (a typo must never turn image spend back on)" % v)

# ══ 2. build_one with images OFF, every image function forbidden ═════════════
print("\n=== 2. build_one, images OFF — no render, no backdrop, no Frame Check ===")
DD.RUNS = TMP / "runs.jsonl"
DD.OUT = TMP / "content"; DD.OUT.mkdir()
for mod, names in ((DD.CR, ("render_card",)), (DD.FRAME, ("check_frame",)),
                   (DD.BD, ("generate", "_generate_openai", "_generate_xai", "record_verdict")),
                   (DD.COMP, ("render",))):
    for n in names:
        setattr(mod, n, forbid("%s.%s" % (mod.__name__, n)))
# network / LLM / state inputs replaced with fixed ones (not under test here)
DD.DOS.dossier_proposable = lambda n: True
DD.CR.fetch_card = lambda img, rar: {"brand": "Jordan", "name": "Air Jordan 1 Retro Low OG",
                                     "colorway": "Shadow", "style_code": "TEST-1",
                                     "estimated_resale": 150, "is_set_reward": False}
DD.rails.price_claim_allowed = lambda sc, er: (False, "stub")
DD.editorial.detect_hook = lambda *a, **k: ("cultural_moment", "stub hook")
DD.editorial.choose_format = lambda h: "story_spotlight"
DD.editorial.lead_is_specific = lambda t, r: (True, "stub lead")
DD.editorial.record_format = lambda f: None
DD.ST.brief = lambda *a, **k: {"scene_key": None, "source": "test", "fallback_fired": False,
                               "shared_tokens": 1, "fact_id": "f1"}
DD.BD.scene_for = lambda row, key=None: ("scene", "category_fallback", "")
draft_fn = lambda ctx, attempt, failed: {"lead": LEAD, "body": None, "fact_id": "f1"}

set_images(False)
built = None
try:
    built = DD.build_one({"image_name": IMAGE, "rarity": RARITY}, card_only=False,
                         draft_fn=draft_fn)
    ok(True, "build_one completed with every image function stubbed to raise")
except ImageCall as ex:
    ok(False, str(ex))
ok(built is not None, "a proposal was built (not skipped)")
if built:
    ok(built["image"] is None, "image is None")
    ok(built["composition"] == COMP.TEXT_ONLY, "composition = text_only")
    ok(built["rails_ctx"]["composition"] == COMP.TEXT_ONLY, "rails_ctx.composition = text_only")
    ok(built["rails_ctx"]["contrast"] == {"ratio": None, "band": "skipped_text_only"},
       "rails_ctx.contrast records the SKIP (band skipped_text_only), not a pass")
    ok("SKIPPED" in built["insp"], "the proposal note says the Frame Check was skipped")
    ok(Path(built["text_file"]).read_text() == LEAD,
       "the draft carries no attribution sentence (card_shows_value False)")
runs = [json.loads(l) for l in DD.RUNS.read_text().splitlines()]
ok(any(r["event"] == "frame_check_skipped" for r in runs), "a frame_check_skipped row is ledgered")
ok(any(r["event"] == "draft_built" and r["composition"] == COMP.TEXT_ONLY for r in runs),
   "draft_built records composition text_only")

# ══ 3. the Telegram proposal is TEXT ═════════════════════════════════════════
print("\n=== 3. propose — sendMessage, never sendPhoto ===")
calls = []
def fake_call(url, data=None, ct=None):
    calls.append((url.rsplit("/", 1)[-1], data))
    return 200, {"ok": True, "result": {"message_id": 700 + len(calls)}}
TB._call = fake_call
TB.PROPOSAL_LEDGER = TMP / "proposals.jsonl"
# state/reject_reasons.json feeds the drafter; a test reject must never land there
TB.REJECT_REASONS = TMP / "reject_reasons.json"
E = {"CYPHERMARKETER_TELEGRAM_BOT_TOKEN": "t", "CYPHERMARKETER_TELEGRAM_CHAT_ID": "1"}
argv = SimpleNamespace(text_file=str(built["text_file"]), image=None, note="digest · test",
                       rails_ctx=built["rails_ctx"], format=built["format"],
                       hook_type=built["hook_type"], composition=built["composition"],
                       tier=RARITY)
pid = TB.cmd_propose(argv, E)
ok([c[0] for c in calls] == ["sendMessage"], "exactly one sendMessage, no sendPhoto: %s"
   % [c[0] for c in calls])
body = json.loads(calls[0][1])["text"]
ok(pid in body, "message carries the proposal id")
ok(LEAD in body, "message carries the draft")
ok("Reply: approve · reject <reason> · edit: <new text>" in body, "message carries the reply grammar")
ok("TEXT ONLY" in body, "message says it is text only")
prow = json.loads(TB.PROPOSAL_LEDGER.read_text().splitlines()[-1])
ok(prow["image"] is None and prow["composition"] == COMP.TEXT_ONLY and prow["message_id"] == 701,
   "proposed row: image None, composition text_only, message_id recorded")

# a CLI propose that hands in an image while images are OFF: text sent anyway
img = TMP / "card.png"; img.write_bytes(b"\x89PNG fake")
calls.clear()
pid_cli = TB.cmd_propose(SimpleNamespace(text_file=str(built["text_file"]), image=str(img),
                                         note="cli", composition="shoe_crop"), E)
cli = json.loads(TB.PROPOSAL_LEDGER.read_text().splitlines()[-1])
ok([c[0] for c in calls] == ["sendMessage"], "CLI image + images OFF -> still text only")
ok(cli["composition"] == COMP.TEXT_ONLY and cli["proposed_composition"] == "shoe_crop"
   and cli["image"] is None, "…recorded as text_only, the handed-in composition kept beside it")

# ══ 4. every verdict still works; posting sends no media ═════════════════════
print("\n=== 4. approve / override / edit / reject / tweak — no media ===")
X.LEDGER = TMP / "posts.jsonl"
X.load_env = lambda p: {}
X.upload_media = forbid("x_client.upload_media")
X.posts_last_24h = lambda: 0
tweets = []
def fake_tweet(text, media_ids, env):
    tweets.append({"text": text, "media_ids": list(media_ids)})
    return {"status": 201, "raw": json.dumps({"data": {"id": "t%d" % len(tweets)}})}
X.create_tweet = fake_tweet
sent = []
TB.send_text = lambda e, text, reply_to=None, parse_mode=None: (sent.append(text) or {"message_id": 900})

def propose_text_only(text=LEAD):
    tf = TMP / ("d%d.txt" % len(sent)); tf.write_text(text)
    return TB.cmd_propose(SimpleNamespace(text_file=str(tf), image=None, note="t",
                                          rails_ctx=built["rails_ctx"], format="story_spotlight",
                                          hook_type="cultural_moment",
                                          composition=COMP.TEXT_ONLY, tier=RARITY), E)
def posted_rows(pid):
    a = [json.loads(l) for l in X.LEDGER.read_text().splitlines() if pid in l] if X.LEDGER.exists() else []
    b = [json.loads(l) for l in TB.PROPOSAL_LEDGER.read_text().splitlines() if pid in l]
    return [r for r in a + b if r.get("event") == "posted"]

try:
    p1 = propose_text_only(); TB.decide(E, p1, "approve", None, 1)
    ok(tweets[-1] == {"text": LEAD, "media_ids": []}, "approve -> text posted with NO media")
    rows = posted_rows(p1)
    ok(len(rows) == 2 and all(r["composition"] == COMP.TEXT_ONLY for r in rows),
       "approve -> both posted rows say composition text_only")
    ok(all("proposed_composition" not in r for r in rows), "…and carry no drafted-composition note (it WAS text_only)")
    ok(json.loads([l for l in X.LEDGER.read_text().splitlines() if p1 in l and '"posted"' in l][0])["media_ids"] == [],
       "posts.jsonl media_ids = []")
    appr = [json.loads(l) for l in TB.PROPOSAL_LEDGER.read_text().splitlines()
            if p1 in l and '"approved"' in l][0]
    ok(appr["contrast"]["band"] == "skipped_text_only", "approved row records the contrast SKIP")

    p2 = propose_text_only(); TB.decide(E, p2, "override", None, 1, overridden=True)
    ok(len(posted_rows(p2)) == 2 and tweets[-1]["media_ids"] == [], "override -> posts, no media")

    p3 = propose_text_only(); edited = LEAD.replace("grey", "cement-grey")
    TB.decide(E, p3, "edit", edited, 1)
    ok(tweets[-1] == {"text": edited, "media_ids": []}, "edit: -> the edited text posted, no media")

    p4 = propose_text_only(); n_before = len(tweets); TB.decide(E, p4, "reject", None, 1, reason="flat")
    ok(len(tweets) == n_before and "rejected" in sent[-1], "reject -> nothing posted, rejected")

    p5 = propose_text_only(); st = TB.proposal_state()[p5]; n_sent = len(sent)
    TB.send_tweak(E, st, 1)
    ok(len(sent) == n_sent + 1 and "Shadow" in sent[-1], "tweak -> the text comes back")
except ImageCall as ex:
    ok(False, str(ex))

# ══ 5. an IMAGE proposal approved after the switch went OFF ══════════════════
print("\n=== 5. image proposal made before the flip, approved after — posts text only ===")
calls.clear(); set_images(True)
ctx_img = {**built["rails_ctx"], "composition": "shoe_crop",
           "contrast": {"ratio": 1.2, "band": "flag"}}       # even a FLAGGED card
tf = TMP / "img_prop.txt"; tf.write_text(LEAD)
p6 = TB.cmd_propose(SimpleNamespace(text_file=str(tf), image=str(img), note="pre-flip",
                                    rails_ctx=ctx_img, format="story_spotlight",
                                    hook_type="cultural_moment", composition="shoe_crop",
                                    tier=RARITY), E)
ok([c[0] for c in calls] == ["sendPhoto"], "images ON at propose time -> sendPhoto")
set_images(False)
try:
    TB.decide(E, p6, "approve", None, 1)
    ok(tweets[-1] == {"text": LEAD, "media_ids": []}, "approved with images OFF -> text only, no upload")
    rows = posted_rows(p6)
    ok(len(rows) == 2 and all(r["composition"] == COMP.TEXT_ONLY
                              and r["proposed_composition"] == "shoe_crop" for r in rows),
       "posted rows: composition text_only, proposed_composition shoe_crop")
    appr = [json.loads(l) for l in TB.PROPOSAL_LEDGER.read_text().splitlines()
            if p6 in l and '"approved"' in l][0]
    ok(appr["contrast"]["band"] == "skipped_text_only" and appr["contrast"]["measured_band"] == "flag",
       "the contrast flag is SKIPPED (the card is not posted) and the measured flag is kept")
except ImageCall as ex:
    ok(False, str(ex))

# ══ 6. switch back ON — the image path is restored ═══════════════════════════
print("\n=== 6. IMAGES_ENABLED=true restores the image path ===")
set_images(True)
uploads = []
X.upload_media = lambda path, env: (uploads.append(str(path)) or "m1")
calls.clear()
p7 = TB.cmd_propose(SimpleNamespace(text_file=str(tf), image=str(img), note="on",
                                    rails_ctx={**built["rails_ctx"], "composition": "shoe_crop",
                                               "contrast": {"ratio": 3.0, "band": "pass"}},
                                    format="story_spotlight", hook_type="cultural_moment",
                                    composition="shoe_crop", tier=RARITY), E)
ok([c[0] for c in calls] == ["sendPhoto"], "propose -> sendPhoto")
TB.decide(E, p7, "approve", None, 1)
ok(uploads == [str(img)] and tweets[-1]["media_ids"] == ["m1"], "approve -> one upload, media attached")
rows = posted_rows(p7)
ok(len(rows) == 2 and all(r["composition"] == "shoe_crop" and "proposed_composition" not in r
                          for r in rows), "posted rows carry the drafted composition, unchanged")

# ══ 7. rotation and the report take the new value ════════════════════════════
print("\n=== 7. rotation + format report ===")
hist = [{"format": "story_spotlight", "hook_type": "x", "brand": "Jordan",
         "composition": COMP.TEXT_ONLY, "scene": "s"}] * 3
ok(ROT.composition_used_recently("shoe_crop", hist) is False,
   "text_only history never blocks an image composition")
d_ok, n = ROT.differs_enough({"format": "a", "hook_type": "b", "brand": "c",
                              "composition": "shoe_crop", "scene": "s"}, hist[0])
ok(isinstance(d_ok, bool), "differs_enough handles text_only without crashing (%d axes)" % n)
FR.RUNS = DD.RUNS
FR.PROPOSALS = TB.PROPOSAL_LEDGER
sig = FR.pipeline_signals(days=None)
ok(COMP.TEXT_ONLY not in sig["compositions"] and sig["n_text_only"] >= 1,
   "report: text_only is NOT in the image composition distribution (n_text_only=%d)"
   % sig["n_text_only"])
out = "\n".join(FR.render_signals(sig))
ok("text-only draft" in out, "report says how many text-only drafts it left out")
posted = [json.loads(l) for l in X.LEDGER.read_text().splitlines() if '"posted"' in l]
ok(FR.media_of("t1", posted) == "text_only" and FR.media_of("t%d" % len(tweets), posted) == "image",
   "media_of: a text-only post and an image post are told apart")

SW.images_enabled = REAL_SWITCH
print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
