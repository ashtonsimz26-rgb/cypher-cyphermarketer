#!/usr/bin/env python3.12
"""
dossier.py — deterministic fact extraction from GOAT snapshots (D1).

NO LLM. Every fact is EXTRACTED from a field already on disk, never invented and
never embellished. A fact whose text carries a claim absent from its source is a
defect, not a style choice. If the source sentence is dull, the fact is dull.

★ THE NAME-CONSISTENCY GATE — why it exists
    A misattributed fact passes the entire truth gate: every fact traces to a
    real source, the source is real, the gate is satisfied, and the post is
    still FALSE — because nothing verifies the source is about the SAME SHOE.
    Found in D1 GROUND: `nike_air_foamposite_one_wu_tang` carries a GOAT story
    that describes the 'Optic Yellow', never mentioning Wu-Tang. F4's truth gate
    structurally cannot catch that, so it closes here, fail-closed, before any
    fact is emitted.

    Signal 1 SILHOUETTE — the catalog silhouette must appear in GOAT's name or
      story as a word-bounded phrase. Same discipline as the RSS silhouette fix
      after Goadome -> Humara matched on a bare token.
    Signal 2 COLORWAY  — at least one DISTINCTIVE colorway/name token must
      appear in the story. Generic tokens corroborate nothing and are stripped.

    both      -> "confirmed"        facts emitted normally
    sil only  -> "silhouette_only"  ONLY designer / release_date / spec facts;
                 story-derived facts DROPPED, so no hook can come from prose we
                 cannot tie to this card
    no sil    -> "failed"           usable=false, ZERO story-derived facts

    The snapshot is never edited. It is a faithful record of what GOAT returned;
    the dossier is where judgment is applied (capture vs interpretation).

    ★★ LOCKED INVARIANT — SIGNAL PRECEDENCE. DO NOT "SIMPLIFY".
    Signal 3 (year) rescues ABSENCE of evidence only; it may NEVER override
    NEGATIVE evidence. It applies if and only if signal 2 is "unavailable" —
    never when signal 2 is "fail". nike_air_foamposite_one_wu_tang is the proof:
    its years agree (2016 == 2016), so any code path that let signal 3 outrank a
    failed signal 2 would silently recover the exact misattribution this gate
    was built to stop. If you are tempted to collapse the three-way signal 2
    into a boolean, this is why you must not.

    ⚠ WATCH ITEM (2026-09-10). Signal 3 has confirmed 11 of 11 and held back 0.
    It is carrying 11 dossiers on a signal that has never once said no, so it is
    not yet discriminating on this data. If a later rebuild still shows it at
    100% pass, it is decoration: give it teeth or remove it.

PRICE: `retail_price_cents` is the ONLY price field in a snapshot and is NEVER
read. Prose carries no currency at all (verified across 250 files, 0 hits).
Price claims belong to PK and rails.py alone.
"""
from __future__ import annotations
import html, json, re, sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SNAPS = HERE / "data" / "goat_snapshots"
OUT = HERE / "data" / "dossiers"
RELEASE_DATES = HERE / "data" / "release_dates.json"

# ── tags ─────────────────────────────────────────────────────────────────────
# POSITIVE FILTER, same discipline as editorial.ALLOWED_FEEDBACK_CODES and
# format_report.GROUP_DIMENSIONS. A tag becomes hookable only by membership.
# "spec" is deliberately ABSENT: a spec is not a story. Materials, silhouette
# geometry and construction can never open a post, no matter how well written.
HOOKABLE_TAGS = frozenset({
    "designer", "collab_origin", "cultural_moment", "release_drama", "price_reason",
})
ALL_TAGS = HOOKABLE_TAGS | {"release_date", "spec"}

# Tokens that corroborate nothing — present in half the catalog.
GENERIC_TOKENS = frozenset({
    "black", "white", "low", "high", "mid", "retro", "nike", "jordan", "og", "sp",
    "adidas", "air", "shoe", "sneaker", "the", "and", "grey", "gray", "university",
    "wmns", "gs", "qs", "prm", "premium", "se", "id", "v2", "one", "1", "2", "3",
})

MONEY = re.compile(r"[$£€]\s?\d|\bUSD\b|\bMSRP\b|\bdollars?\b|resell|resale|\bworth\b", re.I)


class _Strip(HTMLParser):
    def __init__(self):
        super().__init__(); self.out = []
    def handle_data(self, d): self.out.append(d)
    def text(self): return re.sub(r"\s+", " ", "".join(self.out)).strip()


def strip_html(h: str | None) -> str:
    p = _Strip(); p.feed(h or ""); return html.unescape(p.text())


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


