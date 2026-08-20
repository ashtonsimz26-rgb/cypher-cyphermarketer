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
import json, re, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import daily_digest as DD  # noqa: E402

FEEDS = ["https://sneakernews.com/feed/", "https://www.nicekicks.com/feed/"]
SEEN = HERE / "state" / "seen_headlines.json"
STOP = {"the", "and", "for", "with", "release", "date", "official", "images", "low",
        "high", "mid", "og", "retro", "new", "nike", "jordan", "adidas", "wmns"}


def fetch(url: str) -> list[str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 cyphermarketer/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            xml = r.read().decode("utf-8", "ignore")
    except Exception:
        return []
    return [re.sub(r"<[^>]+>", "", t).strip()
            for t in re.findall(r"<title>(.*?)</title>", xml, re.S)][1:]


def load_seen() -> set:
    try:
        return set(json.loads(SEEN.read_text()))
    except Exception:
        return set()


def save_seen(s: set):
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    SEEN.write_text(json.dumps(sorted(s)[-500:]))


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())


def match(headline: str, rows: list[dict]) -> dict | None:
    h = norm(headline)
    for r in rows:
        cw = norm(r.get("colorway"))
        if not cw or len(cw) < 4 or cw not in h:
            continue
        toks = [t for t in norm(r.get("name")).split() if t not in STOP and len(t) > 2]
        if any(t in h for t in toks):
            return r
    return None


def main():
    DD.run_log(event="run_start", job="drop_correspondent")
    import budget
    ok, why = budget.check(require_image=True)
    if not ok:
        DD.run_log(event="run_blocked", job="drop_correspondent", reason=why)
        print("  BLOCKED: %s" % why); return
    rows = DD._sql(DD.REACHABLE_CTE + """
      select c.image_name, c.rarity::text as rarity, c.name, c.colorway
      from public.catalog_cards c
      join reachable r on r.image_name=c.image_name and r.rarity=c.rarity
      where c.is_set_reward = false;""")
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
            DD.run_log(event="drop_match", headline=key,
                       image_name=m["image_name"], rarity=m["rarity"])
            built = DD.build_one({"image_name": m["image_name"], "rarity": m["rarity"],
                                  "source": "drop_correspondent", "hook": key}, card_only=False)
            if built:
                import telegram_bot as TB
                class _A:
                    text_file = str(built["text_file"]); image = str(built["image"])
                    note = ("DROP CORRESPONDENT — headline: %r · backdrop: %s · %d/280"
                            % (key[:80], built["insp"], built["weighted"]))
                TB.cmd_propose(_A, TB.env())
                hits += 1
            break                                     # at most one extra draft per run
        if hits:
            break
    save_seen(seen)
    DD.run_log(event="run_end", job="drop_correspondent", proposed=hits)
    print("  headlines scanned; %d proposal(s)." % hits)


if __name__ == "__main__":
    main()
