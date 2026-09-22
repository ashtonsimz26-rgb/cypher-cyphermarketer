#!/usr/bin/env python3.12
"""Every bot message that invites a reply is an ADDRESS for its proposal. Zero LLM,
zero network, zero spend.

★★ WHY THIS SUITE EXISTS. Replies route by reply-to message id, else by a sole
pending proposal. A message that tells Ashton to reply, but is not registered as
an address, silently fails the moment two proposals are pending: the reply gets
"reply to the one you mean". The rails-block and too-long messages were made
addresses; the contrast-block message was not, and that is why the 2026-09-18
override on p_34f18679da never routed. The audit that followed found TWO MORE
un-addressed inviters nobody had reported — the 4-post cap message ("approve
again once it clears") and the help message ("Reply to a proposal with…").

Fixing instances leaves the set free to grow an un-addressed member. So this
suite measures the SET: it enumerates EVERY send site by AST — in the bot and in
every other script that sends through it — and requires each to be classified.
An unclassified site fails. An inviting site that is not wrapped in _alias (or is
not one of the two self-addressing senders) fails. Adding a message now forces a
decision about whether it invites a reply.
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

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

# (enclosing function, distinctive source fragment) -> class
#   ADDRESS  invites a reply -> must be _alias-wrapped
#   SELF     invites a reply and registers its own address (proposal photo, tweak)
#   TERMINAL the proposal is finished; nothing to reply to
#   ROUTER   asks for a reply to a DIFFERENT message; no single proposal to bind
BOT = {
    ("cmd_propose", "send_photo(e, img"):                         "SELF",
    ("send_tweak", 'parse_mode="MarkdownV2"'):                    "SELF",
    ("send_tweak", "send_text(e, line, reply_to)"):               "SELF",
    ("decide", "can't tell which text"):                          "ADDRESS",
    ("decide", "you edited this and the edit was refused"):       "ADDRESS",
    ("decide", "too long"):                                       "ADDRESS",
    ("decide", "render_rails_block"):                             "ADDRESS",
    ("decide", "render_contrast_block"):                          "ADDRESS",
    ("decide", "4-post/24h cap"):                                 "ADDRESS",
    ("cmd_poll", "DID_YOU_MEAN"):                                 "ADDRESS",
    ("decide", "expired after"):                                  "TERMINAL",
    ("decide", "already %s"):                                     "TERMINAL",
    ("decide", "rejected%s"):                                     "TERMINAL",
    ("decide", "POSTED"):                                         "TERMINAL",
    ("decide", "post failed"):                                    "TERMINAL",
    ("cmd_poll", "reply to the one you mean"):                    "ROUTER",
}
# Scripts that send through telegram_bot. Alerts are not about a proposal.
EXTERNAL = {
    ("daily_digest.py", "TB.send_text(TB.env(), msg)"): "ALERT",   # the low-disk alert
    ("daily_digest.py", "halted"):                 "ALERT",
    ("watchdog.py", "watchdog"):                   "ALERT",
    ("daily_digest.py", "cmd_propose"):            "SELF",
    ("drop_correspondent.py", "cmd_propose"):      "SELF",
}

def sites(path, names, attr_only=False):
    src = path.read_text(); tree = ast.parse(src); parents = {}
    for n in ast.walk(tree):
        for c in ast.iter_child_nodes(n): parents[c] = n
    def fn(n):
        while n in parents:
            n = parents[n]
            if isinstance(n, ast.FunctionDef): return n.name
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call): continue
        name = getattr(n.func, "attr", None) if attr_only else getattr(n.func, "id", None)
        if attr_only and getattr(n.func, "value", None) is not None and getattr(n.func.value, "id", "") != "TB":
            continue
        if name in names:
            p = parents.get(n)
            wrapped = isinstance(p, ast.Call) and getattr(p.func, "id", None) == "_alias"
            out.append((fn(n), ast.get_source_segment(src, n), wrapped, n.lineno))
    return out

def classify(table, key_fn, seg):
    hits = [c for (f, frag), c in table.items() if key_fn(f) and frag in seg]
    return hits[0] if len(hits) == 1 else ("AMBIGUOUS" if hits else None)

print("\n=== 1. EVERY send site in telegram_bot.py is classified ===")
found = sites(REPO / "telegram_bot.py", {"send_text", "send_photo"})
seen = set()
for f, seg, wrapped, line in found:
    # the message text may live in a helper constant; include HELP/DID_YOU_MEAN names
    c = classify(BOT, lambda k: k == f, seg)
    seen.add(c)
    ok(c not in (None, "AMBIGUOUS"), "L%-4d %-12s classified %-8s %s" % (line, f, c, seg[:48].replace("\n", " ")))
    if c == "ADDRESS":
        ok(wrapped, "      …ADDRESS and wrapped in _alias")
    if c in ("TERMINAL", "ROUTER"):
        ok(not wrapped, "      …%s and NOT an address (a stale alias would misroute)" % c)
ok(len(found) == len(BOT),
   "site count == table size (%d found, %d classified) — a removed or new message shows here"
   % (len(found), len(BOT)))

print("\n=== 2. EVERY script that sends through the bot is classified ===")
ext = []
for py in sorted(REPO.glob("*.py")):
    if py.name == "telegram_bot.py": continue
    for f, seg, _w, line in sites(py, {"send_text", "send_photo", "cmd_propose"}, attr_only=True):
        c = classify(EXTERNAL, lambda k: k == py.name, seg) if "cmd_propose" not in seg else \
            EXTERNAL.get((py.name, "cmd_propose"))
        ext.append(c)
        ok(c is not None, "%s:%d classified %s" % (py.name, line, c))
ok(len(ext) == len(EXTERNAL), "external site count == table size (%d, %d)" % (len(ext), len(EXTERNAL)))

print("\n=== 3. BEHAVIOUR — a reply to each inviting message routes, with TWO pending ===")
def fresh():
    TB.PROPOSAL_LEDGER = Path(tempfile.mkdtemp()) / "p.jsonl"
    for pid, mid in (("p_other", 1), ("p", 2)):
        TB.ledger({"event": "proposed", "proposal_id": pid, "text": "Draft text for %s." % pid,
                   "image": "i.png", "message_id": mid,
                   "rails_ctx": {"image_name": "jordan_1_retro_low_og_shadow", "rarity": "Uncommon",
                                 "composition": "shoe_crop", "contrast": {"ratio": 1.3, "band": "flag"}}})
    box = {"n": 100}
    def send_text(e, text, reply_to=None, parse_mode=None):
        box["n"] += 1; box["last"] = box["n"]; return {"message_id": box["n"]}
    TB.send_text = send_text
    TB.X.posts_last_24h = lambda: 0
    return box
cases = {
    "contrast block":   lambda: TB.decide({}, "p", "approve", None, 9),
    "rails block":      lambda: TB.decide({}, "p", "approve", "Place your bet on it.", 9),
    "too long":         lambda: TB.decide({}, "p", "approve", "x " * 200, 9),
    "bare after edit":  lambda: (TB.decide({}, "p", "approve", "x " * 200, 9),
                                 TB.decide({}, "p", "approve", None, 9)),
}
for label, run in cases.items():
    box = fresh(); run()
    t = TB.resolve_target(TB.proposal_state(), box["last"])
    ok(t is not None and t["proposal_id"] == "p", "reply to the %-15s message -> p" % label)
box = fresh(); TB.X.posts_last_24h = lambda: 99
TB.PROPOSAL_LEDGER.write_text(""); TB.ledger({"event": "proposed", "proposal_id": "p_other",
    "text": "x.", "message_id": 1}); TB.ledger({"event": "proposed", "proposal_id": "p",
    "text": "The grey Swoosh.", "image": "i.png", "message_id": 2,
    "rails_ctx": {"image_name": "jordan_1_retro_low_og_shadow", "rarity": "Uncommon",
                  "composition": "shoe_crop", "contrast": {"ratio": 3.0, "band": "ok"}}})
TB.decide({}, "p", "approve", None, 9)
t = TB.resolve_target(TB.proposal_state(), box["last"])
ok(t is not None and t["proposal_id"] == "p", "reply to the 4-post cap message     -> p")

print("\n=== 4. THE HELP PATH — recorded, diagnosed, addressable ===")
box = fresh()
st = TB.proposal_state()["p"]
looks, sim = TB.looks_like_edit("This one: Draft text for p.", st)
ok(looks, "a changed copy of the text is diagnosed as an attempted edit (%.2f)" % sim)
ok(not TB.looks_like_edit("looks weak", st)[0], "a short remark is not")
ok(TB.parse_verdict("This one: Draft text for p.")[0] == "unknown",
   "…and the diagnosis NEVER makes it an edit: parse_verdict still says unknown")
tree = ast.parse((REPO / "telegram_bot.py").read_text())
pv = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "parse_verdict")
ok(not any(getattr(c.func, "id", "") == "looks_like_edit" for c in ast.walk(pv) if isinstance(c, ast.Call)),
   "parse_verdict never calls looks_like_edit — nothing without a command word becomes a post")
ok('(the \\"edit:\\" is part of what you send)' in (REPO / "telegram_bot.py").read_text()
   or '(the "edit:" is part of what you send)' in TB.HELP, "HELP names the prefix requirement")

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
