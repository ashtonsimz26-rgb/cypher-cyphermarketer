#!/usr/bin/env python3.12
"""
telegram_bot.py — cyphermarketer's approval loop (Phase 1: nothing posts
without an explicit Ashton approval in Telegram).

⚠️ SIBLING BOT — OFFSET ISOLATION IS LOAD-BEARING (ruling Q3).
Telegram's getUpdates is DESTRUCTIVE per bot token: fetching with
offset = last_update_id + 1 permanently discards every lower update. Two
pollers on one token silently eat each other's messages. CPA's approval queue
is a production decision stream, so this bot shares NOTHING with it:

                        CPA                          cyphermarketer
    token env   CPA_TELEGRAM_BOT_TOKEN       CYPHERMARKETER_TELEGRAM_BOT_TOKEN
    offset file cpa/data/telegram_proposals_state.json
                                             cyphermarketer/state/telegram_offset.json
    repo        ~/Documents/openclaw/CYPHER/cpa
                                             ~/Documents/openclaw/cyphermarketer

Same CHAT is fine (two bots, one conversation). Same TOKEN would be data loss.

FLOW
  propose  -> sends photo + exact tweet text + proposal id; ledgers "proposed"
  poll     -> reads replies; `approve` / `reject <reason>` / `edit: <new text>`.
              Replacement copy is OPT-IN behind `edit:`. Anything unrecognised is
              a no-op plus help — it never publishes (ruling C2, 2026-09-09).
              Proposals expire after PROPOSAL_TTL_HOURS (ruling C3).
  approve  -> posts via x_client, ledgers the tweet id, confirms with the link

Authorization: only CYPHERMARKETER_TELEGRAM_CHAT_ID may decide. Decisions are
idempotent — a proposal already decided is never acted on twice.
"""
from __future__ import annotations
import argparse, json, mimetypes, re, sys, time, urllib.request, urllib.error, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rails  # noqa: E402  (pure checks over local data; no network)
from research import composition as COMP  # noqa: E402  (rails_card_shows_value — shared with gate 8)
import switches as SW  # noqa: E402  (IMAGES_ENABLED — the one image switch)
import x_client as X  # noqa: E402

OFFSET_FILE = HERE / "state" / "telegram_offset.json"      # NOT CPA's state file
PROPOSAL_LEDGER = HERE / "ledger" / "proposals.jsonl"
API = "https://api.telegram.org/bot{token}"
APPROVE = {"approve", "approved", "yes", "y", "ok", "ship", "post", "go", "👍", "✅"}
REJECT = {"reject", "rejected", "no", "n", "nope", "kill", "skip", "👎", "❌"}

# ── VERDICT GRAMMAR ──────────────────────────────────────────────────────────
# ⚠️ THE DEFAULT USED TO BE PUBLISH. Until 2026-09-09 any reply that was not an
# exact APPROVE/REJECT token was treated as replacement copy and posted VERBATIM.
# So "reject: too wordy" tweeted the words "reject: too wordy". That made
# reject-with-reason not merely unsupported but actively dangerous, and it is why
# 23 of 31 proposals sat with no verdict — the only safe things to type were two
# bare words. Replacement copy is now OPT-IN behind `edit:`; anything
# unrecognised is a NO-OP plus help. Unrecognised input must never publish.
EDIT_PREFIX = "edit:"
# `tweak` is a REQUEST, not a verdict: it sends the current text back as a
# ready-to-send `edit:` line and does nothing else. It has no path to a post —
# tests/test_tweak.py asserts that structurally and behaviourally.
TWEAK = {"tweak"}

# ★ OVERRIDE — the distinct token for a contrast-flagged proposal (ruled
# 2026-09-17). A flagged card refuses a bare `approve` and requires this word.
#
# THE FRICTION IS THE FEATURE, and it is the whole reason this is not just an
# advisory note. If `approve` worked on a flagged card, the ledger could only
# ever say "a flag was present and he approved" — indistinguishable from a
# reviewer who never read it. Requiring a different word makes the override an
# ACT, so the record shows a judgement instead of a silent pass.
#
# It is deliberately NOT in APPROVE: an override must never be reachable by the
# reflex word. On an unflagged proposal it is accepted as a plain approval, so
# nobody has to remember which kind of card they are looking at.
OVERRIDE = {"override", "override!", "post anyway", "ship anyway"}
PROPOSAL_TTL_HOURS = 48                  # digest is daily; 48h = two cycles of grace
REJECT_REASONS = HERE / "state" / "reject_reasons.json"
REASON_WINDOW = 10

# A reject verb, then an optional free-text reason.
REJECT_RE = re.compile(r"^(reject|rejected|no|nope|kill|skip)\b[\s:,.\-—]*(.*)$",
                       re.I | re.S)

# Reason -> controlled code, first match wins. Codes are CRAFT judgments only.
# A reason that matches nothing stays uncoded — that is a valid outcome, not a
# failure, and an uncoded reason feeds nothing back (see editorial.avoid_guidance).
REASON_CODE_PATTERNS = (
    ("generic_lead",       r"generic|filler|boilerplate|any shoe|swap test"),
    ("too_wordy",          r"wordy|too long|verbose|trim|tighten|rambl"),
    ("weak_hook",          r"weak hook|no hook|hook is weak|boring|dull|not a moment"),
    ("format_repeat",      r"same format|same skeleton|format again|repetitive"),
    ("price_unattributed", r"unattributed|attribution|price claim|\$"),
)

