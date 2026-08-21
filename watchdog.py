#!/usr/bin/env python3.12
"""
watchdog.py — CPA-pattern health check. Silence must never be ambiguous.

Checks: launchd jobs loaded + last exit status, ledger freshness, budget state.
Alerts Ashton's Telegram when the agent has gone dark or a job is failing, so a
missing digest is a message rather than nothing at all.
"""
from __future__ import annotations
import json, subprocess, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import budget  # noqa: E402

JOBS = ["ai.cyphermarketer.digest", "ai.cyphermarketer.poller",
        "ai.cyphermarketer.drops", "ai.cyphermarketer.health"]  # renamed: the old label
        # wedged in launchd's per-user DB after registering a malformed plist
        # (exit 78 EX_CONFIG, zero output, survived bootout+delete+re-bootstrap).
        # Same script under any other label runs fine — proven with a test job.
RUNS = HERE / "ledger" / "runs.jsonl"
SELF_JOB = "ai.cyphermarketer.health"
STREAKS = HERE / "state" / "health_streaks.json"
PERSISTENT_AFTER = 3          # consecutive same-job failures before escalation
STDERR_TAIL_LINES = 4         # failure detail carried into the alert
DIGEST_MAX_AGE_H = 26          # digest is daily; 26h means one was genuinely missed


def launchd_state() -> dict:
    """`launchctl list` is bounded and fault-tolerant on purpose.

    When this ran UNDER launchd it exited 78 with ZERO output — the first print
    happens after this call, so a hang/failure here killed the watchdog before
    it could say anything. A health checker that dies silently is worse than no
    health checker: it turns a loud failure into an ambiguous one. So the call
    is timeout-bounded and any failure degrades to a reported UNKNOWN rather
    than taking the process down.
    """
    out = {}
    try:
        p = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=30)
    except Exception as e:
        return {j: {"loaded": None, "error": type(e).__name__} for j in JOBS}
    table = {}
    for line in p.stdout.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3:
            table[parts[2]] = (parts[0], parts[1])
    for j in JOBS:
        if j in table:
            pid, ex = table[j]
            out[j] = {"loaded": True, "pid": pid, "last_exit": ex}
        else:
            out[j] = {"loaded": False}
    return out


def last_run(job: str) -> datetime | None:
    if not RUNS.exists():
        return None
    latest = None
    for line in RUNS.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            if r.get("job") == job and r.get("event") in ("run_start", "run_end"):
                t = datetime.fromisoformat(r["ts"])
                latest = t if not latest or t > latest else latest
        except Exception:
            continue
    return latest


def _failure_detail(job: str | None) -> str:
    """The failing line itself. An alert that only says last_exit=1 is a
    doorbell, not a diagnosis — it repeated ten times overnight without ever
    naming the NameError that caused it."""
    if not job:
        return ""
    f = HERE / "logs" / ("%s.err.log" % job)
    try:
        tail = [l.rstrip() for l in f.read_text(encoding="utf-8", errors="ignore").splitlines() if l.strip()]
    except Exception:
        return ""
    if not tail:
        return "(stderr empty — check stdout)"
    return " | ".join(tail[-STDERR_TAIL_LINES:])[:400]


def _bump_streaks(alerts) -> dict:
    """Consecutive-failure counts per job, so severity can escalate."""
    try:
        prev = json.loads(STREAKS.read_text())
    except Exception:
        prev = {}
    failing = {(j or "_global") for _, j in alerts}
    cur = {k: (prev.get(k, 0) + 1) for k in failing}
    STREAKS.parent.mkdir(parents=True, exist_ok=True)
    STREAKS.write_text(json.dumps(cur, indent=2))
    return cur


def _ledger_alert(body: list) -> None:
    try:
        RUNS.parent.mkdir(parents=True, exist_ok=True)
        with RUNS.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                                 "job": "health", "event": "alert_sent",
                                 "detail": " ; ".join(body)[:600]}) + "\n")
    except Exception:
        pass


def main():
    print("  watchdog start", flush=True)
    alerts, lines = [], []
    st = launchd_state()
    for j, v in st.items():
        if v.get("loaded") is None:
            alerts.append(("could not read launchd state for %s (%s)" % (j, v.get("error")), j))
            lines.append("  ? %s state UNKNOWN" % j); continue
        if not v["loaded"]:
            alerts.append(("job NOT loaded: %s" % j, j)); lines.append("  ✗ %s not loaded" % j)
        else:
            bad = v["last_exit"] not in ("0", "-")
            # ★ SELF-REFERENCE FIX. This job returns 1 whenever it raises ANY
            # alert, so its own exit code can never be a health signal for
            # itself — it is an alarm output, not a symptom. Watching it created
            # a self-sustaining loop: one real failure (the digest NameError on
            # 2026-08-20) made this exit 1, and every hourly run thereafter
            # alerted on that 1 and exited 1 again, forever, long after the
            # original cause was fixed. Ten identical alerts, zero information.
            # For ourselves, LOADED is the only meaningful signal.
            if j == SELF_JOB:
                lines.append("  ✓ %s loaded (own exit code is an alarm output, "
                             "not a health signal — not alerted on)" % j)
            else:
                lines.append("  %s %s exit=%s" % ("✗" if bad else "✓", j, v["last_exit"]))
                if bad:
                    alerts.append(("job %s last_exit=%s" % (j, v["last_exit"]), j))
    lr = last_run("digest")
    if lr is None:
        lines.append("  · digest: no run recorded yet")
    else:
        age = (datetime.now(timezone.utc) - lr).total_seconds() / 3600
        lines.append("  %s digest last run %.1fh ago" % ("✗" if age > DIGEST_MAX_AGE_H else "✓", age))
        if age > DIGEST_MAX_AGE_H:
            alerts.append(("no digest run in %.1fh" % age, "ai.cyphermarketer.digest"))
    ok, why = budget.check(require_image=True)
    lines.append("  %s budget: %s" % ("·" if ok else "✗", why))
    if not ok and "CIRCUIT BREAKER" in why:
        alerts.append((why, None))

    print("\n".join(lines), flush=True)
    streaks = _bump_streaks(alerts)
    if alerts:
        body = []
        for text, job in alerts:
            n = streaks.get(job or "_global", 0)
            if n >= PERSISTENT_AFTER:
                body.append("🔴 PERSISTENT FAILURE (%d CONSECUTIVE): %s" % (n, text))
            else:
                body.append("• %s" % text)
            detail = _failure_detail(job)
            if detail:
                body.append("    ↳ %s" % detail)
        try:
            import telegram_bot as TB
            TB.send_text(TB.env(), "🚨 cyphermarketer watchdog\n" + "\n".join(body))
            print("  alert sent to Telegram")
        except Exception as e:
            print("  ALERT SEND FAILED: %s" % type(e).__name__)
        _ledger_alert(body)
    else:
        print("  all healthy — no alert sent")
    return 1 if alerts else 0


if __name__ == "__main__":
    raise SystemExit(main())
