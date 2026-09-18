#!/usr/bin/env python3.12
"""
format_report.py — weekly FORMAT performance. Shape only, never subject.

v1.3 ruling (2026-09-09): the agent may measure and report which FORMATS
perform and adjust format rotation accordingly. It may NOT select SUBJECTS by
heat, trend velocity or engagement potential. This report is the measuring half
of that ruling, and the restriction is STRUCTURAL rather than conventional —
GROUP_DIMENSIONS is a positive filter, the same discipline as
editorial.ALLOWED_FEEDBACK_CODES. A dimension enters the aggregation key only
by being in that frozenset. Adding "image_name", "hook_type", "brand" or any
shoe identifier here would convert this into topic-selection-by-engagement,
which is the objective v1.3 rejected.

hook_type is RECORDED but NOT grouped (ruling C2): format is shape, hook_type
leans subject.

LEDGER COMPLETENESS (ruling R3): posts.jsonl covers 5 of the 22 posts on
@appCYPHERR — the other 17 were hand-posted outside the agent. "Our posts"
here means AGENT-POSTED content, scoped explicitly via in_post_ledger, never
silently "the ones we logged".
"""
from __future__ import annotations
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
METRICS = HERE / "ledger" / "metrics.jsonl"
POSTS = HERE / "ledger" / "posts.jsonl"
RUNS = HERE / "ledger" / "runs.jsonl"
PROPOSALS = HERE / "ledger" / "proposals.jsonl"
LABELS = HERE / "data" / "post_format_labels.json"

# ── THE POSITIVE FILTER ──────────────────────────────────────────────────────
# Shape, not subject. Do not widen without a ruling.
GROUP_DIMENSIONS = frozenset({"format"})

# Below this many posts in a format, the report REFUSES to rank. With 3:1
# across four posts, "story_spotlight outperforms price_journey" would be noise
# wearing a number. Ranking is a claim about relative performance; n=4 cannot
# support one.
MIN_N_FOR_RANKING = 5


# ══ PIPELINE SIGNALS (E6, 2026-09-16) ════════════════════════════════════════
#
# ★★ THESE NEVER READ metrics.jsonl, AND THAT IS THE WHOLE DESIGN.
#
# They describe what the agent DID — which tiers it drew, which frames it used,
# how often the brief fell back to its fallback fact, what Ashton rejected and
# why. None of it is joined to engagement. Reporting "GRAIL posts get more
# impressions" would be subject-selection-by-performance wearing a different
# column name, which is precisely what GROUP_DIMENSIONS exists to prevent, and
# a positive filter on the engagement key would not stop it because the join
# would happen in a different function.
#
# So the separation is structural rather than conventional: pipeline_signals()
# and everything it calls read the RUN and PROPOSAL ledgers only. The suite
# asserts that no signal function references METRICS.
#
# EVERY SECTION CARRIES ITS OWN n AND ITS OWN FLOOR. Below the floor it says
# "insufficient data" and the number it would need. A distribution over 3
# observations is not a distribution; printing its percentages would be the
# report inventing a finding, which is the failure R4 names.
MIN_N = {
    "tier": 10,          # a share claim needs enough draws to have a shape
    "composition": 10,
    "divergence": 10,    # a rate over <10 briefs is anecdote
    "reject": 5,         # matches MIN_N_FOR_RANKING — a judgement about taste
}


