#!/usr/bin/env python3.12
"""
verify.py — SOURCE VERIFICATION for facts before they are allowed into copy.

WHAT THIS IS FOR
  SOUL.md's editorial bar item f: any date, year, designer or story fact we
  post must trace to a source. This module is the primitive that checks a
  claim against a page and reports what it found. It decides nothing about
  what to do with the answer — that mapping is the caller's, next batch.

★ "unverified" IS NOT EVIDENCE AGAINST A FACT
  Three outcomes, and the middle one is the trap:
    "verified"      the page loaded and every required term is present
    "contradicted"  the page loaded and at least one term is absent
    "unverified"    the page did NOT load — 404, timeout, DNS, anything
  A 404 says nothing whatsoever about whether the fact is true. Treating
  "unverified" as a rail failure silently discards TRUE facts and starves the
  proposal pipeline; treating it as a pass lets unchecked claims through.
  Callers must branch on `outcome`, never on `ok` alone. `ok` is a convenience
  for the "verified" case only.

NO LLM. NO PAID CALLS. stdlib only.

SHARED PRIMITIVES ARE BORROWED, NEVER MODIFIED
  norm() and has_phrase() are imported from drop_correspondent, which depends
  on their exact semantics for headline matching. This module adds matching on
  top of them; it must never change them.
"""

from __future__ import annotations

import hashlib
import html
import html.parser
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from drop_correspondent import has_phrase, norm          # noqa: E402  shared, unmodified

CACHE_DIR = HERE / "state" / "url_cache"                 # state/ is gitignored
LEDGER = HERE / "ledger" / "research.jsonl"

USER_AGENT = "Mozilla/5.0 cyphermarketer/1.0"
TIMEOUT = 30                                             # matches goat_import
CACHE_TTL_SECONDS = 30 * 24 * 3600
HOST_DELAY = 0.5

_last_hit: dict[str, float] = {}                         # host -> monotonic


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ledger(rec: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec)
    rec.setdefault("ts", now())
    with LEDGER.open("a", encoding="utf-8") as fh:       # append-only
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ── html -> text ────────────────────────────────────────────────────────────
class _Stripper(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._out, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self._out.append(data)

    def text(self) -> str:
        return re.sub(r"\s+", " ", "".join(self._out)).strip()


def strip_html(raw: str) -> str:
    p = _Stripper()
    try:
        p.feed(raw)
        p.close()
    except Exception:
        raw = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)).strip()
    return p.text()


# ── cache ───────────────────────────────────────────────────────────────────
def _cache_path(url: str) -> Path:
    return CACHE_DIR / ("%s.txt" % hashlib.sha256(url.encode("utf-8")).hexdigest())


def _cache_read(url: str) -> str | None:
    p = _cache_path(url)
    try:
        if p.exists() and (time.time() - p.stat().st_mtime) < CACHE_TTL_SECONDS:
            return p.read_text(encoding="utf-8")
    except OSError:
        pass
    return None


def _cache_write(url: str, text: str) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(url).write_text(text, encoding="utf-8")
    except OSError:
        pass                                             # a cache miss is not a failure


def _polite(url: str) -> None:
    """0.5s between requests to the SAME host. Verifying three facts on one
    domain should not sleep against two unrelated ones."""
    try:
        host = urllib.parse.urlparse(url).netloc or url
    except Exception:
        host = url
    last = _last_hit.get(host)
    if last is not None:
        gap = time.monotonic() - last
        if gap < HOST_DELAY:
            time.sleep(HOST_DELAY - gap)
    _last_hit[host] = time.monotonic()


