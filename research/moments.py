#!/usr/bin/env python3.12
"""
moments.py — loader for data/moments.json (D2).

On-this-day CULTURAL moments. Release dates live in data/release_dates.json and
are a different lane; this file is for events whose significance exceeds the
release itself.

★★ THE AGENT MAY NEVER ADD, EDIT, OR APPROVE AN ENTRY. EVER.
   approved_by is set by Ashton, by hand, after reading the sources. Any entry
   without approved_by == "ashton" is REJECTED and logged. There is no code path
   in this module that writes to moments.json, and there must never be one.

MOMENT_SENSITIVITY — a POSITIVE FILTER, not a skip.
   proposable() returns only entries whose sensitivity is in
   PROPOSABLE_SENSITIVITIES. An entry marked "tragedy_adjacent" is never
   returned to a caller that can propose; neither is one carrying a sensitivity
   value nobody anticipated. The field exists so a date can be OCCUPIED
   DEFENSIVELY — so a future session does not add it unflagged — not so a
   judgment call happens at draft time. Same discipline as
   format_report.GROUP_DIMENSIONS and editorial.ALLOWED_FEEDBACK_CODES: a value
   passes by MEMBERSHIP, never by failing to match a blocklist.

Working metadata (_confidence, _contest_note, _source_hint, _verify_terms,
_note) stays in the file for the review loop. Any key beginning with an
underscore is ignored by the loader.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
MOMENTS = HERE / "data" / "moments.json"
REACHABLE_CACHE = HERE / "state" / "_reachable_cache.json"

# ── the positive filters ─────────────────────────────────────────────────────
PROPOSABLE_SENSITIVITIES = frozenset({"none"})     # MOMENT_SENSITIVITY. Do not widen.
APPROVER = "ashton"                                # the only valid approver
VALID_KINDS = frozenset({"riot", "launch", "milestone", "culture", "brand_history"})

REQUIRED_FIELDS = ("id", "title", "year", "kind", "text", "post_text", "sources",
                   "linked_image_names", "sensitivity", "approved_by")

# ── post_text: the copy that ships ───────────────────────────────────────────
# `text` is the VERIFIED FACT RECORD — what verify.py's source check ran
# against. It is NEVER posted. `post_text` is the shipping copy and must be a
# strict factual SUBSET of its own `text`: no proper noun, date or number that
# `text` does not contain. That is what lets the copy be short enough to post
# WITHOUT re-opening verification — every fact in it was already checked.
POST_TEXT_MAX_WEIGHTED = 180


def _tokens(s: str) -> set[str]:
    """Proper nouns (capitalised, not sentence-initial) and every number."""
    words = re.findall(r"[A-Za-z][A-Za-z'\u2019\-]*|\d+", s)
    sent_start = {m.group(1) for m in re.finditer(r"(?:^|[.!?\u2014]\s+)([A-Za-z]+)", s)}
    out = set()
    for w in words:
        if w.isdigit():
            out.add(w)
        elif w[0].isupper() and w not in sent_start:
            # possessive SUFFIX only — rstrip("'s") strips CHARACTERS and turns
            # "Finals" into "Final", which produced a false rejection.
            for suf in ("'s", "\u2019s", "'", "\u2019"):
                if w.endswith(suf):
                    w = w[: -len(suf)]
                    break
            out.add(w)
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())


def untraceable_tokens(post_text: str, text: str) -> list[str]:
    """Tokens in post_text that its own `text` does not support."""
    src = _norm(text)
    out = []
    for t in _tokens(post_text or ""):
        n = _norm(t).strip()
        if not n:
            continue
        # a number may appear pluralised in the source ("12" vs "12s")
        tail = r"(?!\d)" if t.isdigit() else r"(?![a-z0-9])"
        if not re.search(rf"(?<![a-z0-9]){re.escape(n)}{tail}", src):
            out.append(t)
    return sorted(out)


def _public(entry: dict) -> dict:
    """Drop working metadata. Any underscore-prefixed key is not schema."""
    return {k: v for k, v in entry.items() if not k.startswith("_")}


def load_reachable() -> set[str]:
    try:
        return set(json.loads(REACHABLE_CACHE.read_text()))
    except Exception:
        return set()


def load(path: Path | None = None, reachable: set[str] | None = None
         ) -> tuple[dict[str, list[dict]], list[dict]]:
    """(entries_by_date, rejections). Never raises on a bad entry — it logs it.

    linked_image_names are validated against the R1/R2 REACHABLE SET, not the
    dossier set: a moment may legitimately link a card whose dossier is
    unusable, because the moment carries its own sourced text and the card is
    illustration, not the fact source. An entry whose links ALL drop still
    loads — the moment can stand without a card.
    """
    path = path or MOMENTS
    reachable = load_reachable() if reachable is None else reachable
    try:
        raw = json.loads(path.read_text())
    except Exception as e:
        return {}, [{"reason": "file_unreadable", "detail": type(e).__name__}]

    out: dict[str, list[dict]] = {}
    rejections: list[dict] = []
    for date, entries in (raw.get("moments") or {}).items():
        if date.startswith("_"):
            continue
        for raw_entry in entries:
            e = _public(raw_entry)
            eid = e.get("id", "<no id>")
            missing = [f for f in REQUIRED_FIELDS if f not in e]
            if missing:
                rejections.append({"id": eid, "date": date,
                                   "reason": "missing_fields", "detail": missing})
                continue
            if e.get("approved_by") != APPROVER:
                rejections.append({"id": eid, "date": date, "reason": "not_approved",
                                   "detail": repr(e.get("approved_by"))})
                continue
            pt = e.get("post_text")
            if not pt or not str(pt).strip():
                rejections.append({"id": eid, "date": date, "reason": "no_post_text"})
                continue
            sys.path.insert(0, str(HERE))
            from x_client import weighted_len              # noqa: PLC0415
            w = weighted_len(pt)
            if w > POST_TEXT_MAX_WEIGHTED:
                rejections.append({"id": eid, "date": date, "reason": "post_text_too_long",
                                   "detail": "%d > %d weighted" % (w, POST_TEXT_MAX_WEIGHTED)})
                continue
            drift = untraceable_tokens(pt, e.get("text") or "")
            if drift:
                rejections.append({"id": eid, "date": date, "reason": "post_text_not_a_subset",
                                   "detail": drift})
                continue
            if not e.get("sources"):
                # A moment with no source is not a moment.
                rejections.append({"id": eid, "date": date, "reason": "no_sources"})
                continue
            if e.get("kind") not in VALID_KINDS:
                rejections.append({"id": eid, "date": date, "reason": "bad_kind",
                                   "detail": repr(e.get("kind"))})
                continue
            links = list(e.get("linked_image_names") or [])
            kept = [n for n in links if n in reachable]
            dropped = [n for n in links if n not in reachable]
            if dropped:
                rejections.append({"id": eid, "date": date, "reason": "link_dropped",
                                   "detail": dropped, "entry_kept": True})
            e["linked_image_names"] = kept
            out.setdefault(date, []).append(e)
    return out, rejections


def proposable(date: str, path: Path | None = None,
               reachable: set[str] | None = None) -> list[dict]:
    """Entries a caller MAY propose on this date. MOMENT_SENSITIVITY here."""
    entries, _ = load(path, reachable)
    return [e for e in entries.get(date, [])
            if e.get("sensitivity") in PROPOSABLE_SENSITIVITIES]


def coverage(path: Path | None = None) -> dict:
    entries, rej = load(path)
    return {"days_covered": len(entries),
            "entries_loaded": sum(len(v) for v in entries.values()),
            "rejections": len(rej)}


if __name__ == "__main__":
    entries, rej = load()
    print("loaded %d entries across %d days" % (
        sum(len(v) for v in entries.values()), len(entries)))
    for r in rej:
        print("  REJECTED %-22s %s %s" % (r.get("id"), r["reason"], r.get("detail", "")))