def _read(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def load_labels() -> dict:
    try:
        return json.loads(LABELS.read_text())
    except Exception:
        return {}


def format_of(tweet_id: str, posted_rows: list[dict], labels: dict) -> tuple[str | None, str, str]:
    """(format, method, confidence). Denormalised row first, hand label second."""
    for r in posted_rows:
        if r.get("tweet_id") == tweet_id and r.get("format"):
            return r["format"], "denormalised", "exact"
    lab = labels.get(tweet_id)
    if lab:
        return lab.get("format"), lab.get("method", "hand"), lab.get("confidence", "unknown")
    return None, "unresolved", "none"


def aggregate(days: int | None = 7) -> dict:
    metrics = _read(METRICS)
    posted = [r for r in _read(POSTS) if r.get("event") == "posted"]
    labels = load_labels()

    # R3: agent-posted only, stated explicitly.
    rows = [m for m in metrics if m.get("in_post_ledger")]
    excluded = [m for m in metrics if not m.get("in_post_ledger")]

    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        rows = [m for m in rows
                if datetime.fromisoformat(m["created_at"].replace("Z", "+00:00")) >= cutoff]

    buckets: dict[tuple, list[dict]] = defaultdict(list)
    announcements, unresolved = [], []
    for m in rows:
        if m.get("kind") == "announcement":       # own category (ruling C3)
            announcements.append(m); continue
        if m.get("kind") != "content":
            continue
        fmt, method, conf = format_of(m["tweet_id"], posted, labels)
        if not fmt:
            unresolved.append(m); continue
        m = {**m, "_format": fmt, "_method": method, "_confidence": conf}
        key = tuple(sorted((d, m["_format"]) for d in GROUP_DIMENSIONS))
        buckets[key].append(m)
    return {"buckets": buckets, "announcements": announcements,
            "unresolved": unresolved, "excluded_non_agent": excluded,
            "window_days": days}


def _stat(rows: list[dict], field: str) -> tuple[float, int, int]:
    vals = [r[field] for r in rows if r.get(field) is not None]
    if not vals:
        return 0.0, 0, 0
    return sum(vals) / len(vals), min(vals), max(vals)


def render(agg: dict) -> str:
    L = []
    w = agg["window_days"]
    L.append("CYPHERMARKETER — FORMAT PERFORMANCE (%s)" % (
        "last %d days" % w if w else "all time"))
    L.append("=" * 62)
    L.append("Grouped by: %s  (structural — subject dimensions cannot enter)"
             % ", ".join(sorted(GROUP_DIMENSIONS)))
    L.append("")

    buckets = agg["buckets"]
    if not buckets:
        L.append("  No agent-posted content in this window. That is a valid outcome.")
    for key, rows in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        fmt = dict(key)["format"]
        n = len(rows)
        imp, ilo, ihi = _stat(rows, "impressions")
        lik, _, _ = _stat(rows, "likes")
        eng, _, _ = _stat(rows, "engagements")
        L.append("  %-18s n=%d" % (fmt, n))
        L.append("      impressions  mean %5.1f   range %d-%d" % (imp, ilo, ihi))
        L.append("      likes        mean %5.1f" % lik)
        L.append("      engagements  mean %5.1f" % eng)
        methods = {r["_method"] for r in rows}
        L.append("      attribution  %s" % ", ".join(sorted(methods)))
        L.append("")

    # ── the n-floor: state n, refuse to rank below it ────────────────────────
    L.append("-" * 62)
    ranked = [(dict(k)["format"], v) for k, v in buckets.items()]
    under = [f for f, v in ranked if len(v) < MIN_N_FOR_RANKING]
    if under:
        L.append("NO RANKING. %s below the n=%d floor (%s)." % (
            "Formats" if len(under) > 1 else "Format", MIN_N_FOR_RANKING,
            ", ".join("%s n=%d" % (f, len(v)) for f, v in ranked if f in under)))
        L.append("A relative-performance claim needs more posts than this. The")
        L.append("means above are descriptive only — do NOT read them as a ranking.")
    else:
        order = sorted(ranked, key=lambda kv: -_stat(kv[1], "impressions")[0])
        L.append("RANKING by mean impressions (all formats at or above n=%d):"
                 % MIN_N_FOR_RANKING)
        if not order:
            L.append("  none — no format has reached n=%d. Nothing is ranked, and "
                     "that is the finding." % MIN_N_FOR_RANKING)
        for f, v in order:
            L.append("  %-18s n=%d  mean impressions %5.1f"
                     % (f, len(v), _stat(v, "impressions")[0]))

    if agg["announcements"]:
        a = agg["announcements"]
        imp, lo, hi = _stat(a, "impressions")
        L.append("")
        L.append("ANNOUNCEMENTS (own category — not a format, never in format stats)")
        L.append("  n=%d  impressions mean %5.1f  range %d-%d" % (len(a), imp, lo, hi))

    if agg["unresolved"]:
        L.append("")
        L.append("UNRESOLVED FORMAT: %d post(s) — not counted in any bucket."
                 % len(agg["unresolved"]))
    if agg["excluded_non_agent"]:
        L.append("")
        L.append("SCOPE: %d post(s) on the account are NOT agent-posted and are"
                 % len(agg["excluded_non_agent"]))
        L.append("excluded (ruling R3). posts.jsonl is not the whole timeline.")
    return "\n".join(L)


# ── the signals themselves ───────────────────────────────────────────────────
def _window(rows: list[dict], days: int | None) -> list[dict]:
    if not days:
        return rows
    cut = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for r in rows:
        try:
            if datetime.fromisoformat(r["ts"]) >= cut:
                out.append(r)
        except Exception:
            pass
    return out


def _share(counts: dict) -> list[tuple[str, int, float]]:
    tot = sum(counts.values()) or 1
    return sorted(((k, v, v / tot) for k, v in counts.items()), key=lambda x: -x[1])


def _floor(name: str, n: int) -> str | None:
    """The refusal line, or None when there is enough to speak."""
    need = MIN_N[name]
    if n >= need:
        return None
    return ("insufficient data — n=%d, need %d before this says anything"
            % (n, need))


def pipeline_signals(days: int | None = 7) -> dict:
    """What the agent DID. Never what it earned — see the module header."""
    runs = _window(_read(RUNS), days)
    props = _window(_read(PROPOSALS), days)

    drafts = [r for r in runs if r.get("event") == "draft_built"]
    selected = [r for r in runs if r.get("event") == "candidates_selected"]
    div = [r for r in runs if r.get("event") == "brief_divergence"]
    rejects = [r for r in props if r.get("event") == "rejected"]

    cand_tiers: dict[str, int] = defaultdict(int)
    for r in selected:
        for k, v in (r.get("tiers") or {}).items():
            cand_tiers[k] += v
    prop_tiers = defaultdict(int)
    for r in drafts:
        if r.get("tier"):
            prop_tiers[r["tier"]] += 1
    comps = defaultdict(int)
    for r in drafts:
        if r.get("composition"):
            comps[r["composition"]] += 1
    codes = defaultdict(int)
    for r in rejects:
        codes[r.get("reason_code") or "(no code given)"] += 1

    # ★ ONLY drafts that actually went through the brief. Every draft before
    # 2026-09-16 predates E5 and carries no brief_source, so counting them would
    # report "0% fallback over n=36" — which reads as a mechanism working
    # perfectly when in fact it did not exist. A denominator that includes rows
    # the measurement could not have touched is how a report invents a finding.
    briefed = [r for r in drafts if r.get("brief_source")]
    n_div = len(briefed)
    pre_e5 = len(drafts) - n_div
    fallback = sum(1 for d in div if d.get("fallback_fired"))
    zero_overlap = sum(1 for d in div if not d.get("fallback_fired")
                       and d.get("shared_tokens") == 0)
    return {
        "days": days,
        "candidate_tiers": dict(cand_tiers), "n_candidates": sum(cand_tiers.values()),
        "proposal_tiers": dict(prop_tiers), "n_proposals": sum(prop_tiers.values()),
        "compositions": dict(comps), "n_compositions": sum(comps.values()),
        "n_briefs": n_div, "pre_e5_drafts": pre_e5,
        "fallback": fallback, "zero_overlap": zero_overlap,
        "reject_codes": dict(codes), "n_rejects": len(rejects),
        "n_runs": len([r for r in runs if r.get("event") == "run_start"]),
    }


def render_signals(sig: dict) -> list[str]:
    L: list[str] = []

    def section(title, name, n, body_fn):
        L.append("")
        L.append("%s  (n=%d)" % (title, n))
        msg = _floor(name, n)
        if msg:
            L.append("  " + msg)
        else:
            L.extend(body_fn())

    def tiers_body():
        out = []
        import daily_digest as DD
        for k, c, sh in _share(sig["proposal_tiers"]):
            grp = DD.TIER_GROUP.get(k, "body")
            tgt = DD.GROUP_TARGET_SHARE.get(grp, 0)
            out.append("  %-11s %3d  %5.1f%%   (group %s, target %.0f%%)"
                       % (k, c, 100 * sh, grp, 100 * tgt))
        return out

    def comp_body():
        return ["  %-14s %3d  %5.1f%%" % (k, c, 100 * sh)
                for k, c, sh in _share(sig["compositions"])]

    def div_body():
        fb = sig["fallback"] / sig["n_briefs"]
        zo = sig["zero_overlap"] / sig["n_briefs"]
        out = ["  fallback fired      %3d  %5.1f%%   (writer named no usable fact)"
               % (sig["fallback"], 100 * fb),
               "  zero token overlap  %3d  %5.1f%%   (lead shares nothing with its claimed fact)"
               % (sig["zero_overlap"], 100 * zo)]
        if fb > 0.5:
            out.append("  ⚠️  the fallback is carrying most briefs — the fact_id contract")
            out.append("      is not landing, and tuning around it would hide that.")
        return out

    def reject_body():
        return ["  %-22s %3d" % (k, c) for k, c, _ in _share(sig["reject_codes"])]

    ns = section_ns(sig)
    section("TIER DISTRIBUTION of drafts (E3 weighting, measured)", "tier",
            ns["tier"], tiers_body)
    section("COMPOSITION DISTRIBUTION", "composition", ns["composition"], comp_body)
    section("BRIEF DIVERGENCE (E5)", "divergence", ns["divergence"], div_body)
    if sig["pre_e5_drafts"]:
        L.append("  (%d earlier draft(s) excluded — they predate the fact_id "
                 "contract and could not have diverged)" % sig["pre_e5_drafts"])
    section("REJECT REASONS", "reject", ns["reject"], reject_body)
    return L


# ★★ ONE MAPPING OF SECTION -> n, READ TWICE.
# render_signals() uses it to draw each section; nothing_to_report() uses it to
# decide whether ANY section can speak. Two copies of "which n belongs to which
# floor" would drift, and the symptom is exactly the bug this replaced: a page
# of refusals printed by a function whose docstring promised one line.
def section_ns(sig: dict) -> dict[str, int]:
    return {"tier": sig["n_proposals"],
            "composition": sig["n_compositions"],
            "divergence": sig["n_briefs"],
            "reject": sig["n_rejects"]}


def nothing_to_report(agg: dict, sig: dict) -> bool:
    """★ R4: a weekly report that always produces a page will eventually invent
    one. If nothing was posted, nothing was drafted, nothing was rejected and no
    signal clears its floor, the honest output is one line.

    ★★ FIXED 2026-09-17. The clause "and no signal clears its floor" was in this
    docstring from the day it was written and was NEVER EVALUATED. The test was
    `if sig["n_proposals"] or sig["n_rejects"] or sig["n_briefs"]: return False`
    — ANY activity at all defeated the one-liner, floors never consulted. It
    went unseen because the window happened to be empty: with zero drafts both
    conditions agree. The first week carrying a single draft printed 24 lines,
    five of which were "insufficient data", under a heading promising there
    would be one.

    That is the inert-rail shape in the reporting layer, and it is the shape
    run_all.py was written about: a guarantee the data cannot violate because
    the code never checks it. A refusal is not a finding. A week in which every
    section refuses has produced no findings, and printing four headings over
    four refusals is the page R4 exists to prevent.
    """
    if agg["buckets"] or agg["announcements"] or agg["unresolved"]:
        return False
    # A section speaks only at or above its floor. If none does, there is
    # nothing to report however much machinery ran.
    return not any(n >= MIN_N[name] for name, n in section_ns(sig).items())


def weekly(days: int | None = 7) -> str:
    """The whole report: engagement by FORMAT, then what the pipeline did.

    The two halves never meet. See the pipeline-signals header for why.
    """
    agg = aggregate(days)
    sig = pipeline_signals(days)
    if nothing_to_report(agg, sig):
        ns = section_ns(sig)
        # ★ "no drafts" would be a lie the moment one draft exists, so the line
        # states what happened AND why it says nothing, rather than claiming
        # emptiness it cannot support.
        detail = ("no agent posts, no drafts, no rejections"
                  if not any(ns.values()) else
                  "no agent posts; nothing reached its floor (%s)"
                  % ", ".join("%s %d/%d" % (k, ns[k], MIN_N[k]) for k in sorted(ns)))
        return ("CYPHERMARKETER — WEEKLY (last %s)\n"
                "Nothing worth reporting this week: %s.\n%d run(s) executed." % (
                    ("%d days" % days) if days else "all time", detail, sig["n_runs"]))
    return "\n".join([render(agg)] + render_signals(sig))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Weekly report — format, then pipeline")
    ap.add_argument("--days", type=int, default=7, help="window; 0 = all time")
    a = ap.parse_args()
    print(weekly(a.days or None))