HELP = ("🧢 Not a verdict I recognise — nothing was posted.\n"
        "Reply to a proposal with one of:\n"
        "  approve\n"
        "  reject <reason>      e.g.  reject weak hook\n"
        "  edit: <new text>     replaces the copy, posted verbatim\n"
        "                       (the \"edit:\" is part of what you send)\n"
        "  tweak                sends the text back, ready to edit and return\n"
        "Proposals expire after %dh." % PROPOSAL_TTL_HOURS)


def infer_reason_code(reason: str | None) -> str | None:
    """Map a free-text reason onto a controlled craft code, or None."""
    if not reason:
        return None
    for code, pat in REASON_CODE_PATTERNS:
        if re.search(pat, reason, re.I):
            return code
    return None


def parse_verdict(body: str) -> tuple[str, str | None, str | None]:
    """(verdict, payload, reason_code) — verdict in approve|override|reject|edit|tweak|unknown.

    `payload` is the replacement copy for edit, or the reason for reject.
    NOTHING falls through to publishing: an unparsed reply returns "unknown".
    """
    s = (body or "").strip()
    low = s.lower()
    if low in TWEAK:                                  # a request, never a verdict
        return "tweak", None, None
    if low in OVERRIDE:
        return "override", None, None
    if low in APPROVE:
        return "approve", None, None
    if low in REJECT:                                 # bare reject token or emoji
        return "reject", None, None
    if low.startswith(EDIT_PREFIX):
        payload = s[len(EDIT_PREFIX):].strip()
        return ("edit", payload, None) if payload else ("unknown", None, None)
    m = REJECT_RE.match(s)
    if m:
        reason = (m.group(2) or "").strip() or None
        return "reject", reason, infer_reason_code(reason)
    return "unknown", None, None


def record_reject_reason(pid: str, reason: str | None, code: str | None):
    """Rolling window of reasons for the drafter to read. Reason-bearing only —
    a reasonless reject carries no signal. The allow-list filter lives at the
    READ side (editorial.avoid_guidance), so an uncoded reason is still stored
    for Ashton to read while feeding nothing into drafting."""
    if not reason:
        return
    try:
        cur = json.loads(REJECT_REASONS.read_text())
        if not isinstance(cur, list):
            cur = []
    except Exception:
        cur = []
    cur.append({"proposal_id": pid, "reason": reason, "reason_code": code, "ts": now()})
    REJECT_REASONS.parent.mkdir(parents=True, exist_ok=True)
    REJECT_REASONS.write_text(json.dumps(cur[-REASON_WINDOW:], indent=1) + "\n")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def env() -> dict:
    e = X.load_env(Path(X.DEFAULT_ENV))
    for k in ("CYPHERMARKETER_TELEGRAM_BOT_TOKEN", "CYPHERMARKETER_TELEGRAM_CHAT_ID"):
        if not e.get(k):
            X.die("env missing key: %s" % k)          # name only, never the value
    if e["CYPHERMARKETER_TELEGRAM_BOT_TOKEN"] == e.get("CPA_TELEGRAM_BOT_TOKEN"):
        X.die("REFUSING: bot token is identical to CPA's — that would consume CPA's queue")
    return e


def api(e: dict) -> str:
    return API.format(token=e["CYPHERMARKETER_TELEGRAM_BOT_TOKEN"])


def _call(url: str, data: bytes | None = None, ct: str | None = None) -> tuple[int, dict]:
    h = {"User-Agent": "cyphermarketer/1.0"}
    if ct:
        h["Content-Type"] = ct
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as ex:
        try:
            return ex.code, json.loads(ex.read().decode())
        except Exception:
            return ex.code, {}
    except Exception as ex:
        return 0, {"transport_error": type(ex).__name__}