def fetch_text(url: str) -> str:
    """Page text, or "" on ANY failure. Never raises.

    Cache hit costs no network call and no politeness sleep — nothing was
    requested, so no courtesy is owed. A stale entry whose re-fetch fails is
    KEPT: a 31-day-old page beats nothing.
    """
    cached = _cache_read(url)
    if cached is not None:
        return cached
    _polite(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read().decode("utf-8", "ignore")     # lossy, same as fetch()
    except Exception as e:
        reason = "HTTP %s" % e.code if isinstance(e, urllib.error.HTTPError) else \
                 "%s: %s" % (type(e).__name__, e)
        ledger({"event": "verify_fetch_failed", "url": url, "reason": reason[:200]})
        stale = _cache_path(url)
        if stale.exists():                               # do NOT delete on failure
            try:
                return stale.read_text(encoding="utf-8")
            except OSError:
                pass
        return ""
    text = strip_html(raw)
    _cache_write(url, text)
    return text


# ── numeric matching ────────────────────────────────────────────────────────
# WHY THIS EXISTS, precisely.
# has_phrase() ALREADY guards bare digit runs: its (?<![a-z0-9])/(?![a-z0-9])
# lookarounds correctly reject "65" inside "650", "1965" and "x650x". Verified
# 2026-09-09. What it cannot guard is SEPARATORS, because norm() strips "." and
# "," to spaces before matching:
#     "$65.99"  -> "65 99"  -> has_phrase("65")  == True   ← WRONG, that is $65.99
#     "1,650"   -> "1 650"  -> has_phrase("650") == True   ← WRONG, that is 1,650
# A false verification is worse than a failed one: it green-lights the claim.
# So numeric terms are matched against the RAW text, where the separators still
# exist, requiring the digit run to be bounded by neither a digit nor a
# separator-followed-by-a-digit. norm()/has_phrase() are untouched.
_NUM_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _parse_num(tok: str):
    """'1,650.00' -> 1650.0. None if it is not a clean number."""
    try:
        return float(tok.replace(",", ""))
    except ValueError:
        return None


def _numeric_present(raw_text: str, term: str) -> bool:
    """True iff the page contains a number of EQUAL VALUE to `term`.

    Value comparison, not pattern matching, because the separators are the
    whole problem and they are not decorative:
        "$65.99"  is not $65        "1,650"   is not 650
        "650.00"  IS   $650         "1965"    is not 65
    Matching on text would have to choose between rejecting "650.00" (a false
    negative on a correct claim) and accepting "650.99" (a false verification,
    which is worse). Parsing both sides sidesteps the choice entirely.

    Use for prices, years, counts. NOT for style codes — "304292-051" is an
    identifier, not a quantity; route those through required_terms, where
    has_phrase's word boundaries already handle them correctly.
    """
    want = _parse_num(re.sub(r"[^\d.,]", "", str(term or "")))
    if want is None:
        return False
    hay = html.unescape(raw_text or "")
    for m in _NUM_TOKEN.finditer(hay):
        got = _parse_num(m.group(0))
        if got is not None and got == want:
            return True
    return False


def verify_fact(url: str, required_terms: list[str],
                numeric_terms: list[str] | None = None) -> dict:
    """Check that a page supports a claim.

    outcome: "verified" | "contradicted" | "unverified" — branch on THIS.
      unverified  = the page did not load. NOT evidence the fact is false.
      contradicted= the page loaded and a term is absent.
      verified    = the page loaded and every term is present.

    required_terms  matched with has_phrase() (word-bounded, shared semantics)
    numeric_terms   matched separator-aware against raw text; use for prices,
                    years, style codes — anything where "65" must not be
                    satisfied by "$65.99" or "1,650".
    """
    numeric_terms = list(numeric_terms or [])
    cached = _cache_read(url) is not None
    text = fetch_text(url)
    if not text:
        return {"outcome": "unverified", "ok": False, "fetched": False,
                "found": [], "missing": list(required_terms) + numeric_terms,
                "url": url, "cached": cached, "reason": "fetch_failed"}

    found, missing = [], []
    for t in required_terms:
        (found if has_phrase(text, t) else missing).append(t)
    for t in numeric_terms:
        (found if _numeric_present(text, t) else missing).append(t)

    ok = not missing
    return {"outcome": "verified" if ok else "contradicted", "ok": ok,
            "fetched": True, "found": found, "missing": missing,
            "url": url, "cached": cached,
            "reason": None if ok else "missing_terms"}