def has_all_tokens(haystack: str, phrase: str) -> bool:
    """Every phrase token present as a whole word. Order NOT required.

    ★ Three passes taught this: PRESENCE is what matters, not contiguity and
    not order. The catalog and GOAT use different naming vocabularies —
    catalog "Jordan 1 High" vs GOAT "Air Jordan 1 Retro High OG" (interposed
    modifiers, which killed contiguity), and catalog "SB Dunk Low" vs GOAT
    "Nike Dunk Low Pro SB" (reordered, which killed ordered-subsequence).
    Neither is a mismatch; both are the same shoe named differently.

    This still rejects the case the strict form existed for: silhouette
    "Nike Air Humara" against an "Air Max Goadome" name fails because the
    token `humara` is ABSENT — in any order. Order never caught Goadome;
    presence did.
    """
    h, ph = set(norm(haystack).split()), norm(phrase).split()
    if not h or not ph:
        return False
    return all(t in h for t in ph)


def distinctive_tokens(*sources: str) -> list[str]:
    toks, seen = [], set()
    for s in sources:
        for t in norm(s).split():
            if t in GENERIC_TOKENS or len(t) < 3 or t in seen:
                continue
            seen.add(t); toks.append(t)
    return toks


# ── the gate ─────────────────────────────────────────────────────────────────
def name_consistency(cat: dict, snap: dict) -> dict:
    """Three signals, fail-closed. Auditable per shoe — every input recorded.

    Signal 2 is THREE-WAY, because "nothing to test" and "tested and found
    nothing" are different outcomes — the same distinction verify.py draws
    between unverified and contradicted. Collapsing them rejects shoes whose
    colorway is simply generic ("Black"); granting them a free pass is the
    opposite error. Signal 3 (year agreement) resolves the unavailable case:
    weak alone, but genuinely independent of silhouette, and a snapshot about a
    different shoe usually carries a different year.
    """
    story = strip_html(snap.get("story_html"))
    goat_name = snap.get("name") or ""
    silhouette = (cat.get("silhouette") or "").strip()

    sig1 = bool(silhouette) and (has_all_tokens(goat_name, silhouette)
                                 or has_all_tokens(story, silhouette))
    # ★ Signal 2 must be INDEPENDENT of signal 1, or it corroborates nothing.
    # First cut pulled tokens from colorway AND name — but `name` contains the
    # silhouette words, so "foamposite" alone satisfied signal 2 for
    # nike_air_foamposite_one_wu_tang and the gate returned "confirmed" on the
    # exact case it exists to catch (the story is about 'Optic Yellow'; the token
    # "tang" is absent). Silhouette tokens are now excluded, so signal 2 tests
    # only what signal 1 cannot.
    sil_tokens = set(norm(silhouette).split())
    tokens = [t for t in distinctive_tokens(cat.get("colorway") or "",
                                            cat.get("name") or "")
              if t not in sil_tokens]
    found = [t for t in tokens if has_phrase(story, t)]
    sig2 = "unavailable" if not tokens else ("pass" if found else "fail")

    cat_year, goat_year = cat.get("year"), snap.get("release_year")
    year_match = bool(cat_year) and bool(goat_year) and int(cat_year) == int(goat_year)
    sig3 = {"tested": {"catalog_year": cat_year, "goat_release_year": goat_year},
            "match": year_match, "applied": sig2 == "unavailable"}

    if not sig1:
        verdict, decided_by = "failed", "signal_1_silhouette"
    elif sig2 == "pass":
        verdict, decided_by = "confirmed", "signal_2_colorway"
    elif sig2 == "fail":
        verdict, decided_by = "silhouette_only", "signal_2_colorway"
    else:                                   # unavailable -> fall back to year
        verdict = "confirmed" if year_match else "silhouette_only"
        decided_by = "signal_3_year"
    return {"name_match": verdict,
            "decided_by": decided_by,
            "signal_1_silhouette": {"tested": silhouette, "found": sig1},
            "signal_2_colorway": {"tested": tokens, "found": found, "result": sig2},
            "signal_3_year": sig3}


# ── sentence-level extraction ────────────────────────────────────────────────
# Sentence-level, NOT story-level: most GOAT prose is 60-80% materials copy, so a
# whole-story blob would bury the one real fact under four sentences of spec.
SPEC_MARKERS = re.compile(
    r"\b(upper|midsole|outsole|sockliner|insole|tongue|heel|collar|eyelet|lace|"
    r"suede|leather|mesh|nubuck|canvas|rubber|foam|boost|cushion|shank|overlay|"
    r"panel|stitch|embroider|print|graphic|branding|constructed|features|"
    r"crafted|built|finish|textured|colorway|palette|hue|tonal)\b", re.I)