def ledger(rec: dict):
    PROPOSAL_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec)
    rec.setdefault("ts", now())
    with PROPOSAL_LEDGER.open("a", encoding="utf-8") as fh:     # append-only
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_ledger() -> list[dict]:
    if not PROPOSAL_LEDGER.exists():
        return []
    out = []
    for line in PROPOSAL_LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def proposal_state() -> dict:
    """Fold the append-only ledger into current state per proposal id."""
    st: dict[str, dict] = {}
    for r in read_ledger():
        pid = r.get("proposal_id")
        if not pid:
            continue
        cur = st.setdefault(pid, {"proposal_id": pid, "status": "unknown"})
        ev = r.get("event")
        if ev == "proposed":
            cur.update(status="pending", text=r.get("text"), image=r.get("image"),
                       message_id=r.get("message_id"), proposed_ts=r.get("ts"),
                       rails_ctx=r.get("rails_ctx"), format=r.get("format"),
                       hook_type=r.get("hook_type"),
                       composition=r.get("composition"), tier=r.get("tier"))
        elif ev in ("tweak_sent", "reply_alias"):
            # The tweak message becomes a second address for its proposal, so an
            # `edit:` sent as a REPLY TO THE TWEAK routes back here even when more
            # than one proposal is pending. Not a status change.
            if r.get("message_id"):
                cur.setdefault("alias_message_ids", []).append(r["message_id"])
        elif ev == "contrast_blocked":
            # The EXACT text the contrast block showed Ashton. `override` posts this
            # and nothing else. Rows written before 2026-09-18 carry no text: an
            # un-edited block showed the draft; an edited one showed the edit folded
            # just before it (edit_received precedes contrast_blocked in the same
            # decide() call). Anything unrecoverable is AMBIGUOUS, and override refuses.
            t = r.get("text")
            if t is None:
                t = cur.get("last_edit_text") if r.get("edited") else cur.get("text")
            cur["contrast_blocked_text"] = t
            cur["contrast_blocked_ambiguous"] = t is None
        elif ev == "edit_received":
            # The operator's most recent wording, kept even if rails or the 280
            # ceiling refused it — `tweak` hands this back, not the stale draft.
            # Not a status change: a refused edit leaves the proposal pending.
            cur["last_edit_text"] = r.get("edited_text")
        # ⚠️ "rails_blocked" and "edit_too_long" are DELIBERATELY ABSENT from this
        # tuple. A validation failure is information, not a verdict: the proposal
        # stays pending so it can be fixed with `edit:` and re-approved. Logging
        # either as "failed" would make it terminal — which is exactly the bug
        # fixed here (the over-length path told you to "send a shorter version"
        # and then refused every retry).
        elif ev in ("approved", "rejected", "posted", "failed", "expired"):
            cur["status"] = ev
            if r.get("url"):
                cur["url"] = r["url"]
            if r.get("final_text"):
                cur["text"] = r["final_text"]
    # TTL is COMPUTED, so a proposal ages out whether or not a sweep ever runs.
    # Without this, pending was terminal-by-omission: 23 proposals accumulated,
    # which killed the single-pending fallback and made every bare reply useless.
    cutoff = datetime.now(timezone.utc) - timedelta(hours=PROPOSAL_TTL_HOURS)
    for v in st.values():
        if v["status"] == "pending" and v.get("proposed_ts"):
            try:
                if datetime.fromisoformat(v["proposed_ts"]) < cutoff:
                    v["status"] = "expired"
            except Exception:
                pass
    return st


# ── send ─────────────────────────────────────────────────────────────────────
def send_photo(e: dict, image: Path, caption: str) -> dict:
    b = "----cm" + uuid.uuid4().hex
    ct = mimetypes.guess_type(image.name)[0] or "image/png"
    body = b""
    for k, v in (("chat_id", e["CYPHERMARKETER_TELEGRAM_CHAT_ID"]), ("caption", caption)):
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                 % (b, k, v)).encode()
    body += ("--%s\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"%s\"\r\n"
             "Content-Type: %s\r\n\r\n" % (b, image.name, ct)).encode()
    body += image.read_bytes() + b"\r\n" + ("--%s--\r\n" % b).encode()
    st, j = _call(api(e) + "/sendPhoto", body, "multipart/form-data; boundary=%s" % b)
    if not j.get("ok"):
        X.die("sendPhoto failed (HTTP %s): %s" % (st, str(j)[:200]))
    return j["result"]


def send_text_strict(e: dict, text: str) -> dict:
    """sendMessage that DIES on failure, like send_photo. A text-only proposal
    that silently failed to send would be ledgered with no message_id, and no
    reply could ever address it; send_text() returns {} on failure, which is
    fine for chatter but not for the proposal itself."""
    p = {"chat_id": e["CYPHERMARKETER_TELEGRAM_CHAT_ID"], "text": text,
         "disable_web_page_preview": True}
    st, j = _call(api(e) + "/sendMessage", json.dumps(p).encode(), "application/json")
    if not j.get("ok"):
        X.die("sendMessage failed (HTTP %s): %s" % (st, str(j)[:200]))
    return j["result"]


def send_text(e: dict, text: str, reply_to: int | None = None,
              parse_mode: str | None = None) -> dict:
    p = {"chat_id": e["CYPHERMARKETER_TELEGRAM_CHAT_ID"], "text": text,
         "disable_web_page_preview": False}
    if parse_mode:
        p["parse_mode"] = parse_mode
    if reply_to:
        p["reply_to_message_id"] = reply_to
    st, j = _call(api(e) + "/sendMessage", json.dumps(p).encode(), "application/json")
    return j.get("result", {})


def word_diff(before: str, after: str) -> list[dict]:
    """Word-level changes only — what the operator actually altered, readable
    from the ledger row without re-diffing two 280-char strings by eye."""
    import difflib
    a, b = before.split(), after.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op != "equal":
            out.append({"op": op, "from": " ".join(a[i1:i2]), "to": " ".join(b[j1:j2])})
    return out


_MD2_SPECIAL = r"_*[]()~`>#+-=|{}.!"


def md2_escape(t: str) -> str:
    """Escape for Telegram MarkdownV2 OUTSIDE code spans."""
    return "".join("\\" + c if c in _MD2_SPECIAL or c == "\\" else c for c in t)


def md2_code_escape(t: str) -> str:
    """Escape INSIDE a MarkdownV2 code span: only backslash and backtick."""
    return t.replace("\\", "\\\\").replace("`", "\\`")


