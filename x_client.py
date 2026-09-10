#!/usr/bin/env python3.12
"""
x_client.py — cyphermarketer's X posting client. @appCYPHERR.

Governed by CYPHER_MARKETING_AGENT_STRATEGY.md (locked 2026-08-19) and the
cyphermarketer SOUL.md rails.

DESIGN NOTES (grounded 2026-08-19, not assumed):
  * v2 ONLY. `POST /2/media/upload` + `POST /2/tweets`. The v1.1 media endpoint
    still answers 200 despite its 2025-06-09 sunset — it is treated as DEAD and
    is never called (ruling Q5).
  * OAuth 1.0a user context for BOTH calls. Probed live: /2/media/upload accepts
    OAuth 1.0a and takes a simple single-request multipart for images — no
    INIT/APPEND/FINALIZE chunking. Public docs disagree with each other on this;
    the probe is the authority.
  * Credentials load from an env file BY PATH and are never logged, echoed, or
    written to the ledger.

SAFETY:
  * Posting requires an explicit --post flag. Default is a dry run.
  * Append-only ledger records INTENT before the network call and OUTCOME after,
    so a crash mid-flight is still visible (shadow-ledger pattern, per CPA).
  * Hard cap of 4 posts / rolling 24h, enforced against the ledger.
  * Refuses text over X's 280 weighted-character limit.
"""
from __future__ import annotations
import argparse, base64, hashlib, hmac, json, os, re, secrets, sys, time, uuid
import urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ENV = Path.home() / "Documents/openclaw/cyphermarketer/.env"
LEDGER = Path(__file__).resolve().parent / "ledger" / "posts.jsonl"
MEDIA_URL = "https://api.x.com/2/media/upload"
TWEET_URL = "https://api.x.com/2/tweets"
USER_ID = "2085855313014448128"                    # @appCYPHERR
# OWNED-READ form. Deliberately NOT `GET /2/tweets?ids=`: X prices an "owned
# resource read" at $0.001 only when the {id} path param matches the
# authenticated user, so ?ids= risks billing as standard post reads at $0.005 —
# 5x for identical data. This form also returns every post in ONE request.
OWN_POSTS_URL = "https://api.x.com/2/users/%s/tweets" % USER_ID
HANDLE = "appCYPHERR"
METRICS_LEDGER = Path(__file__).resolve().parent / "ledger" / "metrics.jsonl"
MAX_POSTS_24H = 4
MAX_IMAGE_BYTES = 5 * 1024 * 1024
REQUIRED = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")


def die(msg: str, code: int = 2):
    sys.stderr.write("FATAL: %s\n" % msg)
    raise SystemExit(code)


def load_env(path: Path) -> dict:
    if not path.exists():
        die("env file not found: %s" % path)
    if (path.stat().st_mode & 0o077) != 0:
        sys.stderr.write("WARN: %s is group/world readable — chmod 600 it.\n" % path)
    d = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip().strip('"').strip("'")
    missing = [k for k in REQUIRED if not d.get(k)]
    if missing:
        die("env missing keys: %s" % ", ".join(missing))   # names only, never values
    return d


# ── X weighted length ────────────────────────────────────────────────────────
def weighted_len(text: str) -> int:
    """X counts most chars 1, others (emoji, CJK, some punctuation) 2, and every
    URL as exactly 23 regardless of real length (t.co wrapping)."""
    body = re.sub(r"https?://\S+", "", text)
    n_urls = len(re.findall(r"https?://\S+", text))

    def w(ch):
        o = ord(ch)
        light = (0x0000 <= o <= 0x10FF or 0x2000 <= o <= 0x200D
                 or 0x2010 <= o <= 0x201F or 0x2032 <= o <= 0x2037)
        return 1 if light else 2

    return sum(w(c) for c in body) + 23 * n_urls


# ── OAuth 1.0a ───────────────────────────────────────────────────────────────
def _pe(s) -> str:
    return urllib.parse.quote(str(s), safe="-._~")


