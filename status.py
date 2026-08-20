#!/usr/bin/env python3.12
"""
status.py — READ-ONLY operational status for cyphermarketer.

Purpose (Q6 split): the Hermes profile owns VOICE and JUDGMENT; this repo owns
CREDENTIALS and EXECUTION. The profile needs to answer "what's today's status?"
from ground truth instead of guessing — so it gets READ access to the ledgers,
not sync, and not control.

STRICTLY READ-ONLY BY CONSTRUCTION:
  * opens ledger files in "r" only; never writes, appends, or truncates
  * never imports the posting path and never calls create_tweet / upload_media /
    telegram send / approve. Reading a ledger cannot post.
  * takes no arguments that could select an action — the only output is a report.
Granting the profile this skill does NOT let it post, approve, or mutate
anything. Ashton remains the only approver; execution stays in the scheduled
pipeline.
"""
from __future__ import annotations
import json, subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "ledger"
POST_CAP = 4
SPEND_LIMIT = 1.00


def _read(name: str) -> list[dict]:
    p = LEDGER / name
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():   # read mode only
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def _since(rows, hours, event=None):
    cut = datetime.now(timezone.utc) - timedelta(hours=hours)
    keep = []
    for r in rows:
        if event and r.get("event") != event:
            continue
        try:
            if datetime.fromisoformat(r["ts"]) >= cut:
                keep.append(r)
        except Exception:
            pass
    return keep


def collect() -> dict:
    posts, props, backs, runs = (_read("posts.jsonl"), _read("proposals.jsonl"),
                                 _read("backdrops.jsonl"), _read("runs.jsonl"))
    posted24 = _since(posts, 24, "posted")
    gen24 = _since(backs, 24, "generated")
    spend24 = round(sum(float(r.get("cost_usd") or 0) for r in gen24), 4)

    state = {}
    for r in props:
        pid = r.get("proposal_id")
        if not pid:
            continue
        if r.get("event") == "proposed":
            state[pid] = {"status": "pending", "text": r.get("text", "")}
        elif r.get("event") in ("approved", "rejected", "posted", "failed"):
            state.setdefault(pid, {})["status"] = r["event"]
            if r.get("url"):
                state[pid]["url"] = r["url"]

    decided = [v for v in state.values() if v.get("status") in ("posted", "rejected")]
    approved = [v for v in decided if v.get("status") == "posted"]
    verdicts = [r for r in backs if r.get("event") == "inspection"]
    discarded = [v for v in verdicts if v.get("verdict") == "DISCARD"]

    digest_runs = [r for r in runs if r.get("job") == "digest"]
    last_digest = digest_runs[-1] if digest_runs else None

    try:
        lc = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=20).stdout
    except Exception:
        lc = ""
    jobs = {}
    for line in lc.splitlines():
        p = line.split(None, 2)
        if len(p) == 3 and p[2].startswith("ai.cyphermarketer."):
            jobs[p[2]] = p[1]

    return {
        "posts_today": len(posted24), "post_cap": POST_CAP,
        "posts_remaining": max(0, POST_CAP - len(posted24)),
        "recent_posts": [{"url": r.get("url"), "ts": r.get("ts", "")[:16]} for r in posts
                         if r.get("event") == "posted"][-5:],
        "image_spend_24h": spend24, "spend_limit": SPEND_LIMIT,
        "circuit_breaker": "TRIPPED" if spend24 >= SPEND_LIMIT else "ok",
        "images_generated_24h": len(gen24),
        "pending_proposals": [{"id": k, "preview": (v.get("text") or "")[:70]}
                              for k, v in state.items() if v.get("status") == "pending"],
        "approval_rate": (round(len(approved) / len(decided), 2) if decided else None),
        "decisions_total": len(decided), "approved_total": len(approved),
        "discard_rate": (round(len(discarded) / len(verdicts), 2) if verdicts else None),
        "backdrops_inspected": len(verdicts), "backdrops_discarded": len(discarded),
        "last_digest": (last_digest or {}).get("ts", "never")[:16],
        "last_digest_event": (last_digest or {}).get("event", "none"),
        "jobs": jobs,
    }


def render(d: dict) -> str:
    L = []
    L.append("CYPHERMARKETER STATUS  (read-only)")
    L.append("  posts today      : %d/%d  (%d remaining)"
             % (d["posts_today"], d["post_cap"], d["posts_remaining"]))
    L.append("  image spend 24h  : $%.2f / $%.2f  [%s]  (%d images)"
             % (d["image_spend_24h"], d["spend_limit"], d["circuit_breaker"],
                d["images_generated_24h"]))
    L.append("  pending proposals: %d" % len(d["pending_proposals"]))
    for p in d["pending_proposals"]:
        L.append("      %s  %s…" % (p["id"], p["preview"]))
    ar = d["approval_rate"]
    L.append("  approval rate    : %s  (%d/%d decided)"
             % ("n/a" if ar is None else "%.0f%%" % (ar * 100),
                d["approved_total"], d["decisions_total"]))
    dr = d["discard_rate"]
    L.append("  backdrop discard : %s  (%d inspected, %d discarded)"
             % ("n/a" if dr is None else "%.0f%%" % (dr * 100),
                d["backdrops_inspected"], d["backdrops_discarded"]))
    L.append("  last digest run  : %s (%s)" % (d["last_digest"], d["last_digest_event"]))
    L.append("  scheduled jobs   :")
    for j, ex in sorted(d["jobs"].items()):
        L.append("      %-34s last_exit=%s" % (j, ex))
    L.append("  recent posts:")
    for p in d["recent_posts"]:
        L.append("      %s  %s" % (p["ts"], p["url"]))
    return "\n".join(L)


if __name__ == "__main__":
    import sys
    d = collect()
    if "--json" in sys.argv[1:]:
        print(json.dumps(d, indent=2))
    else:
        print(render(d))