def _alias(pid: str, res: dict):
    """Make a bot message that asks for a fix an ADDRESS for its proposal, so a
    reply to it (`tweak`, `edit:`) routes back even with several pending."""
    if res and res.get("message_id"):
        ledger({"event": "reply_alias", "proposal_id": pid, "message_id": res["message_id"]})


def send_tweak(e: dict, target: dict, reply_to: int | None) -> dict:
    """Send the proposal's current text back as a ready-to-send `edit:` line.

    ★ A REQUEST, NOT A VERDICT. This produces TEXT and nothing else: it never
    calls decide(), never touches x_client, never writes approved/posted. The
    only way from here to a post is Ashton sending the edited line back, which
    re-enters through parse_verdict -> decide -> rails_gate like any `edit:`.
    tests/test_tweak.py asserts that.

    Current text = his most recent edit attempt if one exists (even a refused
    one — that is the wording he was working on), else the draft.

    Primary form: MarkdownV2 inline code, which most Telegram clients copy in
    one tap. If Telegram rejects the markup, fall back to a plain message whose
    ENTIRE body is the `edit:` line, so a long-press copy still gets exactly it.
    """
    pid = target["proposal_id"]
    last = target.get("last_edit_text")
    text = last or target.get("text") or ""
    line = "%s %s" % (EDIT_PREFIX, text)
    src = "your last edit" if last else "the draft"
    head = ("✏️ %s — %s. Copy the whole line below, `edit:` included, change the "
            "words, and reply here." % (pid, src))
    res = {}
    try:
        res = send_text(e, md2_escape(head) + "\n`" + md2_code_escape(line) + "`",
                        reply_to, parse_mode="MarkdownV2")
    except Exception:
        res = {}
    mode = "markdownv2"
    if not res.get("message_id"):
        res = send_text(e, line, reply_to)
        mode = "plain_fallback"
    ledger({"event": "tweak_sent", "proposal_id": pid, "message_id": res.get("message_id"),
            "source": "last_edit" if last else "draft", "mode": mode})
    return res


def new_proposal_id() -> str:
    """The ONE place a proposal id is minted. The digest calls it when it names a
    draft's output files (so content/ is keyed by the id, never by shoe+date), and
    hands the same id to cmd_propose — files and proposal share one key."""
    return "p_" + uuid.uuid4().hex[:10]


def cmd_propose(a, e):
    text = Path(a.text_file).read_text(encoding="utf-8").rstrip("\n")
    wl = X.weighted_len(text)
    if wl > 280:
        X.die("draft is %d weighted chars, over 280" % wl)
    # ★ IMAGES_ENABLED=false: no image is attached to ANY proposal, whoever built
    # it. An image handed in anyway (a CLI propose) is not sent; the proposal is
    # recorded as text_only and the original composition is kept alongside.
    images_on = SW.images_enabled()
    img = Path(a.image) if (getattr(a, "image", None) and images_on) else None
    if img is not None and not img.exists():
        X.die("image not found: %s" % img)
    composition = getattr(a, "composition", None)
    proposed_composition = None
    if img is None and composition != COMP.TEXT_ONLY:
        proposed_composition, composition = composition, COMP.TEXT_ONLY
    # ★ The id may be PRE-MINTED by the digest, which named this draft's content/
    # files with it before proposing. Use it rather than minting a second one — a
    # mismatch would orphan the files from their proposal. Refuse a reused id.
    pid = getattr(a, "proposal_id", None) or new_proposal_id()
    if pid in proposal_state():
        X.die("proposal id %s is already in the ledger — refusing to reuse it" % pid)
    caption = (
        "🧢 CYPHERMARKETER — proposal %s\n"
        "%s\n"
        "──────────\n%s\n──────────\n"
        "%d/280 chars · %s\n\n"
        "Reply: approve · reject <reason> · edit: <new text>\n"
        "A reason teaches the next draft. Unrecognised replies do nothing.\n"
        "Expires in %dh."
        % (pid, a.note or "", text, wl,
           img.name if img is not None else "TEXT ONLY — no image (IMAGES_ENABLED=false)",
           PROPOSAL_TTL_HOURS)
    )
    res = send_photo(e, img, caption[:1024]) if img is not None else send_text_strict(e, caption)
    # rails_ctx lets check_draft() re-run at APPROVE time. Absent for CLI-driven
    # proposals, which then fall back to the STRICT direction (see decide()).
    # NEVER derive image_name from the image filename: daily_digest truncates it
    # at [:40] in the stem, so long names would be silently wrong.
    ledger({"event": "proposed", "proposal_id": pid, "text": text,
            "image": str(img) if img is not None else None,
            "note": a.note, "message_id": res.get("message_id"), "weighted_len": wl,
            "rails_ctx": getattr(a, "rails_ctx", None),
            "format": getattr(a, "format", None),
            "hook_type": getattr(a, "hook_type", None),
            # R6 — composition and tier ride the proposal so the POSTED row can
            # carry them without a join. Everything downstream of here is
            # append-only, so a field absent at propose time is unrecoverable
            # later: see the five Aug posts, whose composition is gone for good
            # because nothing logged it.
            "composition": composition,
            **({"proposed_composition": proposed_composition} if proposed_composition else {}),
            "tier": getattr(a, "tier", None)})
    print("  proposed %s  (telegram message_id %s)" % (pid, res.get("message_id")))
    print("  awaiting decision in Telegram…")
    return pid                       # so callers can emit an EXACT linking row