def _auth_header(method: str, url: str, env: dict) -> str:
    """OAuth 1.0a header.

    NOTE: query-string params MUST be folded into the signature base string or
    the request 401s. Body params are NOT (JSON bodies and multipart uploads are
    excluded by spec) — which is why POST /2/tweets and /2/media/upload sign
    correctly with no extra handling, while a GET with a query string does not.
    Found the hard way verifying the first post (2026-08-19).
    """
    parsed = urllib.parse.urlsplit(url)
    url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    q = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
    p = {
        "oauth_consumer_key": env["X_API_KEY"],
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": env["X_ACCESS_TOKEN"],
        "oauth_version": "1.0",
    }
    allp = dict(p); allp.update(q)
    base = "&".join([method, _pe(url),
                     _pe("&".join("%s=%s" % (_pe(k), _pe(allp[k])) for k in sorted(allp)))])
    key = ("%s&%s" % (_pe(env["X_API_SECRET"]), _pe(env["X_ACCESS_TOKEN_SECRET"]))).encode()
    p["oauth_signature"] = base64.b64encode(
        hmac.new(key, base.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join('%s="%s"' % (_pe(k), _pe(v)) for k, v in sorted(p.items()))


def _request(req) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:                      # never surface credential-bearing detail
        return 0, json.dumps({"transport_error": type(e).__name__})


# ── ledger (append-only) ─────────────────────────────────────────────────────
def ledger_append(rec: dict):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec)
    rec.setdefault("ts", datetime.now(timezone.utc).isoformat())
    with LEDGER.open("a", encoding="utf-8") as fh:     # append-only, never rewritten
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def posts_last_24h() -> int:
    if not LEDGER.exists():
        return 0
    cutoff = time.time() - 86400
    n = 0
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("event") != "posted":
            continue
        try:
            if datetime.fromisoformat(r["ts"]).timestamp() >= cutoff:
                n += 1
        except Exception:
            pass
    return n


# ── API ──────────────────────────────────────────────────────────────────────
def upload_media(path: Path, env: dict) -> str:
    data = path.read_bytes()
    if len(data) > MAX_IMAGE_BYTES:
        die("image %s is %d bytes, over X's 5MB limit" % (path.name, len(data)))
    boundary = "----cypher" + uuid.uuid4().hex
    body = b""
    for k, v in (("media_category", "tweet_image"),):
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                 % (boundary, k, v)).encode()
    body += ("--%s\r\nContent-Disposition: form-data; name=\"media\"; filename=\"%s\"\r\n"
             "Content-Type: image/png\r\n\r\n" % (boundary, path.name)).encode()
    body += data + b"\r\n" + ("--%s--\r\n" % boundary).encode()
    req = urllib.request.Request(MEDIA_URL, data=body, headers={
        "Authorization": _auth_header("POST", MEDIA_URL, env),
        "Content-Type": "multipart/form-data; boundary=%s" % boundary,
        "User-Agent": "cyphermarketer/1.0"})
    status, raw = _request(req)
    if status != 200:
        die("media upload failed (HTTP %s): %s" % (status, raw[:300]))
    return json.loads(raw)["data"]["id"]


def create_tweet(text: str, media_ids: list[str], env: dict) -> dict:
    payload = {"text": text}
    if media_ids:
        payload["media"] = {"media_ids": media_ids}
    req = urllib.request.Request(TWEET_URL, data=json.dumps(payload).encode(), headers={
        "Authorization": _auth_header("POST", TWEET_URL, env),
        "Content-Type": "application/json",
        "User-Agent": "cyphermarketer/1.0"})
    status, raw = _request(req)
    return {"status": status, "raw": raw}


