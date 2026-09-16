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
    """(verdict, payload, reason_code) — verdict in approve|reject|edit|unknown.

    `payload` is the replacement copy for edit, or the reason for reject.
    NOTHING falls through to publishing: an unparsed reply returns "unknown".
    """
    s = (body or "").strip()
    low = s.lower()
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


def send_text(e: dict, text: str, reply_to: int | None = None) -> dict:
    p = {"chat_id": e["CYPHERMARKETER_TELEGRAM_CHAT_ID"], "text": text,
         "disable_web_page_preview": False}
    if reply_to:
        p["reply_to_message_id"] = reply_to
    st, j = _call(api(e) + "/sendMessage", json.dumps(p).encode(), "application/json")
    return j.get("result", {})


def cmd_propose(a, e):
    text = Path(a.text_file).read_text(encoding="utf-8").rstrip("\n")
    wl = X.weighted_len(text)
    if wl > 280:
        X.die("draft is %d weighted chars, over 280" % wl)
    img = Path(a.image)
    if not img.exists():
        X.die("image not found: %s" % img)
    pid = "p_" + uuid.uuid4().hex[:10]
    caption = (
        "🧢 CYPHERMARKETER — proposal %s\n"
        "%s\n"
        "──────────\n%s\n──────────\n"
        "%d/280 chars · %s\n\n"
        "Reply: approve · reject <reason> · edit: <new text>\n"
        "A reason teaches the next draft. Unrecognised replies do nothing.\n"
        "Expires in %dh."
        % (pid, a.note or "", text, wl, img.name, PROPOSAL_TTL_HOURS)
    )
    res = send_photo(e, img, caption[:1024])
    # rails_ctx lets check_draft() re-run at APPROVE time. Absent for CLI-driven
    # proposals, which then fall back to the STRICT direction (see decide()).
    # NEVER derive image_name from the image filename: daily_digest truncates it
    # at [:40] in the stem, so long names would be silently wrong.
    ledger({"event": "proposed", "proposal_id": pid, "text": text, "image": str(img),
            "note": a.note, "message_id": res.get("message_id"), "weighted_len": wl,
            "rails_ctx": getattr(a, "rails_ctx", None),
            "format": getattr(a, "format", None),
            "hook_type": getattr(a, "hook_type", None),
            # R6 — composition and tier ride the proposal so the POSTED row can
            # carry them without a join. Everything downstream of here is
            # append-only, so a field absent at propose time is unrecoverable
            # later: see the five Aug posts, whose composition is gone for good
            # because nothing logged it.
            "composition": getattr(a, "composition", None),
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


def rails_gate(text: str, ctx: dict | None) -> tuple[bool, list[tuple[str, bool, str]]]:
    """Re-run rails.check_draft() on the text about to be posted.

    price_verified is RECOMPUTED, never cached: rails.price_claim_allowed reads
    PK's local price_history and applies FRESHNESS_DAYS against the current
    clock, so an aged proposal fails freshness here even though it passed at
    draft time. No network, no PK process, no fresh API read.

    FAIL-CLOSED on a missing context: a proposal with no stored rails_ctx (a
    CLI-driven propose, or one made before F1.5) gets price_verified=False,
    which forces any price claim out of our own voice. Never permissive.

    card_shows_value / pool_reachable are passed exactly as daily_digest passes
    them, so this call site treats the rail identically — no rail is weakened,
    strengthened, or made conditional here.
    """
    price_verified = False
    if ctx and ctx.get("style_code"):
        price_verified, _why = rails.price_claim_allowed(
            ctx["style_code"], ctx.get("estimated_resale"))
    checks = rails.check_draft(text, card_shows_value=True, pool_reachable=True,
                              price_verified=price_verified)
    failed = [c for c in checks if not c[1]]
    return (not failed), failed


def render_rails_block(pid: str, failed: list[tuple[str, bool, str]]) -> str:
    """Labels PLUS remediation notes — this has to be actionable from a phone."""
    lines = ["⛔ %s NOT posted — rails failed at approval:" % pid]
    for label, _passed, note in failed:
        lines.append("  • %s" % label)
        if note:
            lines.append("    ↳ %s" % note)
    lines.append("")
    lines.append("Still pending. Send `edit: <fixed text>` to correct it, or leave "
                 "it to expire.")
    return "\n".join(lines)


def decide(e, pid: str, verdict: str, final_text: str | None, reply_to: int | None,
           reason: str | None = None, reason_code: str | None = None):
    st = proposal_state().get(pid)
    if not st:
        return
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

    text = final_text if final_text is not None else st["text"]
    wl = X.weighted_len(text)
    if wl > 280:
        # NON-TERMINAL (fix #1): the message promises a retry, so the retry must
        # work. This used to log "failed", which is terminal — every "shorter
        # version" was then answered with "already failed — ignoring".
        ledger({"event": "edit_too_long", "proposal_id": pid, "weighted": wl})
        send_text(e, "❌ %s: your edit is %d/280 chars — too long. Send a shorter version."
                  % (pid, wl), reply_to)
        return

    # ── RAILS AT APPROVE TIME (F1.5) ─────────────────────────────────────────
    # Runs on the FINAL text — the stored draft OR an `edit:` payload. Edits were
    # previously length-checked ONLY, so a verbatim edit bypassed gambling,
    # attribution and price screening entirely. rails.py itself is unchanged;
    # this is the same rail running at one more call site.
    ok_rails, failed = rails_gate(text, st.get("rails_ctx"))
    if not ok_rails:
        ledger({"event": "rails_blocked", "proposal_id": pid,      # NON-terminal
                "failed": [f[0] for f in failed], "edited": final_text is not None})
        send_text(e, render_rails_block(pid, failed), reply_to)
        return

    used = X.posts_last_24h()
    if used >= X.MAX_POSTS_24H:
        # NON-TERMINAL (fix #2): checked BEFORE the approved row is written, so a
        # capped proposal stays decidable once the cap clears. Previously
        # "approved" was ledgered first, terminally, and the retry was refused.
        ledger({"event": "cap_deferred", "proposal_id": pid, "posts_last_24h": used})
        send_text(e, "🚫 %s not posted — the 4-post/24h cap is reached (%d). Still "
                     "pending: approve again once it clears." % (pid, used), reply_to)
        return

    edited = final_text is not None
    ledger({"event": "approved", "proposal_id": pid, "final_text": text, "edited": edited})

    xenv = X.load_env(Path(X.DEFAULT_ENV))
    X.ledger_append({"event": "attempt", "text": text,
                     "note": "telegram approval %s" % pid})
    mid = X.upload_media(Path(st["image"]), xenv)
    res = X.create_tweet(text, [mid], xenv)
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
    X.ledger_append({"event": "posted", "text": text, "tweet_id": tid, "url": url,
                     "media_ids": [mid], "note": "telegram approval %s" % pid,
                     "proposal_id": pid, "format": st.get("format"),
                     "hook_type": st.get("hook_type"),
                     "composition": st.get("composition"), "tier": st.get("tier")})
    ledger({"event": "posted", "proposal_id": pid, "tweet_id": tid, "url": url,
            "final_text": text, "edited": edited, "format": st.get("format"),
            "hook_type": st.get("hook_type"),
            "composition": st.get("composition"), "tier": st.get("tier")})
    send_text(e, "✅ POSTED%s\n%s\n\n(%d/%d posts used in the last 24h)"
              % (" (your edit, verbatim)" if edited else "", url,
                 X.posts_last_24h(), X.MAX_POSTS_24H), reply_to)


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
            target = None
            if reply_mid:
                target = next((v for v in state.values()
                               if v.get("message_id") == reply_mid), None)
            if target is None and len(pending) == 1:
                target = pending[0]
            if target is None:
                if pending:
                    send_text(e, "⚠️ %d proposals pending — reply to the one you mean."
                              % len(pending), m.get("message_id"))
                continue
            verdict, payload, reason_code = parse_verdict(body)
            if verdict == "unknown":
                # NO-OP + discoverable grammar. Never a publish. The help text is
                # the whole remedy: the correct usage is learnable from a mistake.
                send_text(e, HELP, m.get("message_id"))
                continue
            if verdict == "approve":
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