# ── poll ─────────────────────────────────────────────────────────────────────
def load_offset() -> int:
    try:
        return int(json.loads(OFFSET_FILE.read_text()).get("offset", 0))
    except Exception:
        return 0


def save_offset(v: int):
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(json.dumps({"offset": v, "updated": now()}) + "\n")


def rails_gate(text: str, ctx: dict | None, composition: str | None = None
               ) -> tuple[bool, list[tuple[str, bool, str]]]:
    """Re-run rails.check_draft() on the text about to be posted.

    price_verified is RECOMPUTED, never cached: rails.price_claim_allowed reads
    PK's local price_history and applies FRESHNESS_DAYS against the current
    clock, so an aged proposal fails freshness here even though it passed at
    draft time. No network, no PK process, no fresh API read.

    FAIL-CLOSED on a missing context: a proposal with no stored rails_ctx (a
    CLI-driven propose, or one made before F1.5) gets price_verified=False,
    which forces any price claim out of our own voice. Never permissive.

    card_shows_value comes from COMP.rails_card_shows_value(composition) — the
    SAME function gate 8 calls at draft time. Composition is read from rails_ctx,
    or from the top-level proposal row for proposals stored before 2026-09-18,
    and a missing one yields True: fail closed, require attribution. No rail is
    weakened here — a composition that shows the value row still demands it.

    ★ CORRECTED 2026-09-18. This docstring said card_shows_value was "passed
    exactly as daily_digest passes it". That was true when F1.5 (91e4a23) wrote
    it — both doors passed a literal True. G2 (13834d0) then taught the DIGEST to
    compute it and never touched this file, so from 09-11 this door kept True and
    the sentence became false. Same text, same card, opposite verdicts on
    shoe_crop / shoe_only / two_card_crop. The defect arrived by a change to the
    OTHER file, which is why no review of this one could have caught it.
    tests/test_rails_door_parity.py is what catches it now.

    ★ pool_reachable=True is GONE (2026-09-16). This door had the same hardcoded
    literal as the digest, so the obtainability rail was inert at BOTH of them.
    The (image_name, rarity) pair now comes off rails_ctx and rails derives the
    verdict. A proposal stored before this change carries no rarity, so it fails
    OBTAINABLE closed and has to be re-proposed — which is correct: we cannot
    prove a card is obtainable from a context that never recorded which card it
    was at which tier.
    """
    price_verified = False
    if ctx and ctx.get("style_code"):
        price_verified, _why = rails.price_claim_allowed(
            ctx["style_code"], ctx.get("estimated_resale"))
    comp = (ctx or {}).get("composition") or composition
    checks = rails.check_draft(text, card_shows_value=COMP.rails_card_shows_value(comp),
                               price_verified=price_verified,
                               image_name=(ctx or {}).get("image_name"),
                               rarity=(ctx or {}).get("rarity"))
    failed = [c for c in checks if not c.passed]
    return (not failed), failed


def render_rails_block(pid: str, failed: list[tuple[str, bool, str]]) -> str:
    """Labels PLUS remediation notes — this has to be actionable from a phone."""
    lines = ["⛔ %s NOT posted — rails failed at approval:" % pid]
    for c in failed:
        lines.append("  • %s" % c.label)
        if c.note:
            lines.append("    ↳ %s" % c.note)
    lines.append("")
    lines.append("Still pending. Reply `tweak` to get the text back ready to edit, "
                 "or send `edit: <fixed text>`, or leave it to expire.")
    return "\n".join(lines)


def contrast_gate(st: dict, overridden: bool) -> tuple[bool, dict]:
    """(may_post, contrast_record) for a proposal about to be approved.

    ★ Returns the record on EVERY path, flagged or not (Ashton's ruling,
    2026-09-17, extending the ask). A flagged-and-overridden row shows a
    judgement; but logging the ratio on ordinary passes too turns each ruling
    into labelled data, so the threshold can later be re-derived from what he
    actually accepted rather than from the estimate we opened with.
    """
    c = (st.get("rails_ctx") or {}).get("contrast") or {}
    rec = {"ratio": c.get("ratio"), "band": c.get("band") or "unmeasured",
           "overridden": bool(overridden)}
    if rec["band"] == "flag" and not overridden:
        return False, rec
    return True, rec


def render_contrast_block(pid: str, rec: dict, text: str | None = None) -> str:
    """NON-TERMINAL refusal — same shape as render_rails_block (ruled).

    Quotes the exact text held, because `override` posts THAT text and nothing
    else: the message has to show what the word will publish."""
    held = ("\n  Text held for override:\n  %s\n" % text) if text else ""
    return ("⚠️ %s NOT posted — the card is contrast-flagged at %.2f:1.\n"
            "  • The shoe may not read against its panel. Zoom the card.\n%s"
            "  • Reply `override` to post exactly that text anyway, or `reject`.\n"
            "  Still pending — nothing has been decided."
            % (pid, rec["ratio"] if rec["ratio"] is not None else float("nan"), held))


