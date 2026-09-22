#!/usr/bin/env python3.12
"""`tweak` and `edit_received`. Zero LLM, zero network, zero spend.

`tweak` sends a proposal's current text back as a ready-to-send `edit:` line so
Ashton can change a phrase instead of retyping 280 characters. Three properties
matter, and this suite holds each one:

1. TWEAK HAS NO PATH TO A POST. It is a request, not a verdict. It produces text
   and nothing else — no decide(), no x_client, no approved/posted row. Checked
   behaviourally (every posting surface is booby-trapped) AND structurally (AST),
   because a behavioural test only covers the paths it happens to drive.

2. THE ROUND TRIP IS EXACT. What the code span displays, copied and sent back
   unchanged, must parse as `edit:` with the ORIGINAL text byte-for-byte —
   including backticks, backslashes, quotes and MarkdownV2 punctuation. An
   escaping bug here would silently alter copy that gets posted verbatim.

3. EVERY EDIT IS RECORDED BEFORE ANYTHING CAN REFUSE IT. Until 2026-09-18 a
   refused edit left no trace of its text. edit_received is written first, with
   the original preserved and the word diff, whether the edit then passes, is
   too long, fails rails, or targets an expired proposal.

An edit still re-runs the FULL rails at approval exactly as a fresh draft does:
tweak adds no new way through a gate, only a faster way to produce the text that
then goes through it.
"""
import ast, json, sys, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import switches as _SW  # noqa: E402
# This suite tests the IMAGE path (contrast gate / media). Pin the switch ON so its
# result never depends on the live .env (IMAGES_ENABLED=false since 2026-09-22).
_SW.images_enabled = lambda env=None: True
import telegram_bot as TB  # noqa: E402
import rails               # noqa: E402

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

def fresh_ledger():
    TB.PROPOSAL_LEDGER = Path(tempfile.mkdtemp()) / "proposals.jsonl"
    return TB.PROPOSAL_LEDGER

def rows():
    p = TB.PROPOSAL_LEDGER
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []

# ── booby-trap every posting surface: tweak must never reach one ─────────────
class Tripped(Exception): pass
def _trap(name):
    def f(*a, **k): raise Tripped(name)
    return f
REAL_DECIDE = TB.decide
TB.X.create_tweet = _trap("X.create_tweet")
TB.X.upload_media = _trap("X.upload_media")
TB.X.ledger_append = _trap("X.ledger_append")

MD2_SPECIAL = set("_*[]()~`>#+-=|{}.!")

def md2_valid(t):
    """A strict stand-in for Telegram's MarkdownV2 parser. Outside a code span
    every special character must be backslash-escaped; inside one, an unescaped
    backtick ENDS the span. A message that leaves a span open, or exposes an
    unescaped special outside one, is rejected — as Telegram rejects it.

    ★ This exists because the first version of this suite let ANY MarkdownV2
    through, and a mutation test proved it: with escaping deleted outright, the
    round-trip still passed. A fake more forgiving than the real API tests the
    fake, not the code."""
    in_code, i = False, 0
    while i < len(t):
        c = t[i]
        if c == "\\":
            i += 2; continue
        if c == "`":
            in_code = not in_code
        elif not in_code and c in MD2_SPECIAL:
            return False
        i += 1
    return not in_code

SENT = []
def fake_send(markdown_ok=True):
    def send_text(e, text, reply_to=None, parse_mode=None):
        if parse_mode and (not markdown_ok or not md2_valid(text)):
            return {}                                  # Telegram rejected the markup
        SENT.append({"text": text, "parse_mode": parse_mode, "reply_to": reply_to})
        return {"message_id": 9000 + len(SENT)}
    return send_text

def unescape_code(t):
    """What a Telegram client shows for a MarkdownV2 code span."""
    out, i = [], 0
    while i < len(t):
        if t[i] == "\\" and i + 1 < len(t) and t[i+1] in "\\`":
            out.append(t[i+1]); i += 2
        else:
            out.append(t[i]); i += 1
    return "".join(out)

def code_span(msg):
    body = msg.split("\n", 1)[1]
    assert body.startswith("`") and body.endswith("`"), body
    return unescape_code(body[1:-1])

print("\n=== 0. THE FAKE TELEGRAM IS STRICT ENOUGH TO TEST AGAINST ===")
ok(md2_valid("a\\.b `c\\`d`"), "accepts correctly escaped text + an escaped backtick in code")
ok(not md2_valid("a.b"), "rejects an unescaped '.' outside code")
ok(not md2_valid("x `a`b` y"), "rejects an unescaped backtick inside code (span closes early)")
ok(not md2_valid("x `open"), "rejects an unterminated code span")

print("\n=== 1. PARSER — tweak is its own request, and nothing else moved ===")
for body in ("tweak", "Tweak", "  TWEAK  "):
    ok(TB.parse_verdict(body)[0] == "tweak", "%r -> tweak" % body)
ok(TB.parse_verdict("tweak the lead")[0] == "unknown",
   "'tweak the lead' is NOT a tweak (exact token only) -> unknown, a no-op")
