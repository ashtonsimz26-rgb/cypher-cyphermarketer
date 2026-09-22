#!/usr/bin/env python3.12
"""
drop_correspondent.py — Q1: two-feed RSS watch (SneakerNews + NiceKicks).

Editorial trigger, not a calendar: when the sneaker internet is talking about a
shoe TODAY and our catalog holds a pool-reachable card for it, propose an extra
same-day draft. Still capped at 4 posts/24h, still Telegram-approved.

Matching is deliberately CONSERVATIVE. A false match posts about a shoe we do
not really have, which is a rails violation (nothing imagined, nothing
unpullable shown as pullable). It requires the catalog colorway AND a model
token to both appear in the headline, and re-verifies pool reachability before
drafting. Missing a drop costs nothing; inventing one is not recoverable.
"""
from __future__ import annotations
import html, json, re, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import daily_digest as DD, editorial  # noqa: E402

FEEDS = ["https://sneakernews.com/feed/", "https://www.nicekicks.com/feed/"]
SEEN = HERE / "state" / "seen_headlines.json"
QUEUE = HERE / "state" / "drop_queue.json"
# Colorways too common to discriminate between models. A match may never rest
# on one of these alone.
GENERIC_COLORWAYS = {"black", "white", "grey", "gray", "black white", "white black",
                     "triple black", "triple white", "red", "blue", "green", "navy",
                     "brown", "tan", "cream", "bone", "sail", "olive", "pink"}