def decide(e, pid: str, verdict: str, final_text: str | None, reply_to: int | None,
           reason: str | None = None, reason_code: str | None = None,
           overridden: bool = False):
    st = proposal_state().get(pid)
    if not st:
        return
    # ★ EDIT RECEIVED — recorded FIRST, before the status checks, the 280 ceiling
    # and the rails. Until 2026-09-18 a refused edit left no trace of its text:
    # rails_blocked stored only `edited: true`, edit_too_long only a length. That
    # discarded the operator's own words. Now every `edit:` is on the ledger with
    # the original preserved beside it and the word diff between them, whatever
    # happens next. A write, never a status change — see proposal_state.
    if final_text is not None:
        ledger({"event": "edit_received", "proposal_id": pid,
                "status_at_receipt": st.get("status"),
                "original_text": st.get("text"), "edited_text": final_text,
                "diff": word_diff(st.get("text") or "", final_text)})
    if st["status"] == "expired":                    # specific before generic
        send_text(e, "⏳ %s expired after %dh — the digest will re-propose it if it is "
                     "still right. Nothing posted." % (pid, PROPOSAL_TTL_HOURS), reply_to)
        return
    if st["status"] != "pending":                    # idempotent
        send_text(e, "⚠️ %s already %s — ignoring." % (pid, st["status"]), reply_to)
        return
    if verdict == "reject":
        rec = {"event": "rejected", "proposal_id": pid, "reason_code": reason_code}
        if reason:
            rec["reason"] = reason
        ledger(rec)
        record_reject_reason(pid, reason, reason_code)
        send_text(e, "🛑 %s rejected%s. Nothing posted." % (
            pid, " — noted: %s" % reason if reason else " (no reason given)"), reply_to)
        return

    # ── WHICH TEXT THIS VERDICT ACTS ON (2026-09-18) ─────────────────────────
    # `override` used to post st["text"] — the ORIGINAL DRAFT — because an edit
    # that hit the contrast gate was never stored as the proposal's text. On
    # p_34f18679da that would have published the machine's words in place of
    # Ashton's, with no error, on a surface where posts cannot be retracted.
    # Rule: a verdict acts on text it can NAME. An `edit:` names its own. An
    # `override` names the text the contrast block showed. A bare verdict after
    # a refused edit names nothing — falling back to the draft is substitution —
    # so it is refused and pointed at `tweak`.
    draft = st["text"]
    if final_text is not None:
        text = final_text
    elif overridden and st.get("contrast_blocked_text") is not None:
        text = st["contrast_blocked_text"]
    elif overridden and st.get("contrast_blocked_ambiguous"):
        ledger({"event": "bare_verdict_refused", "proposal_id": pid,
                "verdict": "override", "why": "contrast_blocked_text_unrecoverable"})
        _alias(pid, send_text(e, "⚠️ %s NOT posted — I can't tell which text the contrast "
                                 "flag was on, so `override` has nothing exact to post. Reply "
                                 "`tweak`, then send the text you want as `edit:`. Nothing "
                                 "posted." % pid, reply_to))
        return
    elif st.get("last_edit_text") is not None and st["last_edit_text"] != draft:
        ledger({"event": "bare_verdict_refused", "proposal_id": pid,
                "verdict": "override" if overridden else "approve",
                "why": "edit_refused_earlier_bare_verdict_would_post_draft"})
        _alias(pid, send_text(e, "⚠️ %s NOT posted — you edited this and the edit was refused, "
                                 "so a bare `%s` would post the ORIGINAL draft, not your words. "
                                 "Reply `tweak` for your edit back, fix it, and send it. "
                                 "Nothing posted." % (pid, "override" if overridden else "approve"),
                              reply_to))
        return
    else:
        text = draft
    wl = X.weighted_len(text)
    if wl > 280:
        # NON-TERMINAL (fix #1): the message promises a retry, so the retry must
        # work. This used to log "failed", which is terminal — every "shorter
        # version" was then answered with "already failed — ignoring".
        ledger({"event": "edit_too_long", "proposal_id": pid, "weighted": wl})
        _alias(pid, send_text(e, "❌ %s: your edit is %d/280 chars — too long. Reply `tweak` "
                                 "for your text back, or send a shorter version." % (pid, wl),
                              reply_to))
        return

    # ── RAILS AT APPROVE TIME (F1.5) ─────────────────────────────────────────
    # Runs on the FINAL text — the stored draft OR an `edit:` payload. Edits were
    # previously length-checked ONLY, so a verbatim edit bypassed gambling,
    # attribution and price screening entirely. rails.py itself is unchanged;
    # this is the same rail running at one more call site.
    ok_rails, failed = rails_gate(text, st.get("rails_ctx"), st.get("composition"))
    if not ok_rails:
        ledger({"event": "rails_blocked", "proposal_id": pid,      # NON-terminal
                "failed": [f[0] for f in failed], "edited": final_text is not None})
        _alias(pid, send_text(e, render_rails_block(pid, failed), reply_to))
        return

    # ── CONTRAST GATE ────────────────────────────────────────────────────────
    # NON-TERMINAL, deliberately the same shape as rails_blocked above: the
    # proposal stays pending and decidable, and the reply names the other word.
    # ★ TEXT-ONLY POST: the proposal was made text-only, OR IMAGES_ENABLED is
    # now false. The second case is an image proposal made before the switch was
    # turned off and approved after — it posts WITHOUT its image, because
    # "images off" means none reaches X. Rails above still ran on the composition
    # the text was DRAFTED against (never weaker: removing the image removes a
    # claim, it cannot add one).
    text_only_post = (st.get("composition") == COMP.TEXT_ONLY or not st.get("image")
                      or not SW.images_enabled())
    may_post, contrast = contrast_gate(st, overridden)
    if text_only_post:
        # The contrast gate measures a card that will not be posted. SKIPPED, and
        # the skip is written into the approved row — never silently passed.
        contrast = {**contrast, "band": "skipped_text_only",
                    "measured_band": contrast.get("band")}
        may_post = True
    if not may_post:
        ledger({"event": "contrast_blocked", "proposal_id": pid,   # NON-terminal
                "contrast": contrast, "edited": text != draft, "text": text})
        _alias(pid, send_text(e, render_contrast_block(pid, contrast, text), reply_to))
        return

    used = X.posts_last_24h()
    if used >= X.MAX_POSTS_24H:
        # NON-TERMINAL (fix #2): checked BEFORE the approved row is written, so a
        # capped proposal stays decidable once the cap clears. Previously
        # "approved" was ledgered first, terminally, and the retry was refused.
        ledger({"event": "cap_deferred", "proposal_id": pid, "posts_last_24h": used})
        _alias(pid, send_text(e, "🚫 %s not posted — the 4-post/24h cap is reached (%d). "
                                 "Still pending: approve again once it clears." % (pid, used),
                              reply_to))
        return

    # Edited = the words differ from the draft — true for an overridden edit too,
    # which arrives here with final_text None.
    edited = text != draft
    ledger({"event": "approved", "proposal_id": pid, "final_text": text,
            "edited": edited, "contrast": contrast})

    xenv = X.load_env(Path(X.DEFAULT_ENV))
    X.ledger_append({"event": "attempt", "text": text,
                     "note": "telegram approval %s" % pid})
    media_ids = [] if text_only_post else [X.upload_media(Path(st["image"]), xenv)]
    res = X.create_tweet(text, media_ids, xenv)
    if res["status"] not in (200, 201):
        ledger({"event": "failed", "proposal_id": pid, "error": res["raw"][:300]})
        X.ledger_append({"event": "failed", "error": res["raw"][:300]})
        send_text(e, "❌ %s post failed (HTTP %s)." % (pid, res["status"]), reply_to)
        return
    tid = json.loads(res["raw"])["data"]["id"]
    url = "https://x.com/%s/status/%s" % (X.HANDLE, tid)
    # format/hook_type are DENORMALISED here on purpose: a post's format must be
    # readable straight off the posted row, not reconstructed by joining
    # posts -> proposals -> runs on timestamp proximity. That join was ambiguous
    # (aj8_doernbecher was drafted 3x in 6 minutes under two formats).
    # The posted composition is what was POSTED. An image proposal posted without
    # its image is text_only, with the drafted composition kept beside it.
    posted_comp = COMP.TEXT_ONLY if text_only_post else st.get("composition")
    drafted = ({"proposed_composition": st.get("composition")}
               if text_only_post and st.get("composition") not in (None, COMP.TEXT_ONLY)
               else {})
    X.ledger_append({"event": "posted", "text": text, "tweet_id": tid, "url": url,
                     "media_ids": media_ids, "note": "telegram approval %s" % pid,
                     "proposal_id": pid, "format": st.get("format"),
                     "hook_type": st.get("hook_type"),
                     "composition": posted_comp, **drafted, "tier": st.get("tier")})
    ledger({"event": "posted", "proposal_id": pid, "tweet_id": tid, "url": url,
            "final_text": text, "edited": edited, "format": st.get("format"),
            "hook_type": st.get("hook_type"),
            "composition": posted_comp, **drafted, "tier": st.get("tier")})
    send_text(e, "✅ POSTED%s\n%s\n\n(%d/%d posts used in the last 24h)"
              % (" (your edit, verbatim)" if edited else "", url,
                 X.posts_last_24h(), X.MAX_POSTS_24H), reply_to)


