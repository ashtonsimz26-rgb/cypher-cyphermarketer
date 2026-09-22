#!/usr/bin/env python3.12
"""retract_test_rows.py — append ONE retraction row for the resolver-test contamination.

tests/test_cypher_resolver.py wrote six rows into the REAL ledger/research.jsonl on
every suite run until 616965e (2026-09-22). Ashton's ruling (2026-09-22, R2): the
ledger is append-only, so the rows are not edited or deleted; one retraction row is
appended that names each of them by line number and content hash, with the rule,
the counts, the time range, the reason, the ruling — and the evidence, including
the one judgement call (the bare cypher:// rows). Readers honour it through
research/ledger_read.rows().

    python3.12 research/retract_test_rows.py            # dry run: prints the row, writes nothing
    python3.12 research/retract_test_rows.py --apply    # appends it (refuses if one exists)
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
from research import ledger_read as LR  # noqa: E402

# The six (event, uri, reason) pairs the test hard-coded. Nothing else matches.
FINGERPRINTS = [
    ("cypher_resolve_failed", "cypher://card/x/Rare", "RuntimeError: db down"),
    ("cypher_uri_malformed", "cypher://", "empty"),
    ("cypher_uri_malformed", "cypher://card/only_one_arg", "unknown kind 'card' or wrong arity (1)"),
    ("cypher_uri_malformed", "cypher://listing/x/y", "unknown kind 'listing' or wrong arity (2)"),
    ("cypher_uri_malformed", "cypher://serial/x/Rare/not_a_number", "serial is not a number"),
    ("cypher_uri_malformed", "cypher://card/a/b/c/d", "unknown kind 'card' or wrong arity (4)"),
]
EVENTS = sorted({f[0] for f in FINGERPRINTS})
BARE = "cypher://"                       # the one value production could also produce
TEST_ONLY_URIS = {f[1] for f in FINGERPRINTS} - {BARE}
BURST_S = 30                             # one suite run writes its six rows within seconds


def identify(lines: list[str]) -> tuple[list[tuple[int, dict]], dict]:
    """(rows to retract as (line_no, row), evidence). Raises on anything unproven."""
    parsed = []
    for i, raw in enumerate(lines, start=1):
        try:
            parsed.append((i, json.loads(raw)))
        except Exception:
            continue
    fp = set(FINGERPRINTS)
    cand = [(i, r) for i, r in parsed if r.get("event") in EVENTS]
    matched = [(i, r) for i, r in cand if (r["event"], r.get("uri"), r.get("reason")) in fp]
    stray = [(i, r) for i, r in cand if (i, r) not in matched]
    if stray:
        raise SystemExit("REFUSING: %d row(s) of these events do NOT match a test fingerprint "
                         "(first: line %d) — they may be real; investigate before retracting"
                         % (len(stray), stray[0][0]))
    ts = lambda r: datetime.fromisoformat(r["ts"])
    bursts: list[list[tuple[int, dict]]] = []
    for i, r in matched:
        if bursts and (ts(r) - ts(bursts[-1][-1][1])).total_seconds() < BURST_S:
            bursts[-1].append((i, r))
        else:
            bursts.append([(i, r)])
    unproven = []
    for b in bursts:
        uris = {r.get("uri") for _, r in b}
        for i, r in b:
            if r.get("uri") == BARE and not TEST_ONLY_URIS <= uris:
                unproven.append(i)
    if unproven:
        raise SystemExit("REFUSING: bare cypher:// row(s) at line(s) %s are NOT inside a burst "
                         "with all five test-only URIs — the only evidence they are test rows "
                         "is missing for them" % unproven)
    by_event: dict[str, int] = {}
    for _, r in matched:
        by_event[r["event"]] = by_event.get(r["event"], 0) + 1
    bare_n = sum(1 for _, r in matched if r.get("uri") == BARE)
    return matched, {"bursts": len(bursts), "by_event": by_event, "bare": bare_n}


def build(lines: list[str]) -> dict:
    matched, ev = identify(lines)
    return {
        "event": LR.RETRACTION,
        "ts": datetime.now(timezone.utc).isoformat(),
        "ledger": "ledger/research.jsonl",
        "reason": ("test contamination: tests/test_cypher_resolver.py appended these rows to the "
                   "REAL ledger on every suite run until commit 616965e (2026-09-22). They record "
                   "no real event — five malformed URIs and one simulated 'db down' that the test "
                   "feeds research/verify.resolve_cypher on purpose."),
        "ruling": ("Ashton, 2026-09-22 (R2): the ledger is append-only — append one retraction row "
                   "naming every contaminated row by line number and content hash; no existing row "
                   "changes; readers skip retracted rows via research/ledger_read.rows()."),
        "rule": {"events": EVENTS,
                 "fingerprints": [list(f) for f in FINGERPRINTS],
                 "match": "event in events AND [event, uri, reason] in fingerprints",
                 "line_hash": "sha256 of the line's exact UTF-8 text without the trailing newline"},
        "count": len(matched),
        "by_event": ev["by_event"],
        "first_ts": matched[0][1]["ts"], "last_ts": matched[-1][1]["ts"],
        "bursts": ev["bursts"],
        "evidence": {
            "test_only_values": ("Five of the six URIs (%s) and the reason 'RuntimeError: db down' "
                                 "appeared nowhere in the repository's code or data except "
                                 "tests/test_cypher_resolver.py (grep, 2026-09-22, before this "
                                 "tool — which names them — was written)."
                                 % ", ".join(sorted(TEST_ONLY_URIS))),
            "no_genuine_rows": ("Every row of events %s matches a fingerprint: no row of either "
                                "event exists outside this set." % EVENTS),
            "bare_scheme_rows": (
                "JUDGEMENT CALL, recorded as such: %d rows carry uri 'cypher://' with reason 'empty'. "
                "That value COULD come from production — it is research/verify.CYPHER_SCHEME, and a "
                "real empty cypher reference would ledger exactly this row. The ONLY evidence these "
                "%d are test rows is that every one of them sits inside a burst (rows < %d s apart) "
                "that also contains all five test-only URIs above. They are retracted on that basis. "
                "It was checked row by row, not assumed; a bare row outside such a burst would have "
                "made this tool refuse." % (ev["bare"], ev["bare"], BURST_S)),
            "readers_at_retraction": ("Nothing read ledger/research.jsonl when this was written "
                                      "(verify.py and goat_import.py only append to it), so the rows "
                                      "affected the audit trail but never the agent's behaviour."),
        },
        "rows": [{"line": i, "sha256": LR.line_hash(lines[i - 1])} for i, _ in matched],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="append the row (default: dry run)")
    a = ap.parse_args()
    lines = LR.LEDGER.read_text(encoding="utf-8").splitlines()
    if any('"event": "%s"' % LR.RETRACTION in l for l in lines):
        sys.exit("REFUSING: a retraction row already exists — this is a one-off")
    row = build(lines)
    summary = {k: v for k, v in row.items() if k != "rows"}
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    print("rows listed: %d (lines %d..%d)" % (len(row["rows"]), row["rows"][0]["line"], row["rows"][-1]["line"]))
    if not a.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
        return
    with LR.LEDGER.open("a", encoding="utf-8") as fh:        # append-only, like verify.ledger
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    got = LR.retracted_lines()
    assert len(got) == row["count"], (len(got), row["count"])
    print("\nAPPENDED as line %d. The reader verifies all %d hashes." % (len(lines) + 1, len(got)))


if __name__ == "__main__":
    main()
