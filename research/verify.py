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

★ "contradicted" IS PHRASING-SENSITIVE — IT IS NOT PROOF OF FALSEHOOD
  required_terms are matched with has_phrase(), which is WORD-BOUNDED and
  order-preserving. A term-order variant therefore returns "contradicted" on a
  page that plainly confirms the fact.

  CANONICAL CASE (D2, 2026-09-10). Verifying m_yeezy750_first with the entry's
  own term "Yeezy Boost 750" against NiceKicks returned:
      contradicted   found=['2015']   missing=['Yeezy Boost 750']
  The page confirms the shoe and the date — it simply writes "Yeezy 750 Boost".
  Re-probing the same URL with the reordered phrase returned "verified". The
  fact was true, the source was right, and only the word order differed.

  So: a caller must RETRY WITH PHRASING VARIANTS before treating "contradicted"
  as evidence against a claim. Deleting an entry on a single contradicted
  result will delete true entries. What "contradicted" actually means is "this
  page does not contain these exact phrases" — which is a statement about the
  terms, not about the world.

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


# ══ cypher:// — a FIRST-PARTY SOURCE (2026-09-16) ════════════════════════════
#
# Some claims have no URL and are still checkable. "A player earned serial #1 of
# a 10,000-cap GRAIL by completing a two-card set" is not on any blog; it is in
# our own database, and the database is a better source for it than a blog would
# be. So the sources rule is UNCHANGED — a moment still needs a non-empty
# sources[] and every term is still checked against a fetched document. What
# widened is the set of things a source may BE.
#
# THE GRAMMAR. Three kinds, deliberately. This is not a query language and must
# not become one; a fourth kind needs a ruling, not a patch.
#
#   cypher://card/<image_name>/<rarity>
#   cypher://set/<set_name>
#   cypher://serial/<image_name>/<rarity>/<n>
#
# Path segments are percent-encoded, so "HOLY%20GRAIL" and
# "Nike%20x%20Jordan%204%20SB" are how spaces travel.
#
# ★★ IT RESOLVES TO TEXT, AND THEN NOTHING IS SPECIAL. Each URI renders a small
# deterministic document which the EXISTING term matcher reads. That is the
# whole design: outcome, found/missing, numeric matching, the cache and the
# unverified-vs-contradicted distinction are inherited from the HTTP path rather
# than reimplemented beside it, so the two cannot drift.
#
# ★ A RESOLVER THAT CANNOT REACH THE DB RETURNS "" -> "unverified", NEVER
# "contradicted" — identical to an unreachable URL, and for the identical
# reason: silence is not evidence against a fact.
#
# ★★ NO USER IS EVER IDENTIFIED. A serial's OWNER is a private individual and
# owner_id never appears in a rendered document — not even hashed. The serial,
# the cap, the method and the timestamp are facts about the CARD; who holds it
# is not ours to publish. Enforced below and asserted in the suite.
CYPHER_SCHEME = "cypher://"
_PRIVATE_COLUMNS = ("owner_id", "user_id", "id", "email")   # never rendered


def _cypher_sql(q: str) -> list[dict]:
    """Read-only passthrough to daily_digest._sql. Raises on any failure so the
    caller can turn it into "" -> unverified."""
    assert q.lstrip().lower().startswith("select"), "cypher:// resolver is READ-ONLY"
    sys.path.insert(0, str(HERE))
    import daily_digest as DD
    return DD._sql(q)


def _lit(v: str) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def _render(title: str, rows: list[tuple[str, object]]) -> str:
    body = "\n".join("%s: %s" % (k, v) for k, v in rows if v is not None)
    return "%s\n%s\n" % (title, body)