DID_YOU_MEAN = ("🧢 That looks like an edit to %s. Put `edit: ` in front of it and send "
                "it again. Nothing was posted.")
EDIT_LIKE_MIN_WORDS = 4
EDIT_LIKE_RATIO = 0.6


def looks_like_edit(body: str, target: dict) -> tuple[bool, float]:
    """Does an unrecognised reply look like a changed copy of this proposal's text?

    DIAGNOSIS ONLY. The answer chooses which help message to send; it NEVER turns
    the reply into an edit. Nothing without a command word becomes a post —
    parse_verdict is the only door, and this function is not wired to it."""
    import difflib
    words = body.lower().split()
    if len(words) < EDIT_LIKE_MIN_WORDS:
        return False, 0.0
    best = 0.0
    for cand in (target.get("text"), target.get("last_edit_text"),
                 target.get("contrast_blocked_text")):
        if cand:
            best = max(best, difflib.SequenceMatcher(
                a=cand.lower().split(), b=words, autojunk=False).ratio())
    return best >= EDIT_LIKE_RATIO, round(best, 3)


def resolve_target(state: dict, reply_mid: int | None) -> dict | None:
    """Which proposal a reply is about: the one whose proposal message — or whose
    `tweak` message — it replies to; else the only pending one; else None."""
    if reply_mid:
        hit = next((v for v in state.values()
                    if v.get("message_id") == reply_mid
                    or reply_mid in v.get("alias_message_ids", ())), None)
        if hit is not None:
            return hit
    pending = [v for v in state.values() if v["status"] == "pending"]
    return pending[0] if len(pending) == 1 else None