TAG_RULES = (
    ("collab_origin",   re.compile(r"\bcollaborat\w*|\bpartnership\b|\bteamed up\b|\bjoint\b|\bx\s+[A-Z]", re.I)),
    ("cultural_moment", re.compile(r"\bhomage\b|\binspired by\b|\bpays? tribute\b|\bcelebrat\w+|\bcommemorat\w+|"
                                   r"\bproceeds\b|\bcharit\w+|\bfoundation\b|\bhospital\b|\bhonor\w*\b|"
                                   r"\bculture\b|\bmovie\b|\bfilm\b|\bvideo\b|\balbum\b|\bmusic\b", re.I)),
    ("release_drama",   re.compile(r"\bbanned\b|\bcontrovers\w+|\brecall\w*|\bcancel\w+|\blimited\b|"
                                   r"\bexclusive\b|\bfriends and family\b|\bplayer exclusive\b|\bunreleased\b|"
                                   r"\bsold out\b|\briot\w*", re.I)),
    ("price_reason",    re.compile(r"\brare\b|\bscarc\w+|\bonly \d+ pairs?\b|\bnumbered\b|\bone[- ]of[- ]one\b", re.I)),
)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def tag_sentence(s: str) -> str:
    """First matching story tag wins; everything else is spec.

    FAIL-CLOSED on purpose. A sentence that matches no story pattern is either
    materials copy or generic filler, and both are non-hookable — so the safe
    default is the one tag that can never become a hook. Being wrong here costs
    a dull fact; the opposite default would let filler open a post.
    """
    for tag, pat in TAG_RULES:
        if pat.search(s):
            return tag
    return "spec"


def build(image_name: str, cat: dict, snap: dict, release_dates: dict) -> dict:
    gate = name_consistency(cat, snap)
    facts: list[dict] = []
    n = 0

    def add(tag, text, kind, ref, verified="self_evident"):
        nonlocal n
        text = re.sub(r"\s+", " ", text).strip()
        if not text or MONEY.search(text):      # no figure enters a fact, ever
            return
        if tag not in ALL_TAGS:
            return
        n += 1
        facts.append({"id": "f%d" % n, "tag": tag, "text": text,
                      "source": {"kind": kind, "ref": ref},
                      "verified": verified, "checked_at": None})

    # designer — 83.6% populated, 13 distinct values: a controlled vocabulary and
    # the highest-confidence target in the snapshot. Emitted at every gate level
    # except "failed", because it is a field, not prose.
    designer = (snap.get("designer") or "").strip()
    if designer and gate["name_match"] != "failed":
        add("designer", "%s designed the %s." % (designer, cat.get("name") or image_name),
            "goat_snapshot", "designer")

    # release_date — from cyphermarketer-owned release_dates.json (v1.2 ruling)
    rd = release_dates.get(image_name) or {}
    if rd.get("release_date") and gate["name_match"] != "failed":
        add("release_date", "Released %s." % rd["release_date"], "release_dates", image_name)

    # story-derived facts — DROPPED unless the gate confirms the story is about
    # this shoe. This is the whole point of the gate.
    if gate["name_match"] == "confirmed":
        for s in split_sentences(strip_html(snap.get("story_html"))):
            add(tag_sentence(s), s, "goat_snapshot", "story_html")

    hooks = [f["id"] for f in facts if f["tag"] in HOOKABLE_TAGS]
    return {"image_name": image_name,
            "built_at": datetime.now(timezone.utc).isoformat(),
            **gate,
            "facts": facts,
            "hook_candidates": hooks,
            "usable": bool(hooks)}


CATALOG_CACHE = HERE / "state" / "_catalog_cache.json"   # machine-local, gitignored


def load_catalog() -> dict:
    """Catalog rows for the name-consistency gate. Cached locally because
    state/ is gitignored; re-fetched read-only when the cache is absent, so the
    script is self-contained on a fresh checkout."""
    if CATALOG_CACHE.exists():
        return {r["image_name"]: r for r in json.loads(CATALOG_CACHE.read_text())}
    import subprocess
    q = HERE / "state" / "_dossier_cat.sql"
    q.parent.mkdir(parents=True, exist_ok=True)
    q.write_text("select distinct image_name, name, colorway, silhouette, brand, year "
                 "from public.catalog_cards order by image_name;", encoding="utf-8")
    r = subprocess.run(["supabase", "db", "query", "--linked", "-o", "json", "-f", str(q)],
                       capture_output=True, text=True, timeout=180,
                       cwd=str(Path.home() / "Documents/openclaw/CYPHER"))
    m = re.search(r"\[.*\]", r.stdout, re.S)
    if not m:
        sys.stderr.write("FATAL: catalog query failed: %s\n" % r.stderr[:200])
        raise SystemExit(2)
    rows = json.loads(m.group(0))
    CATALOG_CACHE.write_text(json.dumps(rows, indent=0))
    return {x["image_name"]: x for x in rows}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    catalog = load_catalog()
    try:
        rd = json.loads(RELEASE_DATES.read_text())
    except Exception:
        rd = {}
    built = 0
    for f in sorted(SNAPS.glob("*.json")):
        image_name = f.stem
        snap = json.loads(f.read_text())
        cat = catalog.get(image_name)
        if not cat:
            continue
        d = build(image_name, cat, snap, rd)
        (OUT / ("%s.json" % image_name)).write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
        built += 1
    print("built %d dossiers -> %s" % (built, OUT))


if __name__ == "__main__":
    main()