ok(TB.parse_verdict("approve")[0] == "approve" and TB.parse_verdict("edit: x")[0] == "edit",
   "approve and edit: unchanged")
ok("tweak" in TB.HELP, "HELP lists tweak, so a mistyped reply teaches it")

print("\n=== 2. NO PATH FROM TWEAK TO A POST — behavioural ===")
fresh_ledger()
TB.decide = _trap("decide")
TB.send_text = fake_send(markdown_ok=True)
TB.ledger({"event": "proposed", "proposal_id": "p_a", "text": "Draft A.", "message_id": 100})
target = TB.proposal_state()["p_a"]
try:
    TB.send_tweak({}, target, 555); tripped = None
except Tripped as t:
    tripped = str(t)
ok(tripped is None, "send_tweak reached no posting surface (tripped: %s)" % tripped)
ev = [r["event"] for r in rows()]
ok(ev == ["proposed", "tweak_sent"], "ledger gained exactly one tweak_sent row: %s" % ev)
ok(not {"approved", "posted", "failed", "rails_blocked", "edit_received"} & set(ev),
   "no verdict, post or edit event was written by a tweak")
ok(TB.proposal_state()["p_a"]["status"] == "pending", "the proposal is still pending")
TB.decide = REAL_DECIDE

print("\n=== 3. NO PATH FROM TWEAK TO A POST — structural ===")
tree = ast.parse((REPO / "telegram_bot.py").read_text())
fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "send_tweak")
calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
names = {getattr(c.func, "id", None) or getattr(c.func, "attr", None) for c in calls}
ok("decide" not in names, "send_tweak never calls decide()")
ok(not any(isinstance(c.func, ast.Attribute) and getattr(c.func.value, "id", "") == "X"
           for c in calls), "send_tweak never calls anything on x_client")
consts = {n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
ok(not consts & {"approved", "posted", "approve"},
   "send_tweak contains no approved/posted/approve literal it could write")
poll = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "cmd_poll")
branch = next((n for n in ast.walk(poll) if isinstance(n, ast.If)
               and isinstance(n.test, ast.Compare)
               and any(isinstance(c, ast.Constant) and c.value == "tweak"
                       for c in n.test.comparators)), None)
ok(branch is not None, "cmd_poll has an explicit tweak branch")
if branch:
    bcalls = {getattr(c.func, "id", None) or getattr(c.func, "attr", None)
              for c in ast.walk(ast.Module(body=branch.body, type_ignores=[])) if isinstance(c, ast.Call)}
    # `.get` is a dict read on the incoming message (m.get("message_id")), not an action.
    ok(bcalls - {"get"} == {"send_tweak"},
       "…whose body calls send_tweak and nothing else (dict reads aside): %s" % bcalls)
    ok(any(isinstance(n, ast.Continue) for n in branch.body),
       "…and ends in `continue` — it cannot fall through to the approve/edit handling")

print("\n=== 4. ROUND TRIP — copy the code span, send it back, get the text EXACTLY ===")
HARD = [
    "Swarovski crystals set into the grey leather Swoosh and heel on the AJ1 Retro Low OG 'Shadow'.",
    "Nike SB x Staple 'Pigeon' (2005) — the one that made the news. 1/1? No. 150.",
    "back`tick and back\\slash and *stars* _unders_ [brackets] (parens) ~tilde > # + - = | { } . !",
]
for t in HARD:
    fresh_ledger(); SENT.clear()
    TB.send_text = fake_send(markdown_ok=True)
    TB.ledger({"event": "proposed", "proposal_id": "p_r", "text": t, "message_id": 1})
    TB.send_tweak({}, TB.proposal_state()["p_r"], 2)
    m = SENT[-1]
    ok(m["parse_mode"] == "MarkdownV2", "sent as MarkdownV2")
    shown = code_span(m["text"])
    v, payload, _ = TB.parse_verdict(shown)
    ok(v == "edit" and payload == t, "round-trips byte-for-byte: %r" % t[:48])

print("\n=== 5. FALLBACK — markup refused, plain message is EXACTLY the edit line ===")
fresh_ledger(); SENT.clear()
TB.send_text = fake_send(markdown_ok=False)
TB.ledger({"event": "proposed", "proposal_id": "p_f", "text": HARD[2], "message_id": 1})
TB.send_tweak({}, TB.proposal_state()["p_f"], 2)
ok(len(SENT) == 1 and SENT[0]["parse_mode"] is None, "fell back to one plain message")
ok(SENT[0]["text"] == "edit: " + HARD[2],
   "plain body is exactly `edit: <text>` — a long-press copies precisely the command")
ok(TB.parse_verdict(SENT[0]["text"]) == ("edit", HARD[2], None), "…and it parses back exactly")
tw = [r for r in rows() if r["event"] == "tweak_sent"][-1]
ok(tw["mode"] == "plain_fallback", "tweak_sent records the fallback mode")

