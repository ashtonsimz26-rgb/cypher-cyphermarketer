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
from research import compose_text as CT  # noqa: E402  (assembly; owns attribution + link)
from research import writer as WR, composition as COMP, rotation as ROT  # noqa: E402
from research import selector as SEL, moments as MOM  # noqa: E402
from research import dossier as DOS  # noqa: E402  (hook/lineage/support rails)

# ⚠ EDITING THIS FILE PROGRAMMATICALLY: assert the match count before every
# replace (see README "Working conventions"). The moment-lane fallback below
# was inserted by an unasserted replace whose anchor had already been rewritten
# earlier in the same script — it matched nothing, changed nothing, and
# reported success, turning a wrong-post bug into a no-post bug.

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


# ── the obtainability cache rails reads ──────────────────────────────────────
# ★ rails.py must not grow DB access, so the verdict it needs is written here,
# where _sql already lives. REGENERATED AT THE START OF EVERY DIGEST RUN. That
# is the answer to "what happens if nothing regenerates it for 8 days": the
# digest has not run for 8 days, so nothing is posting anyway — and rails then
# fails every card closed and says why, rather than producing a silent empty
# morning. refresh_set_routes() failing is logged and NOT swallowed.
SET_ROUTES = HERE / "state" / "_set_routes.json"


