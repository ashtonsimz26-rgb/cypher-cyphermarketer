#!/usr/bin/env python3.12
"""
daily_digest.py — the scheduled Content Factory pass.

Selects candidates -> renders TRUE cards -> generates + composes visuals ->
rails-checks -> proposes to Telegram. Posts NOTHING itself; Phase 1 means every
post is an explicit Ashton approval in Telegram.

⚠️ INSPECTION RAIL UNDER AUTOMATION — read this before trusting the visuals.
The ratified rail is "Claude visually inspects every backdrop BEFORE it reaches
Ashton's Telegram". A launchd job runs with no Claude in the loop, so that rail
CANNOT hold as written for unattended runs. This job does not pretend otherwise:
backdrops it generates are ledgered inspection="UNINSPECTED_AUTOMATED" and every
proposal caption says so in plain words, so Ashton knows he is the first human
eye on that image. Nothing reaches the public without his approval either way.
`--card-only` renders the card on its own (no generation, no spend) for anyone
who prefers the stricter posture; the schedule's mode is a one-flag change.
"""
from __future__ import annotations
import argparse, json, subprocess, sys, random
from types import SimpleNamespace
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import x_client as X, card_render as CR, backdrop as BD, compose as CP, rails, budget, editorial  # noqa: E402

RUNS = HERE / "ledger" / "runs.jsonl"
SEED = HERE / "data" / "on_this_day.json"
OUT = HERE / "content"
POOL_FACTOR = 8   # candidates searched per proposal wanted


def run_log(**kw):
    RUNS.parent.mkdir(parents=True, exist_ok=True)
    kw.setdefault("ts", datetime.now(timezone.utc).isoformat())
    with RUNS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(kw, ensure_ascii=False) + "\n")


def _sql(q: str) -> list[dict]:
    f = HERE / "state" / "_dq.sql"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(q, encoding="utf-8")
    p = subprocess.run(["supabase", "db", "query", "--linked", "-o", "json", "-f", str(f)],
                       capture_output=True, text=True, timeout=180,
                       cwd=str(Path.home() / "Documents/openclaw/CYPHER"))
    import re
    m = re.search(r"\[.*\]", p.stdout, re.S)
    return json.loads(m.group(0)) if m else []


REACHABLE_CTE = """
with reachable as (
  select w.image_name, w.rarity from public.welcome_pool w
  union select d.image_name, d.rarity from public.daily_pool d
  union select pp.image_name, pp.rarity from public.pack_pool pp where pp.rarity is not null
  union select c.image_name, c.rarity from public.pack_pool pp
    join public.catalog_cards c on c.image_name = pp.image_name
    join public.pack_rarity_weights prw on prw.pack_type=pp.pack_type and prw.rarity=c.rarity
    where pp.rarity is null and prw.weight > 0
)"""


def is_reachable(image_name: str, rarity: str) -> bool:
    q = (REACHABLE_CTE + " select count(*) as n from reachable where image_name=%s and rarity=%s;"
         % ("'" + image_name.replace("'", "''") + "'", "'" + rarity.replace("'", "''") + "'"))
    r = _sql(q)
    return bool(r and int(r[0].get("n", 0)) > 0)


def drain_drop_queue() -> list[dict]:
    """Overnight drop matches deferred by quiet hours (FIX 2). They are first in
    line at the digest — they were newsworthy enough to match a headline."""
    import drop_correspondent as DC
    q = DC.load_queue()
    if not q:
        return []
    DC.save_queue([])                       # drained exactly once
    run_log(event="drop_queue_drained", count=len(q))
    return [{"image_name": r["image_name"], "rarity": r["rarity"],
             "source": "drop_overnight", "hook": r.get("headline", "")} for r in q]


def candidates(limit: int) -> list[dict]:
    """Overnight drop queue first, then the on-this-day seed, then standouts."""
    out, seen = [], set()
    for e in drain_drop_queue():
        if len(out) < limit and is_reachable(e["image_name"], e["rarity"]):
            out.append(e); seen.add(e["image_name"])
    try:
        seed = json.loads(SEED.read_text())
        key = datetime.now().strftime("%m-%d")
        for e in seed.get(key, []):
            if is_reachable(e["image_name"], e["rarity"]):
                out.append({**e, "source": "on_this_day"}); seen.add(e["image_name"])
    except Exception:
        pass
    if len(out) < limit:
        rows = _sql(REACHABLE_CTE + """
          select c.image_name, c.rarity::text as rarity
          from public.catalog_cards c
          join reachable r on r.image_name=c.image_name and r.rarity=c.rarity
          where c.is_set_reward = false and c.estimated_resale >= 400
          order by c.estimated_resale desc limit 40;""")
        random.shuffle(rows)
        for r in rows:
            if len(out) >= limit:
                break
            if r["image_name"] in seen:
                continue
            out.append({**r, "source": "catalog_standout", "hook": ""}); seen.add(r["image_name"])
    return out[:limit]