print("\n=== 6. ROUTING — a reply to the TWEAK message finds its proposal ===")
fresh_ledger(); SENT.clear()
TB.send_text = fake_send(markdown_ok=True)
TB.ledger({"event": "proposed", "proposal_id": "p_1", "text": "One.", "message_id": 11})
TB.ledger({"event": "proposed", "proposal_id": "p_2", "text": "Two.", "message_id": 22})
res = TB.send_tweak({}, TB.proposal_state()["p_2"], 22)
st = TB.proposal_state()
ok(TB.resolve_target(st, None) is None, "two pending, no reply: unresolved (unchanged behaviour)")
ok(TB.resolve_target(st, 11)["proposal_id"] == "p_1", "reply to proposal 1's message -> p_1")
ok(TB.resolve_target(st, res["message_id"])["proposal_id"] == "p_2",
   "reply to p_2's TWEAK message -> p_2, with two pending")
ok(st["p_2"]["status"] == "pending", "tweak_sent changed no status")

print("\n=== 6b. ...and so does a reply to a RAILS-BLOCK message ===")
fresh_ledger()
TB.send_text = lambda *a, **k: {"message_id": 777}
TB.ledger({"event": "proposed", "proposal_id": "p_x", "text": "Other.", "message_id": 31})
TB.ledger({"event": "proposed", "proposal_id": "p_b", "text": "The grey leather Swoosh.",
           "message_id": 32, "rails_ctx": {"image_name": "jordan_1_retro_low_og_shadow",
                                            "rarity": "Uncommon", "composition": "shoe_crop"}})
TB.decide({}, "p_b", "approve", "Place your bet on it.", 33)
st = TB.proposal_state()
ok(TB.resolve_target(st, 777)["proposal_id"] == "p_b",
   "reply `tweak` to the block message -> p_b, with two pending")
ok(st["p_b"]["status"] == "pending", "the block is still non-terminal")
ok("tweak" in TB.render_rails_block("p_b", []), "the block message offers tweak")

print("\n=== 7. edit_received — written FIRST, whatever happens next ===")
TB.send_text = lambda *a, **k: {"message_id": 1}
def run_edit(pid, text, **proposed):
    fresh_ledger()
    TB.ledger({"event": "proposed", "proposal_id": pid, "text": "The grey leather Swoosh.",
               "message_id": 5, **proposed})
    TB.decide({}, pid, "approve", text, 6)
    return rows()

too_long = "x " * 200
r = run_edit("p_long", too_long)
ev = [x["event"] for x in r]
ok(ev[1:3] == ["edit_received", "edit_too_long"], "too long: edit_received THEN edit_too_long %s" % ev)
er = r[1]
ok(er["edited_text"] == too_long and er["original_text"] == "The grey leather Swoosh.",
   "the refused text is on the ledger, beside the original")

bad = "Place your bet on the grey leather Swoosh."
r = run_edit("p_rails", bad, rails_ctx={"image_name": "jordan_1_retro_low_og_shadow",
                                        "rarity": "Uncommon", "composition": "shoe_crop"})
ev = [x["event"] for x in r]
ok(ev[1:3] == ["edit_received", "rails_blocked"], "rails refusal: edit_received THEN rails_blocked %s" % ev)
ok(r[1]["edited_text"] == bad, "…and the blocked wording is preserved — it used to be discarded")
ok(r[1]["diff"] == [{"op": "replace", "from": "The", "to": "Place your bet on the"}],
   "…with the word diff: %s" % r[1]["diff"])
blk = next(x for x in r if x["event"] == "rails_blocked")
ok(blk.get("edited") is True and "NO_GAMBLING" in blk["failed"],
   "the edit went through the FULL rails, exactly as a fresh draft does")

fresh_ledger()
TB.ledger({"event": "proposed", "proposal_id": "p_old", "text": "Old.", "message_id": 5})
TB.ledger({"event": "expired", "proposal_id": "p_old"})
TB.decide({}, "p_old", "approve", "Old, reworded.", 6)
er = [x for x in rows() if x["event"] == "edit_received"]
ok(len(er) == 1 and er[0]["status_at_receipt"] == "expired",
   "an edit to an EXPIRED proposal is still recorded (status_at_receipt=expired)")
ok(not any(x["event"] == "posted" for x in rows()), "…and still posts nothing")

print("\n=== 8. tweak hands back the LATEST wording, not the stale draft ===")
fresh_ledger(); SENT.clear()
TB.send_text = fake_send(markdown_ok=True)
TB.ledger({"event": "proposed", "proposal_id": "p_w", "text": "Draft.", "message_id": 5})
TB.ledger({"event": "edit_received", "proposal_id": "p_w", "original_text": "Draft.",
           "edited_text": "My reworded line.", "diff": []})
TB.send_tweak({}, TB.proposal_state()["p_w"], 6)
ok(code_span(SENT[-1]["text"]) == "edit: My reworded line.",
   "after a refused edit, tweak returns the operator's last wording")
ok([x for x in rows() if x["event"] == "tweak_sent"][-1]["source"] == "last_edit",
   "…and says so on the ledger (source=last_edit)")

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