def fetch(url: str) -> list[str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 cyphermarketer/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            xml = r.read().decode("utf-8", "ignore")
    except Exception:
        return []
    return [re.sub(r"<[^>]+>", "", t).strip()
            for t in re.findall(r"<title>(.*?)</title>", xml, re.S)][1:]


def load_queue() -> list:
    try:
        return json.loads(QUEUE.read_text())
    except Exception:
        return []


def save_queue(q: list):
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE.write_text(json.dumps(q, indent=2))


def load_seen() -> set:
    try:
        return set(json.loads(SEEN.read_text()))
    except Exception:
        return set()


def save_seen(s: set):
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    SEEN.write_text(json.dumps(sorted(s)[-500:]))


def norm(s: str) -> str:
    """Lowercase, entity-decode, collapse punctuation. Feeds phrase matching."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ",
                  html.unescape(s or "").lower())).strip()


def has_phrase(haystack: str, phrase: str) -> bool:
    """Whole-phrase, word-bounded containment. 'air' must not match 'airmax'."""
    h, p = norm(haystack), norm(phrase)
    if not h or not p:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])", h) is not None


def match(headline: str, rows: list[dict]) -> dict | None:
    """STRICT. The headline must name the actual SILHOUETTE, as a whole phrase.

    The bug this replaces (p_afbd558609, 2026-08-20): headline
    "Nike Air Max Goadome Low 'Black'" matched nike_air_humara_17_black, because
    the old rule was "colorway appears in headline AND any name token appears".
    Colorway "Black" is in that headline, and the token "air" is in almost every
    Nike headline — so two generic overlaps paired a Goadome story with a Humara
    card. That would have posted a factual error about a shoe we did not match.

    The rule now: the catalog SILHOUETTE ("Air Humara 17") must appear in the
    headline as a complete, word-bounded phrase. Colorway is corroborating, and
    is required only when it is distinctive — a generic colorway can never be
    the thing that carries a match.

    This is deliberately biased toward false NEGATIVES. A missed drop costs
    nothing; a wrong pairing costs credibility we cannot buy back.
    """
    for r in rows:
        sil = r.get("silhouette") or ""
        if len(norm(sil)) < 4 or not has_phrase(headline, sil):
            continue                       # silhouette is mandatory, no exceptions
        cw = norm(r.get("colorway") or "")
        if cw and cw not in GENERIC_COLORWAYS and not has_phrase(headline, cw):
            continue                       # distinctive colorway must corroborate
        return r
    return None


def main():
    DD.run_log(event="run_start", job="drop_correspondent")
    import budget
    quiet = budget.in_quiet_hours()
    # Overnight we still POLL and MATCH (both free) — we just refuse to propose
    # or to spend on a backdrop until the morning digest drains the queue.
    import switches as SW
    # images off -> no image spend to guard (the post cap still applies)
    ok, why = budget.check(require_image=(not quiet) and SW.images_enabled())
    if not ok:
        DD.run_log(event="run_blocked", job="drop_correspondent", reason=why)
        print("  BLOCKED: %s" % why); return
    # ★ This carried `where c.is_set_reward = false` — a byte-for-byte twin of the
    # filter that kept the three set rewards out of the digest's standout pool.
    # Removing one and leaving the other would have fixed the tentpole on one
    # path and left it broken on the other. Both routes, proved from the tables.
    rows = DD._sql(DD.OBTAINABLE_CTE + """
      select c.image_name, c.rarity::text as rarity, c.name, c.colorway, c.silhouette
      from public.catalog_cards c
      join obtainable o on o.image_name=c.image_name and o.rarity=c.rarity;""")
    seen, hits = load_seen(), 0
    for feed in FEEDS:
        for title in fetch(feed):
            key = title[:120]
            if key in seen:
                continue
            seen.add(key)
            m = match(title, rows)
            if not m:
                continue
            # (b) MOMENT BAR — a correct match is still not automatically a post.
            moment, why = editorial.is_moment(title)
            if not moment:
                DD.run_log(event="drop_skipped_not_moment", headline=key, reason=why,
                           image_name=m["image_name"])
                print("  matched but skipped (%s): %s" % (why, m["image_name"]))
                continue
            DD.run_log(event="drop_match", headline=key,
                       image_name=m["image_name"], rarity=m["rarity"])
            if quiet:
                q = load_queue()
                q.append({"image_name": m["image_name"], "rarity": m["rarity"],
                          "headline": key, "queued_at": datetime.now(timezone.utc).isoformat()})
                save_queue(q)
                DD.run_log(event="drop_queued_quiet_hours", headline=key,
                           image_name=m["image_name"], queue_depth=len(q))
                print("  quiet hours — queued %s for the morning digest" % m["image_name"])
                hits += 1
                break
            built = DD.build_one({"image_name": m["image_name"], "rarity": m["rarity"],
                                  "source": "drop_correspondent", "hook": key}, card_only=False)
            if built:
                import telegram_bot as TB
                class _A:
                    text_file = str(built["text_file"])
                    # None when IMAGES_ENABLED=false — cmd_propose then sends text
                    image = str(built["image"]) if built["image"] else None
                    note = ("DROP CORRESPONDENT — headline: %r · backdrop: %s · %d/280"
                            % (key[:80], built["insp"], built["weighted"]))
                    # Same rails context as the digest path. Omitting it here would
                    # leave drop proposals silently unprotected at approve time —
                    # the half-wired state F1.5 exists to avoid.
                    rails_ctx = built["rails_ctx"]
                    format = built["format"]; hook_type = built["hook_type"]
                    # R6 — same four fields as the digest path. Omitting them here
                    # would leave drop posts unmeasurable while digest posts were
                    # measurable, which is the half-wired state F1.5 exists to avoid.
                    composition = built.get("composition")
                    tier = (built.get("cand") or {}).get("rarity")
                pid = TB.cmd_propose(_A, TB.env())
                DD.run_log(event="draft_proposed", proposal_id=pid,
                           image_name=m["image_name"], format=built["format"],
                           hook_type=built["hook_type"], weighted=built["weighted"],
                           composition=built.get("composition"),
                           tier=m.get("rarity"))
                hits += 1
            break                                     # at most one extra draft per run
        if hits:
            break
    save_seen(seen)
    DD.run_log(event="run_end", job="drop_correspondent", proposed=hits)
    print("  headlines scanned; %d proposal(s)." % hits)


if __name__ == "__main__":
    main()