def build_one(cand: dict, card_only: bool) -> dict | None:
    """Returns a proposal-ready draft, or None when the BAR is not cleared.

    Returning None is a normal, healthy outcome (gate d: zero is a valid day).
    Every rejection is ledgered with its reason so the bar is auditable."""
    row = CR.fetch_card(cand["image_name"], cand["rarity"])
    if row.get("is_set_reward"):
        return None                                   # ceremony-exclusive, never showcased

    sc = row.get("style_code")
    price_ok, price_why = rails.price_claim_allowed(sc, row.get("estimated_resale"))

    # (a) HOOK GATE — before spending a cent on a render or a backdrop.
    hook_type, hook = editorial.detect_hook(
        row, source=cand.get("source", ""), price_verified=price_ok,
        headline=cand.get("hook", ""))
    if hook_type is None:
        run_log(event="skipped_no_hook", image_name=cand["image_name"], reason=hook)
        return None

    fmt = editorial.choose_format(hook_type)
    display = CR.normalize_display_name(row.get("brand", ""), row.get("name", ""))
    text = editorial.build_draft(row, hook_type, fmt, price_verified=price_ok,
                                 display_name=display)

    # (b) LEAD SPECIFICITY — the swap test.
    ok_lead, lead_why = editorial.lead_is_specific(text, row)
    if not ok_lead:
        run_log(event="skipped_generic_lead", image_name=cand["image_name"],
                format=fmt, reason=lead_why)
        return None

    wl = X.weighted_len(text)
    checks = rails.check_draft(text, card_shows_value=True, pool_reachable=True,
                               price_verified=price_ok)
    if not all(c[1] for c in checks) or wl > 280:
        run_log(event="draft_rejected_by_rails", image_name=cand["image_name"],
                failed=[c[0] for c in checks if not c[1]], weighted=wl)
        return None

    # Only now is it worth rendering and generating.
    stem = "%s_%s" % (cand["image_name"][:40], datetime.now().strftime("%Y%m%d"))
    card = OUT / f"{stem}_card.png"
    CR.render_card(cand["image_name"], cand["rarity"], card)
    visual, insp = card, "N/A (card only)"
    if not card_only:
        env = X.load_env(Path(X.DEFAULT_ENV))
        bd = OUT / f"{stem}_bd.png"
        BD.generate(BD.build_prompt(row), "3:4", bd, env)
        BD.record_verdict(str(bd), "UNINSPECTED_AUTOMATED",
                          "unattended launchd run — no Claude in the loop; Ashton is "
                          "the first human eye on this image")
        visual = OUT / f"{stem}_45.png"
        CP.compose(card, bd, "4:5", visual)
        insp = "NOT pre-inspected (automated run)"

    tf = OUT / f"{stem}.txt"; tf.write_text(text, encoding="utf-8")
    editorial.record_format(fmt)
    run_log(event="draft_built", image_name=cand["image_name"], hook_type=hook_type,
            format=fmt, weighted=wl)
    return {"text_file": tf, "image": visual, "cand": cand, "insp": insp,
            "price_ok": price_ok, "price_why": price_why, "weighted": wl,
            "hook_type": hook_type, "hook": hook, "format": fmt, "lead": lead_why,
            # RAILS CONTEXT — persisted on the proposal so rails.check_draft() can
            # re-run at APPROVE time (F1.5). The ledger row previously carried none
            # of this, so the approve path could not re-derive price_verified and
            # ran no rails at all. style_code + estimated_resale are the only
            # inputs rails.price_claim_allowed() needs; freshness is recomputed
            # from local PK history against the clock, never cached here.
            "rails_ctx": {"style_code": sc,
                          "estimated_resale": row.get("estimated_resale"),
                          "image_name": cand["image_name"]}}


def main():
    ap = argparse.ArgumentParser(description="Scheduled Content Factory digest")
    ap.add_argument("--max", type=int, default=1, help="PROPOSALS to produce (<=3); the candidate POOL searched is larger")
    ap.add_argument("--card-only", action="store_true", help="no AI backdrop, no spend")
    ap.add_argument("--source", default="digest")
    a = ap.parse_args()
    run_log(event="run_start", job=a.source, card_only=a.card_only)

    ok, why = budget.check(require_image=not a.card_only)
    if not ok:
        run_log(event="run_blocked", job=a.source, reason=why)
        print("  BLOCKED: %s" % why)
        try:
            import telegram_bot as TB
            TB.send_text(TB.env(), "⏸️ cyphermarketer %s halted: %s" % (a.source, why))
        except Exception:
            pass
        return
    n = 0
    # ★ The digest evaluated exactly --max candidates, so ONE hookless candidate
    # produced ZERO proposals (2026-08-21 09:00: a single skipped_no_hook and an
    # empty morning). --max is a cap on PROPOSALS; the pool searched must be
    # wider or a strict editorial bar guarantees silence. Search POOL_FACTOR x
    # the target, stop at the target.
    want = min(a.max, 3)
    pool = candidates(want * POOL_FACTOR)
    run_log(event="candidate_pool", job=a.source, pool=len(pool), want=want)
    for cand in pool:
        if n >= want:
            break
        try:
            built = build_one(cand, a.card_only)
        except SystemExit:
            run_log(event="candidate_failed", image_name=cand.get("image_name")); continue
        if not built:
            continue
        import telegram_bot as TB
        e = TB.env()
        note = ("%s · format=%s · HOOK[%s]: %s · lead: %s · %d/280 · backdrop: %s · price: %s"
                % (a.source, built["format"], built["hook_type"], built["hook"],
                   built["lead"], built["weighted"], built["insp"],
                   "PK-verified" if built["price_ok"] else "unverified -> omitted"))
        # NOTE: a class body cannot read an enclosing function's local, so the
        # old `class _A: note = note` raised NameError at 09:00 and killed the
        # first unattended digest AFTER it had already spent $0.04 on a backdrop.
        # SimpleNamespace has no scoping surprise.
        argv = SimpleNamespace(text_file=str(built["text_file"]),
                               image=str(built["image"]), note=note,
                               rails_ctx=built["rails_ctx"])
        TB.cmd_propose(argv, e)
        n += 1
    run_log(event="run_end", job=a.source, proposed=n)
    # Gate (d): zero is a valid outcome, and says so rather than looking broken.
    print("  proposed %d draft(s)." % n if n else
          "  proposed 0 drafts — no candidate cleared the editorial bar today. "
          "That is a valid outcome, not a failure.")


if __name__ == "__main__":
    main()
