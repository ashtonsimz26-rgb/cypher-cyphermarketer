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
        "ai.cyphermarketer.drops", "ai.cyphermarketer.watchdog"]
RUNS = HERE / "ledger" / "runs.jsonl"
DIGEST_MAX_AGE_H = 26          # digest is daily; 26h means one was genuinely missed


def launchd_state() -> dict:
    out = {}
    p = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
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


def main():
    alerts, lines = [], []
    st = launchd_state()
    for j, v in st.items():
        if not v["loaded"]:
            alerts.append("job NOT loaded: %s" % j); lines.append("  ✗ %s not loaded" % j)
        else:
            bad = v["last_exit"] not in ("0", "-")
            lines.append("  %s %s exit=%s" % ("✗" if bad else "✓", j, v["last_exit"]))
            if bad:
                alerts.append("job %s last_exit=%s" % (j, v["last_exit"]))
    lr = last_run("digest")
    if lr is None:
        lines.append("  · digest: no run recorded yet")
    else:
        age = (datetime.now(timezone.utc) - lr).total_seconds() / 3600
        lines.append("  %s digest last run %.1fh ago" % ("✗" if age > DIGEST_MAX_AGE_H else "✓", age))
        if age > DIGEST_MAX_AGE_H:
            alerts.append("no digest run in %.1fh" % age)
    ok, why = budget.check(require_image=True)
    lines.append("  %s budget: %s" % ("·" if ok else "✗", why))
    if not ok and "CIRCUIT BREAKER" in why:
        alerts.append(why)

    print("\n".join(lines))
    if alerts:
        try:
            import telegram_bot as TB
            TB.send_text(TB.env(), "🚨 cyphermarketer watchdog\n" + "\n".join("• " + a for a in alerts))
            print("  alert sent to Telegram")
        except Exception as e:
            print("  ALERT SEND FAILED: %s" % type(e).__name__)
    else:
        print("  all healthy — no alert sent")
    return 1 if alerts else 0


if __name__ == "__main__":
    raise SystemExit(main())