def resolve_cypher(uri: str) -> str:
    """A cypher:// URI as a text document, or "" when it cannot be resolved.

    "" covers BOTH a malformed URI and an unreachable database. Both are
    unverified rather than contradicted — a source we cannot read says nothing
    about the claim. A malformed URI is additionally ledgered, because it is an
    authoring mistake rather than an outage and should be visible as one.
    """
    rest = uri[len(CYPHER_SCHEME):]
    parts = [urllib.parse.unquote(x) for x in rest.split("/") if x != ""]
    if not parts:
        ledger({"event": "cypher_uri_malformed", "uri": uri, "reason": "empty"})
        return ""
    kind, args = parts[0], parts[1:]
    try:
        if kind == "card" and len(args) == 2:
            image_name, rarity = args
            rows = _cypher_sql(
                "select c.image_name, c.rarity::text as rarity, c.name, c.brand, "
                "c.colorway, c.year, c.retail_price, c.estimated_resale, c.style_code, "
                "c.category, (select s.cap from public.serial_caps s "
                "  where s.image_name=c.image_name and s.rarity=c.rarity) as serial_cap "
                "from public.catalog_cards c "
                "where c.image_name=%s and c.rarity=%s;" % (_lit(image_name), _lit(rarity)))
            if not rows:
                return _render("CYPHER CATALOG CARD — NO SUCH CARD",
                               [("image_name", image_name), ("rarity", rarity)])
            r = rows[0]
            return _render("CYPHER CATALOG CARD",
                           [(k, r.get(k)) for k in
                            ("image_name", "rarity", "name", "brand", "colorway", "year",
                             "retail_price", "estimated_resale", "style_code", "category",
                             "serial_cap")])

        if kind == "set" and len(args) == 1:
            set_name = args[0]
            rw = _cypher_sql(
                "select set_name, reward_image_name, reward_rarity::text as reward_rarity "
                "from public.set_rewards where set_name=%s;" % _lit(set_name))
            rq = _cypher_sql(
                "select required_image_name from public.set_requirements "
                "where set_name=%s order by 1;" % _lit(set_name))
            cl = _cypher_sql(
                "select count(*) as n from public.claimed_set_rewards "
                "where set_name=%s;" % _lit(set_name))
            if not rw:
                return _render("CYPHER SET — NO SUCH SET", [("set_name", set_name)])
            rows = [("set_name", rw[0]["set_name"]),
                    ("reward_image_name", rw[0]["reward_image_name"]),
                    ("reward_rarity", rw[0]["reward_rarity"]),
                    ("requirement_count", len(rq))]
            rows += [("requires", q["required_image_name"]) for q in rq]
            rows += [("times_claimed", (cl[0]["n"] if cl else 0))]
            return _render("CYPHER SET", rows)

        if kind == "serial" and len(args) == 3:
            image_name, rarity, n = args
            if not n.isdigit():
                ledger({"event": "cypher_uri_malformed", "uri": uri,
                        "reason": "serial is not a number"})
                return ""
            # ★ owner_id is NOT selected. See _PRIVATE_COLUMNS.
            # ★ owned_cards.rarity is TEXT while every other table uses the
            # sneaker_rarity ENUM (catalog_cards, serial_caps, all three pools,
            # pack_rarity_weights). `s.rarity = o.rarity` therefore raises
            # "operator does not exist: sneaker_rarity = text". The cast is not
            # cosmetic — without it this resolver silently returned NOT MINTED
            # for a card that was minted twice.
            rows = _cypher_sql(
                "select o.image_name, o.rarity as rarity, o.serial_int, "
                "o.set_name, o.acquisition_method, o.minted_at, "
                "(select s.cap from public.serial_caps s "
                "  where s.image_name=o.image_name and s.rarity::text=o.rarity) as serial_cap "
                "from public.owned_cards o where o.image_name=%s and o.rarity=%s "
                "and o.serial_int=%s;" % (_lit(image_name), _lit(rarity), int(n)))
            if not rows:
                return _render("CYPHER SERIAL — NOT MINTED",
                               [("image_name", image_name), ("rarity", rarity),
                                ("serial_int", n)])
            r = rows[0]
            return _render("CYPHER SERIAL",
                           [(k, r.get(k)) for k in
                            ("image_name", "rarity", "serial_int", "serial_cap",
                             "set_name", "acquisition_method", "minted_at")])
    except Exception as e:
        # Unreachable DB, timeout, auth — all of it. NOT contradicted.
        ledger({"event": "cypher_resolve_failed", "uri": uri,
                "reason": "%s: %s" % (type(e).__name__, e)[:200]})
        return ""

    ledger({"event": "cypher_uri_malformed", "uri": uri,
            "reason": "unknown kind %r or wrong arity (%d)" % (kind, len(args))})
    return ""


def fetch_text(url: str) -> str:
    """Page text, or "" on ANY failure. Never raises.

    ★ Dispatches on scheme: cypher:// resolves against our own database and
    returns a rendered document; everything else is HTTP. The caching, term
    matching and outcome logic below are shared by both, which is the point.

    Cache hit costs no network call and no politeness sleep — nothing was
    requested, so no courtesy is owed. A stale entry whose re-fetch fails is
    KEPT: a 31-day-old page beats nothing.
    """
    cached = _cache_read(url)
    if cached is not None:
        return cached
    if url.startswith(CYPHER_SCHEME):
        text = resolve_cypher(url)
        if text:
            _cache_write(url, text)          # same cache, same TTL, same key shape
        return text                          # "" -> unverified, never contradicted
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