# ── reads (F2) ───────────────────────────────────────────────────────────────
def get_own_posts(env: dict, *, max_results: int = 100,
                  non_public: bool = True) -> tuple[int, dict]:
    """One owned read of our own timeline, with metrics.

    non_public_metrics (impressions, profile clicks, link clicks, engagements)
    require OAuth 1.0a user context — which is what we already use — and are
    only available for posts created in the LAST 30 DAYS. public_metrics never
    expire. The caller records which it actually got per post rather than
    writing silent nulls.

    The OAuth signer already folds query-string params into the signature base
    (verified), so a GET needs no new auth handling.
    """
    fields = "public_metrics,created_at"
    if non_public:
        fields += ",non_public_metrics"
    url = "%s?max_results=%d&tweet.fields=%s" % (
        OWN_POSTS_URL, max_results, urllib.parse.quote(fields, safe=","))
    req = urllib.request.Request(url, headers={
        "Authorization": _auth_header("GET", url, env),
        "User-Agent": "cyphermarketer/1.0"})
    status, raw = _request(req)
    try:
        return status, json.loads(raw)
    except Exception:
        return status, {"unparsed": raw[:800]}


def metrics_append(rec: dict):
    METRICS_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec)
    rec.setdefault("sampled_at", datetime.now(timezone.utc).isoformat())
    with METRICS_LEDGER.open("a", encoding="utf-8") as fh:      # append-only
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Post to X as @appCYPHERR. Dry-run unless --post.")
    ap.add_argument("--text-file", required=True, help="UTF-8 file holding the EXACT post text")
    ap.add_argument("--image", action="append", default=[], help="image path (repeatable, max 4)")
    ap.add_argument("--env", default=str(DEFAULT_ENV))
    ap.add_argument("--post", action="store_true", help="actually publish (default: dry run)")
    ap.add_argument("--note", default="", help="ledger annotation, e.g. why this post exists")
    a = ap.parse_args()

    text = Path(a.text_file).read_text(encoding="utf-8").rstrip("\n")
    if not text.strip():
        die("post text is empty")
    wl = weighted_len(text)
    if wl > 280:
        die("text is %d weighted chars, over X's 280 limit" % wl)
    if len(a.image) > 4:
        die("X allows at most 4 images")
    for p in a.image:
        if not Path(p).exists():
            die("image not found: %s" % p)

    sha = hashlib.sha256(text.encode()).hexdigest()[:16]
    print("  handle          : @%s" % HANDLE)
    print("  weighted length : %d / 280" % wl)
    print("  text sha256[:16]: %s" % sha)
    for p in a.image:
        print("  image           : %s (%d bytes)" % (Path(p).name, Path(p).stat().st_size))

    used = posts_last_24h()
    print("  posts last 24h  : %d / %d" % (used, MAX_POSTS_24H))
    if a.post and used >= MAX_POSTS_24H:
        die("4-post/24h cap reached — refusing to post (strategy doc hard rail)")

    if not a.post:
        print("\n  DRY RUN — nothing uploaded, nothing posted. Re-run with --post to publish.")
        return

    env = load_env(Path(a.env))
    ledger_append({"event": "attempt", "text": text, "text_sha256_16": sha,
                   "images": [Path(p).name for p in a.image], "note": a.note})

    media_ids = []
    for p in a.image:
        mid = upload_media(Path(p), env)
        print("  uploaded        : %s -> media_id %s" % (Path(p).name, mid))
        media_ids.append(mid)

    res = create_tweet(text, media_ids, env)
    if res["status"] not in (200, 201):
        ledger_append({"event": "failed", "text_sha256_16": sha,
                       "http_status": res["status"], "error": res["raw"][:500]})
        die("create tweet failed (HTTP %s): %s" % (res["status"], res["raw"][:400]))

    tid = json.loads(res["raw"])["data"]["id"]
    url = "https://x.com/%s/status/%s" % (HANDLE, tid)
    ledger_append({"event": "posted", "text": text, "text_sha256_16": sha,
                   "tweet_id": tid, "url": url, "media_ids": media_ids, "note": a.note})
    print("\n  POSTED ✅  %s" % url)


if __name__ == "__main__":
    main()
