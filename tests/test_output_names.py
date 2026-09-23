#!/usr/bin/env python3.12
"""content/ outputs are keyed by the proposal id, so two drafts never share a file.

Zero LLM, zero network, zero spend; every file lands in a scratch content/ dir.
The collision this closes: outputs were named {shoe}_{date}, so the digest and the
drops job drafting the SAME shoe on the SAME day would overwrite each other's card,
backdrop, composite and text. Now the id that names the files is minted at naming
time and handed to cmd_propose as the proposal's own id.
"""
import ast, json, sys, tempfile
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import switches as SW                      # noqa: E402
import daily_digest as DD                  # noqa: E402
import telegram_bot as TB                  # noqa: E402
from research import composition as COMP, frame as FRAME, dossier as DOS, story as ST  # noqa: E402
import card_render as CR, backdrop as BD, editorial, rails  # noqa: E402

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

T = Path(tempfile.mkdtemp())
DD.OUT = T / "content"; DD.OUT.mkdir()
DD.RUNS = T / "runs.jsonl"
TB.PROPOSAL_LEDGER = T / "proposals.jsonl"
TB.REJECT_REASONS = T / "reject_reasons.json"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
CR.fetch_card = lambda img, rar: {"brand": "Jordan", "name": "Air Jordan 1 Retro Low OG",
                                  "colorway": "Shadow", "style_code": "TEST-1",
                                  "estimated_resale": 150, "is_set_reward": False}
CR.render_card = lambda img, rar, out: out.write_bytes(PNG)
FRAME.check_frame = lambda card, rar: SimpleNamespace(blocked=False, ratio=3.0, band="pass", why="")
BD.generate = lambda prompt, aspect, out, env: out.write_bytes(PNG) or {}
BD.record_verdict = lambda *a, **k: None
BD.scene_for = lambda row, key=None: ("scene", "category_fallback", "")
COMP.render = lambda name, card, bd, out, ratio="4:5", card_b_path=None: out.write_bytes(PNG) or {}
DOS.dossier_proposable = lambda n: True
rails.price_claim_allowed = lambda sc, er: (False, "stub")
editorial.detect_hook = lambda *a, **k: ("cultural_moment", "stub hook")
editorial.choose_format = lambda h: "story_spotlight"
editorial.lead_is_specific = lambda t, r: (True, "stub lead")
editorial.record_format = lambda f: None
ST.brief = lambda *a, **k: {"scene_key": None, "source": "test", "fallback_fired": False,
                            "shared_tokens": 1, "fact_id": "f1"}
DD.X.load_env = lambda p: {}
LEAD = "Swarovski crystals set into the grey leather Swoosh on the AJ1 Low 'Shadow'."
draft_fn = lambda ctx, attempt, failed: {"lead": LEAD, "body": None, "fact_id": "f1"}
CAND = {"image_name": "jordan_1_retro_low_og_shadow", "rarity": "Uncommon"}

def outputs(b):
    return {Path(p) for p in (b["text_file"], b["image"]) if p} | \
           {p for p in DD.OUT.iterdir() if p.name.startswith(b["proposal_id"])}

print("\n=== 1. images ON: the same shoe drafted twice on the same day ===")
SW.images_enabled = lambda env=None: True
a = DD.build_one(dict(CAND), card_only=False, draft_fn=draft_fn)   # "the digest"
b = DD.build_one(dict(CAND), card_only=False, draft_fn=draft_fn)   # "the drops job"
ok(a["proposal_id"] != b["proposal_id"], "two drafts, two ids: %s / %s" % (a["proposal_id"], b["proposal_id"]))
fa, fb = outputs(a), outputs(b)
ok(len(fa) >= 4 and len(fb) >= 4, "each draft wrote its card, backdrop, composite and text (%d, %d)" % (len(fa), len(fb)))
ok(not (fa & fb), "the two drafts share NO file")
ok(all(p.exists() for p in fa | fb), "neither draft's files were overwritten or removed")
ok(all(p.name.startswith(x["proposal_id"]) for x, fs in ((a, fa), (b, fb)) for p in fs),
   "every output file name starts with its draft's proposal id")

print("\n=== 2. images OFF (text only): same property for the text file ===")
SW.images_enabled = lambda env=None: False
c = DD.build_one(dict(CAND), card_only=False, draft_fn=draft_fn)
d = DD.build_one(dict(CAND), card_only=False, draft_fn=draft_fn)
ok(c["proposal_id"] and d["proposal_id"] and c["text_file"] != d["text_file"],
   "two text-only drafts, two text files")
ok(Path(c["text_file"]).name.startswith(c["proposal_id"]), "text file named by its proposal id")

print("\n=== 3. cmd_propose uses the PRE-MINTED id, and refuses a reused one ===")
TB._call = lambda url, data=None, ct=None: (200, {"ok": True, "result": {"message_id": 1}})
E = {"CYPHERMARKETER_TELEGRAM_BOT_TOKEN": "t", "CYPHERMARKETER_TELEGRAM_CHAT_ID": "1"}
pid = TB.cmd_propose(SimpleNamespace(text_file=str(c["text_file"]), image=None, note="n",
                                     rails_ctx=c["rails_ctx"], format=c["format"],
                                     hook_type=c["hook_type"], composition=c["composition"],
                                     tier=CAND["rarity"], proposal_id=c["proposal_id"]), E)
row = json.loads(TB.PROPOSAL_LEDGER.read_text().splitlines()[-1])
ok(pid == c["proposal_id"] == row["proposal_id"], "the proposal IS the id that named its files: %s" % pid)
try:
    TB.cmd_propose(SimpleNamespace(text_file=str(c["text_file"]), image=None, note="n",
                                   proposal_id=c["proposal_id"]), E)
    ok(False, "a reused id should be refused")
except SystemExit:
    ok(True, "a reused proposal id is refused")
ok(TB.cmd_propose(SimpleNamespace(text_file=str(d["text_file"]), image=None, note="cli"), E)
   .startswith("p_"), "a CLI propose with no pre-minted id still mints one")

print("\n=== 4. structurally: no shoe+date name, and both propose sites pass the id ===")
src = (REPO / "daily_digest.py").read_text()
fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "build_one")
body = ast.get_source_segment(src, fn)
ok('strftime("%Y%m%d")' not in body, "build_one no longer names outputs by date")
ok("new_proposal_id()" in body, "build_one mints the id through telegram_bot.new_proposal_id")
for f, line in (("daily_digest.py", 'proposal_id=built.get("proposal_id")'),
                ("drop_correspondent.py", 'proposal_id = built.get("proposal_id")')):
    ok((REPO / f).read_text().count(line) == 1, "%s hands the pre-minted id to cmd_propose" % f)

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