def cmd_poll(a, e):
    chat_id = str(e["CYPHERMARKETER_TELEGRAM_CHAT_ID"])
    offset = load_offset()
    deadline = time.time() + a.max_seconds
    print("  polling (own offset=%d, own token) — chat %s only" % (offset, chat_id))
    while time.time() < deadline:
        url = api(e) + "/getUpdates?timeout=%d" % a.timeout
        if offset:
            url += "&offset=%d" % offset
        st, j = _call(url)
        if not j.get("ok"):
            time.sleep(3)
            continue
        for u in j.get("result", []):
            offset = u["update_id"] + 1
            save_offset(offset)                       # persist before acting
            m = (u.get("message") or u.get("channel_post")
                 or u.get("edited_message") or {})
            got_chat = str((m.get("chat") or {}).get("id", ""))
            # Raw-update audit BEFORE filtering. An update consumed by the offset
            # but dropped by a filter used to vanish silently — that cost a round
            # trip. Now every update leaves a trace.
            ledger({"event": "update_seen", "update_id": u.get("update_id"),
                    "chat_id": got_chat, "chat_matches": got_chat == chat_id,
                    "has_text": bool(m.get("text")),
                    "text_preview": (m.get("text") or "")[:80],
                    "reply_to": (m.get("reply_to_message") or {}).get("message_id")})
            if got_chat != chat_id:
                continue                              # authorization: chat must match
            body = (m.get("text") or "").strip()
            if not body:
                continue
            reply_mid = (m.get("reply_to_message") or {}).get("message_id")
            state = proposal_state()
            pending = [v for v in state.values() if v["status"] == "pending"]
            target = resolve_target(state, reply_mid)
            if target is None:
                if pending:
                    send_text(e, "⚠️ %d proposals pending — reply to the one you mean."
                              % len(pending), m.get("message_id"))
                continue
            verdict, payload, reason_code = parse_verdict(body)
            if verdict == "unknown":
                # NO-OP + discoverable grammar. Never a publish. If the reply looks
                # like a changed copy of the text (the 2026-09-18 mistake: the lead
                # pasted back without `edit:`), say exactly that; otherwise the
                # generic help. Either way it is RECORDED — an unrecognised reply is
                # the best evidence there is about whether the wording works — and
                # the help is an address, so the corrected reply routes back.
                looks, sim = looks_like_edit(body, target)
                ledger({"event": "unrecognised_reply", "proposal_id": target["proposal_id"],
                        "text": body, "looked_like_edit": looks, "similarity": sim})
                _alias(target["proposal_id"], send_text(
                    e, DID_YOU_MEAN % target["proposal_id"] if looks else HELP,
                    m.get("message_id")))
                continue
            if verdict == "tweak":
                # A request, not a verdict: text out, nothing else. Does NOT end a
                # --once run, so the edited reply can land in the same window.
                send_tweak(e, target, m.get("message_id"))
                continue
            if verdict == "override":
                decide(e, target["proposal_id"], "approve", None, m.get("message_id"),
                       overridden=True)
            elif verdict == "approve":
                decide(e, target["proposal_id"], "approve", None, m.get("message_id"))
            elif verdict == "reject":
                decide(e, target["proposal_id"], "reject", None, m.get("message_id"),
                       reason=payload, reason_code=reason_code)
            else:                                    # explicit `edit:` — verbatim copy
                decide(e, target["proposal_id"], "approve", payload, m.get("message_id"))
            # --once means once: ANY real verdict ends the run. Previously only an
            # edit set this, so approve/reject polled on to the max-seconds ceiling.
            if a.once:
                return
    print("  poll window ended.")


def cmd_status(a, e):
    for pid, v in sorted(proposal_state().items()):
        print("  %-14s %-9s %s" % (pid, v["status"], v.get("url", "")))


def main():
    ap = argparse.ArgumentParser(description="cyphermarketer Telegram approval loop")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("propose"); p1.add_argument("--text-file", required=True)
    p1.add_argument("--image", required=True); p1.add_argument("--note", default="")
    p2 = sub.add_parser("poll"); p2.add_argument("--timeout", type=int, default=30)
    p2.add_argument("--max-seconds", type=int, default=300); p2.add_argument("--once", action="store_true")
    sub.add_parser("status")
    a = ap.parse_args()
    e = env()
    {"propose": cmd_propose, "poll": cmd_poll, "status": cmd_status}[a.cmd](a, e)


if __name__ == "__main__":
    main()
