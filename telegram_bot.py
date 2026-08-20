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
  poll     -> reads replies; approve / reject / or edited text (a reply that is
              not a keyword IS the new text, taken VERBATIM)
  approve  -> posts via x_client, ledgers the tweet id, confirms with the link

Authorization: only CYPHERMARKETER_TELEGRAM_CHAT_ID may decide. Decisions are
idempotent — a proposal already decided is never acted on twice.
"""
from __future__ import annotations
import argparse, json, mimetypes, sys, time, urllib.request, urllib.error, uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import x_client as X  # noqa: E402

OFFSET_FILE = HERE / "state" / "telegram_offset.json"      # NOT CPA's state file
PROPOSAL_LEDGER = HERE / "ledger" / "proposals.jsonl"
API = "https://api.telegram.org/bot{token}"
APPROVE = {"approve", "approved", "yes", "y", "ok", "ship", "post", "go", "👍", "✅"}
REJECT = {"reject", "rejected", "no", "n", "nope", "kill", "skip", "👎", "❌"}


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
                       message_id=r.get("message_id"))
        elif ev in ("approved", "rejected", "posted", "failed"):
            cur["status"] = ev
            if r.get("url"):
                cur["url"] = r["url"]
            if r.get("final_text"):
                cur["text"] = r["final_text"]
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
        "Reply: approve · reject · or send edited text (used VERBATIM)."
        % (pid, a.note or "", text, wl, img.name)
    )
    res = send_photo(e, img, caption[:1024])
    ledger({"event": "proposed", "proposal_id": pid, "text": text, "image": str(img),
            "note": a.note, "message_id": res.get("message_id"), "weighted_len": wl})
    print("  proposed %s  (telegram message_id %s)" % (pid, res.get("message_id")))
    print("  awaiting decision in Telegram…")


# ── poll ─────────────────────────────────────────────────────────────────────
def load_offset() -> int:
    try:
        return int(json.loads(OFFSET_FILE.read_text()).get("offset", 0))
    except Exception:
        return 0


def save_offset(v: int):
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(json.dumps({"offset": v, "updated": now()}) + "\n")


def decide(e, pid: str, verdict: str, final_text: str | None, reply_to: int | None):
    st = proposal_state().get(pid)
    if not st:
        return
    if st["status"] != "pending":                    # idempotent
        send_text(e, "⚠️ %s already %s — ignoring." % (pid, st["status"]), reply_to)
        return
    if verdict == "reject":
        ledger({"event": "rejected", "proposal_id": pid})
        send_text(e, "🛑 %s rejected. Nothing posted." % pid, reply_to)
        return

    text = final_text if final_text is not None else st["text"]
    wl = X.weighted_len(text)
    if wl > 280:
        ledger({"event": "failed", "proposal_id": pid, "error": "edited text %d>280" % wl})
        send_text(e, "❌ %s: your edit is %d/280 chars — too long. Send a shorter version."
                  % (pid, wl), reply_to)
        return
    edited = final_text is not None
    ledger({"event": "approved", "proposal_id": pid, "final_text": text, "edited": edited})

    used = X.posts_last_24h()
    if used >= X.MAX_POSTS_24H:
        ledger({"event": "failed", "proposal_id": pid, "error": "24h cap reached"})
        send_text(e, "🚫 %s approved but the 4-post/24h cap is reached (%d). Not posted."
                  % (pid, used), reply_to)
        return

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
    X.ledger_append({"event": "posted", "text": text, "tweet_id": tid, "url": url,
                     "media_ids": [mid], "note": "telegram approval %s" % pid})
    ledger({"event": "posted", "proposal_id": pid, "tweet_id": tid, "url": url,
            "final_text": text, "edited": edited})
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
            m = u.get("message") or u.get("channel_post") or {}
            if str((m.get("chat") or {}).get("id", "")) != chat_id:
                continue                              # authorization: chat must match
            body = (m.get("text") or "").strip()
            if not body:
                continue
            low = body.lower()
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
            if low in APPROVE:
                decide(e, target["proposal_id"], "approve", None, m.get("message_id"))
            elif low in REJECT:
                decide(e, target["proposal_id"], "reject", None, m.get("message_id"))
            else:
                # anything else IS the replacement copy, taken verbatim
                decide(e, target["proposal_id"], "approve", body, m.get("message_id"))
            if a.once:
                return
        if a.once and j.get("result"):
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