def refresh_set_routes() -> dict:
    """Write state/_set_routes.json: every reachable (image_name, rarity) pair,
    plus every set_rewards route with its requirements PROVEN reachable.

    The requirement reachability is resolved HERE, in SQL, so rails never has to
    assume it. Reads set_rewards, the TABLE — never catalog_cards.is_set_reward,
    which disagrees with it (aj4_sb_varsity_red is flagged at two tiers while
    set_rewards names one)."""
    pairs = _sql(REACHABLE_CTE + """
      select distinct r.image_name, r.rarity::text as rarity from reachable r
      where r.rarity is not null;""")
    rows = _sql(REACHABLE_CTE + """
      select sr.set_name, sr.reward_image_name, sr.reward_rarity::text as reward_rarity,
             q.required_image_name,
             (select count(*) from reachable r where r.image_name = q.required_image_name) as req_reachable
      from public.set_rewards sr
      join public.set_requirements q on q.set_name = sr.set_name
      order by sr.set_name, q.required_image_name;""")
    routes: dict = {}
    for r in rows:
        key = "%s|%s" % (r["reward_image_name"], r["reward_rarity"])
        e = routes.setdefault(key, {"set_name": r["set_name"], "requirements": []})
        e["requirements"].append({"image_name": r["required_image_name"],
                                  "reachable": int(r["req_reachable"] or 0) > 0})
    # AUDIT ONLY, never consulted for a verdict: the pairs catalog_cards FLAGS as
    # set rewards. It disagrees with set_rewards and that disagreement is the
    # reason this code reads the table. Recorded so a test can assert the drift
    # offline instead of needing the DB.
    flagged = _sql("""select image_name, rarity::text as rarity
      from public.catalog_cards where is_set_reward order by 1, 2;""")
    blob = {"_note": ("Despite the name this file carries BOTH halves of the "
                      "obtainability verdict: `reachable_pairs` (the PULL route) and "
                      "`routes` (the EARN route). They live together because proving a "
                      "set route REQUIRES requirement reachability — splitting them "
                      "would mean two caches with two staleness windows answering one "
                      "question. rails.py reads this and grows no DB access. "
                      "`flagged_is_set_reward` is AUDIT ONLY and is never consulted for "
                      "a verdict. Regenerated at the start of every digest run; older "
                      "than rails.FRESHNESS_DAYS and every card fails closed."),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "reachable_pairs": sorted("%s|%s" % (p["image_name"], p["rarity"]) for p in pairs),
            "routes": routes,
            "flagged_is_set_reward": sorted("%s|%s" % (f["image_name"], f["rarity"])
                                            for f in flagged)}
    SET_ROUTES.parent.mkdir(parents=True, exist_ok=True)
    SET_ROUTES.write_text(json.dumps(blob, indent=1, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    run_log(event="set_routes_refreshed", pairs=len(blob["reachable_pairs"]),
            routes=len(routes),
            earnable=sum(1 for v in routes.values()
                         if v["requirements"] and all(q["reachable"] for q in v["requirements"])))
    return blob


def _route_entry(image_name: str, rarity: str) -> dict | None:
    routes, _why = rails.load_set_routes()
    if not routes:
        return None
    return (routes.get("routes") or {}).get("%s|%s" % (image_name, rarity))


def _set_name(image_name: str, rarity: str) -> str:
    e = _route_entry(image_name, rarity)
    return (e or {}).get("set_name") or ""


def _set_requirement_names(image_name: str, rarity: str) -> list[str]:
    """Colorway names of the cards the set needs, for the copy skeleton.

    Catalog fields only — the skeleton has no free-text slot and this must not
    become one. A name that cannot be resolved is DROPPED rather than guessed.

    NOT CR.fetch_card: that needs an exact (image_name, rarity) and die()s when
    it misses, which would take the whole run down for a cosmetic name. One
    query, keyed on image_name, tolerant of a miss."""
    e = _route_entry(image_name, rarity)
    reqs = [q.get("image_name") for q in (e or {}).get("requirements") or [] if q.get("image_name")]
    if not reqs:
        return []
    lits = ", ".join("'" + r.replace("'", "''") + "'" for r in reqs)
    try:
        rows = _sql("select distinct image_name, colorway, name from public.catalog_cards "
                    "where image_name in (%s);" % lits)
    except Exception:
        return []
    by = {r["image_name"]: r for r in rows}
    out = []
    for r in reqs:                          # preserve the set's own order
        row = by.get(r) or {}
        nm = (row.get("colorway") or "").strip() or (row.get("name") or "").strip()
        if nm:
            out.append(nm)
    return out


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


BUILD_ONE_READS = frozenset({"dossier_sensitivity"})
PICK_COMPOSITION_READS = frozenset({"format", "hook_type", "brand", "scene",
                                    "tentpole", "rotation_history"})
GATE8_READS = frozenset({"text", "price_verified", "composition"})
OCCASION_READS = frozenset({"image_name", "day", "moment", "anniversary_age",
                            "release_date"})


def occasion_for(image_name: str, day) -> tuple[dict | None, dict | None]:
    """(occasion, moment). WHY this post exists today — the writer's real hook.

    The selector computes anniversary_age; if it never reaches the writer the
    rule is inert (R3). This is the digest-side half of that wiring.
    """
    key = "%02d-%02d" % (day.month, day.day)
    for m in MOM.proposable(key):
        if image_name in (m.get("linked_image_names") or []):
            return {"kind": "verified_moment", "today": key}, m
    age = SEL.anniversary_age(image_name, day, SEL.load_release_dates())
    if age is not None:
        return {"kind": "round_anniversary", "years": age,
                "today": day.isoformat()}, None
    return None, None


def pick_composition(fmt: str, hook_type: str, brand: str, scene: str,
                     tentpole: bool = False) -> str:
    """First composition that clears depth-3 rotation, in a PREFERENCE ORDER
    that depends on the occasion — rotation is not uniform (G3).

    A moment-lane or round-anniversary post is a TENTPOLE and gets the strong
    compositions. no_backdrop is a dark card on a dark gradient with a small
    shoe inside a window; it is the weakest of the set and it is what the
    2026-09-11 post got. It belongs on ordinary days, not on the day the story
    is worth telling.

    shoe_crop leads both orders because the SHOE is the subject there — and it
    is the only composition that crops the EST. VALUE row out of frame, so it
    is also the one that needs no attribution sentence (G2).
    """
    # No-attribution compositions lead both orders (they need no disclaimer),
    # but the order is only a PREFERENCE — the no-repeat rule below is what
    # actually produces variety.
    order = (["shoe_only", "angled", "two_card_crop", "shoe_crop", "off_centre",
              "poster", "close_crop", "hero"]
             if tentpole else
             ["shoe_crop", "angled", "shoe_only", "two_card_crop", "no_backdrop",
              "poster", "close_crop", "off_centre", "hero"])
    hist = ROT.recent()
    # PASS 1: first candidate that has not been used in the last 3 proposals.
    for name in order:
        if not ROT.composition_used_recently(name, hist):
            return name
    hist = ROT.recent()
    for name in order:
        cand = {"format": fmt, "hook_type": hook_type, "brand": brand,
                "composition": name, "scene": scene}
        ok, _why = ROT.is_varied(cand, hist)
        if ok:
            return name
    return order[0]


def gate8(text: str, price_ok: bool, composition: str | None = None,
          image_name: str | None = None, rarity: str | None = None
          ) -> tuple[bool, list[str]]:
    """rails.check_draft on the ASSEMBLED text, plus the 280 ceiling.

    card_shows_value is passed exactly as it always has been, so this call site
    treats the rail identically — gate 8 is the SAME rail moved EARLIER, never a
    different one.

    ★ pool_reachable=True is GONE (2026-09-16). It was a hardcoded literal, so
    the obtainability rail could not fail here however wrong the card was. The
    pair is passed instead and rails derives the verdict itself.
    """
    # card_shows_value is COMPUTED from the composition (G2), never hardcoded.
    # An unknown composition falls back to True — fail closed.
    shows = COMP.card_shows_value(composition) if composition else True
    checks = rails.check_draft(text, card_shows_value=shows,
                               price_verified=price_ok,
                               image_name=image_name, rarity=rarity)
    failed = [c.label for c in checks if not c.passed]
    if X.weighted_len(text) > 280:
        failed = failed + ["over 280 weighted characters"]
    return (not failed), failed


def skeleton_draft_fn(ctx: dict, attempt: int, failed_rails: list[str]) -> dict | None:
    """Default drafter until F4.4 lands: the existing template, adapted to
    return only the LEAD. build_draft assembles lead + attribution + link; the
    composer owns the last two now, so we take the lead and drop the tail.
    It cannot act on failed_rails — a template has nothing to revise."""
    if attempt > 1:
        return None                       # retrying a deterministic template is pointless
    full = editorial.build_draft(ctx["row"], ctx["hook_type"], ctx["fmt"],
                                 price_verified=ctx["price_ok"],
                                 display_name=ctx["display"])
    return {"lead": full.split("\n\n")[0], "body": None}


def draft_with_gate8(cand, row, fmt, hook_type, display, price_ok, *,
                     draft_fn, max_retries: int = 2, moment: dict | None = None,
                     composition: str | None = None):
    """Draft -> compose -> gate 8, retrying with the failed rail labels fed back.

    Returns (text|None, failed_rails, attempts). Bounded at 1 + max_retries:
    repeated failure on the same facts means the FACTS are the problem, not the
    phrasing, so re-prompting further is waste.
    """
    ctx = {"cand": cand, "row": row, "fmt": fmt, "hook_type": hook_type,
           "display": display, "price_ok": price_ok}
    attr = COMP.card_shows_value(composition) if composition else True
    failed: list[str] = []
    attempt = 0
    for attempt in range(1, max_retries + 2):
        parts = draft_fn(ctx, attempt, failed)
        if not parts or not (parts.get("lead") or "").strip():
            break
        if moment:
            # MOMENT LANE: the approved post_text ships VERBATIM and the writer
            # supplies only a linking line. Composing the lead alone would drop
            # the verified moment and leave a dangling reference ("that day"
            # with no antecedent) — caught in the 2026-02-22 dry run.
            text = CT.compose(moment_text=moment["post_text"], moment_id=moment["id"],
                              linking_line=parts["lead"], include_link=False,
                              include_attribution=attr)
        else:
            text = CT.compose(lead=parts["lead"], body=parts.get("body"),
                              include_link=False, include_attribution=attr)
        ok, failed = gate8(text, price_ok, composition,
                           cand.get("image_name"), cand.get("rarity"))
        if ok:
            return text, [], attempt
        run_log(event="writer_gate_failed", proposal_id=None,
                image_name=cand["image_name"], failed_rails=failed, attempt=attempt)
    if moment:
        # An approved moment plus a card is ALREADY a complete post. The linking
        # line is enhancement, not requirement — ship without it rather than
        # lose the day (ruled). Reached when the writer declines or its line
        # fails gate 8 twice.
        bare = CT.compose(moment_text=moment["post_text"], moment_id=moment["id"],
                          linking_line=None, include_link=False,
                          include_attribution=attr)
        ok, bare_failed = gate8(bare, price_ok, composition,
                                cand.get("image_name"), cand.get("rarity"))
        if ok:
            run_log(event="moment_shipped_without_linking_line",
                    image_name=cand["image_name"], attempts=attempt)
            return bare, [], attempt
        failed = bare_failed
    return None, failed, attempt


def build_one(cand: dict, card_only: bool, draft_fn=None,
              max_retries: int = 2, moment: dict | None = None) -> dict | None:
    """Returns a proposal-ready draft, or None when the BAR is not cleared.

    Returning None is a normal, healthy outcome (gate d: zero is a valid day).
    Every rejection is ledgered with its reason so the bar is auditable."""
    # ★★ R2 GATE — FIRST, BEFORE THE CATALOG ROW IS EVEN FETCHED.
    # candidates() builds the pool DIRECTLY from Supabase and never calls
    # selector.eligibility(), so the selector-side gate does NOT cover this
    # path. Both Doernbecher cards clear the pool's estimated_resale >= 400
    # filter, so a selector-only rail would have been completely inert here —
    # the sixth instance of that shape if it had shipped.
    if not DOS.dossier_proposable(cand["image_name"]):
        run_log(event="skipped_human_copy_required", image_name=cand["image_name"],
                reason="dossier sensitivity is not proposable by the generated-text path")
        return None
    row = CR.fetch_card(cand["image_name"], cand["rarity"])
    # ★ AMENDED 2026-09-16. This guard used to be absolute, and it — not the
    # rail — was what actually kept the three set rewards off the feed. The
    # amendment unlocks nothing without it.
    #
    # It now defers to rails.obtainability, which reads set_rewards THE TABLE.
    # catalog_cards.is_set_reward is NOT authoritative and must never be used
    # for this: it is flagged on four rows while set_rewards names three
    # (aj4_sb_varsity_red carries the flag at Legendary AND GRAIL, but only the
    # GRAIL row is a reward). A flag-driven guard would let the Legendary row
    # through as "earnable" when nothing can earn it.
    _ok, _route, _why = rails.obtainability(cand["image_name"], cand["rarity"])
    if not _ok:
        run_log(event="skipped_not_obtainable", image_name=cand["image_name"],
                rarity=cand.get("rarity"), reason=_why)
        return None
    if row.get("is_set_reward") and _route != "earn":
        run_log(event="skipped_set_reward_not_earnable",
                image_name=cand["image_name"], rarity=cand.get("rarity"),
                reason=_why)
        return None                                   # flagged, but nothing can earn it

    sc = row.get("style_code")
    price_ok, price_why = rails.price_claim_allowed(sc, row.get("estimated_resale"))

    # (a) HOOK GATE — before spending a cent on a render or a backdrop.
    # the dossier's verified hook facts now reach the hook selector (R1/R2)
    _dp = HERE / "data" / "dossiers" / ("%s.json" % cand["image_name"])
    _dj = None
    try:
        _dj = json.loads(_dp.read_text())
        _hooks = DOS.hook_facts(_dj)          # sensitivity-filtered at the source
    except Exception:
        _hooks = []
    # ★ the EARN route reaches the hook selector. _route was already proved above
    # by rails.obtainability; passing it here is what lets set_completion be
    # SELECTED rather than merely declared — the failure mode that kept
    # which_would_you_pull unbuilt for a month.
    if _route == "earn":
        row = dict(row)
        row["set_name"] = _set_name(cand["image_name"], cand["rarity"])
        row["set_requirements"] = _set_requirement_names(cand["image_name"], cand["rarity"])
    hook_type, hook = editorial.detect_hook(
        row, source=cand.get("source", ""), price_verified=price_ok,
        headline=cand.get("hook", ""), hook_facts=_hooks,
        earn_route=(_route == "earn"))
    if hook_type is None:
        run_log(event="skipped_no_hook", image_name=cand["image_name"], reason=hook)
        return None

    fmt = editorial.choose_format(hook_type)
    display = CR.normalize_display_name(row.get("brand", ""), row.get("name", ""))

    # ── GATE 8 (F4.3) — rails at GENERATION time, inside the PRE-SPEND block ──
    # The draft is produced, gated, and retried BEFORE render_card or
    # BD.generate. A gate-8 failure therefore costs $0.00: the $0.04 backdrop
    # is only reached by a draft that has already passed.
    # ── composition FIRST (G2): card_shows_value decides whether the draft
    # needs an attribution sentence, so the frame must be known before the text.
    brand = (row.get("brand") or "").strip() or None
    # ★ E2: the scene comes from the hook FACT. `hook` is detect_hook's chosen
    # fact text, so the scene and the lead are driven by the SAME fact — that is
    # the point, not a coincidence. row["category"] is the fallback only.
    _scene_text, scene_source, _scene_why = BD.scene_for(row, _dj, hook)
    scene = scene_source
    tentpole = bool(occasion_for(cand["image_name"], datetime.now().date())[0])
    composition = pick_composition(fmt, hook_type, brand, scene, tentpole=tentpole)
    shows_value = COMP.card_shows_value(composition)

    if draft_fn is None:
        # SKELETONS ARE RETIRED (ruled). The writer is the only drafter; a
        # fallback would fire precisely when the material is weakest.
        dpath = HERE / "data" / "dossiers" / ("%s.json" % cand["image_name"])
        try:
            dj = json.loads(dpath.read_text())
            # all three go through the sensitivity rail; none is inlined again
            hook_facts = DOS.hook_facts(dj)
            lineage = DOS.lineage_facts(dj)
            support = DOS.support_facts(dj)
        except Exception:
            hook_facts = []; lineage = []; support = []
        occ, moment_ctx = occasion_for(cand["image_name"], datetime.now().date())
        moment = moment_ctx
        draft_fn = WR.make_draft_fn(
            hook_facts=hook_facts, release=SEL.load_release_dates().get(cand["image_name"]),
            moment=moment_ctx, occasion=occ, price_permitted=price_ok, lineage=lineage,
            support_facts=support,
            display_name=display, env=X.load_env(Path(X.DEFAULT_ENV)))
    text, gate_failed, attempts = draft_with_gate8(
        cand, row, fmt, hook_type, display, price_ok,
        draft_fn=draft_fn, max_retries=max_retries, moment=moment,
        composition=composition)
    if text is None:
        # Abandoned. The candidate does NOT consume the daily proposal budget —
        # the caller advances through the existing POOL_FACTOR x pool. Skeletons
        # stay retired: a fallback would fire precisely when the material is
        # weakest, which is the worst possible coupling.
        run_log(event="writer_abandoned", image_name=cand["image_name"],
                failed_rails=gate_failed, attempts=attempts)
        return None

    # (b) LEAD SPECIFICITY — the swap test.
    ok_lead, lead_why = editorial.lead_is_specific(text, row)
    if not ok_lead:
        run_log(event="skipped_generic_lead", image_name=cand["image_name"],
                format=fmt, reason=lead_why)
        return None

    # Only now is it worth rendering and generating.
    stem = "%s_%s" % (cand["image_name"][:40], datetime.now().strftime("%Y%m%d"))
    card = OUT / f"{stem}_card.png"
    CR.render_card(cand["image_name"], cand["rarity"], card)
    # composition is already chosen above — it decides whether the text needs
    # the attribution sentence, so it MUST precede drafting.
    visual, insp = card, "N/A (card only)"
    if not card_only:
        env = X.load_env(Path(X.DEFAULT_ENV))
        bd = None
        if composition in COMP.NEEDS_BACKDROP:
            bd = OUT / f"{stem}_bd.png"
            BD.generate(BD.build_prompt(row, _dj, hook), "3:4", bd, env)
            BD.record_verdict(str(bd), "UNINSPECTED_AUTOMATED",
                              "unattended launchd run — no Claude in the loop; Ashton is "
                              "the first human eye on this image")
            insp = "NOT pre-inspected (automated run)"
        else:
            # no generated imagery at all — nothing to inspect, and no spend
            insp = "N/A (no generated imagery)"
        visual = OUT / f"{stem}_45.png"
        COMP.render(composition, card, bd, visual, ratio="4:5")

    wl = X.weighted_len(text)
    tf = OUT / f"{stem}.txt"; tf.write_text(text, encoding="utf-8")
    editorial.record_format(fmt)
    run_log(event="draft_built", image_name=cand["image_name"], hook_type=hook_type,
            brand=brand, composition=composition, scene=scene,
            scene_why=(_scene_why or "")[:160],
            format=fmt, weighted=wl, tier=cand.get("rarity"))
    return {"text_file": tf, "image": visual, "cand": cand, "insp": insp,
            "price_ok": price_ok, "price_why": price_why, "weighted": wl,
            "hook_type": hook_type, "hook": hook, "format": fmt, "lead": lead_why,
            "brand": brand, "composition": composition, "scene": scene,
            # RAILS CONTEXT — persisted on the proposal so rails.check_draft() can
            # re-run at APPROVE time (F1.5). The ledger row previously carried none
            # of this, so the approve path could not re-derive price_verified and
            # ran no rails at all. style_code + estimated_resale are the only
            # inputs rails.price_claim_allowed() needs; freshness is recomputed
            # from local PK history against the clock, never cached here.
            "rails_ctx": {"style_code": sc,
                          "estimated_resale": row.get("estimated_resale"),
                          "image_name": cand["image_name"],
                          # ★ rarity joined image_name 2026-09-16: identity in
                          # this catalog is the PAIR. The same image is GRAIL,
                          # Legendary and Rare at once, and only one of those is
                          # reachable — an image-only check answers the wrong
                          # question.
                          "rarity": cand.get("rarity")}}


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
    # ── obtainability cache, rebuilt before anything is selected ─────────────
    # R5: if this ever stops running, set posts do not silently stop — rails
    # fails every card closed and the reason is PRINTED here, not merely absent.
    try:
        _sr = refresh_set_routes()
        print("  obtainability: %d reachable pairs, %d set routes."
              % (len(_sr["reachable_pairs"]), len(_sr["routes"])))
    except Exception as ex:
        run_log(event="set_routes_refresh_failed", error=type(ex).__name__)
        print("  ⚠️  OBTAINABILITY CACHE NOT REFRESHED (%s)." % type(ex).__name__)
    _routes, _why = rails.load_set_routes()
    if _routes is None:
        print("  ⚠️  RAILS CANNOT VOUCH FOR OBTAINABILITY: %s" % _why)
        print("      Every candidate will fail the OBTAINABLE rail until this is fixed.")
        run_log(event="obtainability_unavailable", reason=_why)

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
                               rails_ctx=built["rails_ctx"],
                               format=built["format"], hook_type=built["hook_type"],
                               composition=built.get("composition"),
                               tier=(built.get("cand") or {}).get("rarity"))
        pid = TB.cmd_propose(argv, e)
        # EXACT linking row. draft_built alone could not be joined to a post:
        # it carries no proposal_id, and matching on (image_name, nearest ts)
        # is ambiguous when one candidate is drafted repeatedly.
        run_log(event="draft_proposed", proposal_id=pid,
                image_name=cand["image_name"], format=built["format"],
                hook_type=built["hook_type"], weighted=built["weighted"],
                brand=built.get("brand"), composition=built.get("composition"),
                scene=built.get("scene"), tier=cand.get("rarity"))
        n += 1
    run_log(event="run_end", job=a.source, proposed=n)
    # Gate (d): zero is a valid outcome, and says so rather than looking broken.
    print("  proposed %d draft(s)." % n if n else
          "  proposed 0 drafts — no candidate cleared the editorial bar today. "
          "That is a valid outcome, not a failure.")


if __name__ == "__main__":
    main()
