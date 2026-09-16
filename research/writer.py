#!/usr/bin/env python3.12
"""
writer.py — the lead writer (F4.4). grok-4.3 via XAI_API_KEY.

It writes ONE LINE. It never authors the attribution clause, never the link,
never the moment text. Those are the composer's, and that is deliberate: the
writer touches the part where judgment lives and none of the part where a rail
lives (see compose_text — "resale" alone is not an attribution marker, so the
most natural phrasing fails the rail; no prompt reliably beats that).

★★ INPUT IS A WHITELIST, STRUCTURAL NOT CONVENTIONAL.
   build_payload() constructs the model's input from PAYLOAD_FIELDS and asserts
   the result contains nothing else. A future edit cannot widen it by adding a
   key — the assertion fails first.

   Excluded absolutely: spec-tagged facts, retail_price_cents, raw story_html,
   the full dossier object, and any catalog column not explicitly passed.
   Rationale: passing the story back re-admits exactly the spec prose the
   sentence-level split exists to filter, and it would do so INVISIBLY, because
   the model would simply write better-sounding spec.

PROVIDER: mirrors backdrop.py — primary selected by key presence, 5xx falls
back, a 4xx NEVER does (a 4xx means OUR request is wrong). OpenAI text is
configured-but-dormant while OPENAI_API_KEY is absent (C1 parked).
"""
from __future__ import annotations
import json, re, sys, urllib.error, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import x_client as X                                    # noqa: E402

# EXACT path. .env and state.db live in this directory — never glob it.
SOUL = Path.home() / ".hermes/profiles/cyphermarketer/SOUL.md"
from research import memory as MEM  # noqa: E402  (approved entries only)

ENDPOINT = "https://api.x.ai/v1/chat/completions"
MODEL = "grok-4.3"
COST_PER_M_IN, COST_PER_M_OUT = 1.25, 2.50
LEAD_BUDGET = 202          # weighted chars left after attribution, no link (F4.3)

PAYLOAD_FIELDS = frozenset({
    "hook_facts", "support_facts", "lineage", "release", "moment", "occasion",
    "format_contract", "price_permitted", "display_name", "lead_budget", "task",
})


# ══ R3 — THE INERT-RULE GUARD ════════════════════════════════════════════════
# THREE TIMES a mechanism existed and the information never reached it. Each was
# caught by a strict test, never by reading the code:
#   1. D1 signal 2 drew its tokens from colorway AND name — but `name` contains
#      the silhouette, so signal 2 was satisfied by signal 1's own evidence and
#      the gate "confirmed" the exact misattribution it existed to stop.
#   2. F4.1 computed anniversary_age correctly, and the general pass resolved
#      first, so a 25-year anniversary lost to whichever dossier sorted first
#      alphabetically. The rule was implemented and completely inert.
#   3. F4.4 — this boundary. The selector computed anniversary_age and NOTHING
#      PASSED IT HERE, so the writer saw only "X designed the Y" and correctly
#      declined. The reason the post existed today was invisible to the only
#      component that needed it.
#
# So: every field the SELECTOR computes must either appear in the writer's
# whitelist or be listed as DELIBERATELY WITHHELD with a reason. A new selector
# field that is neither is a HARD FAILURE AT IMPORT, not a silent omission.
SELECTOR_WITHHELD = {
    "lane":            "routing, not content — which lane won says nothing to a writer",
    "day":             "reaches the writer inside `occasion`, which also says WHY",
    "image_name":      "an identifier, not a fact; the display name is passed instead",
    "moment_text":     "shipped VERBATIM by the composer; the writer must never rewrite it",
    "dossier_usable":  "a gate result already applied upstream, not content",
    "supporting_facts": "reaches the writer as `release` after field selection",
    "eligibility":     "reaches the writer as `occasion` — the hook, not the bookkeeping",
    # Declared as a pipeline field on 2026-09-11 (R2a). The moment it was
    # declared, THIS GUARD FIRED — which is the guard working: the value had
    # been computed and passed to nobody for a full commit. It reaches the
    # writer inside `occasion`, which carries both the age and the reason.
    "anniversary_age": "reaches the writer inside `occasion`, with the years and the reason",
}


def _assert_selector_boundary() -> None:
    from research import selector as _sel                 # noqa: PLC0415
    computed = set(_sel.SELECTOR_OUTPUT_FIELDS)
    mapped = {"hook_facts", "moment"}                     # pass through by name
    unaccounted = computed - PAYLOAD_FIELDS - set(SELECTOR_WITHHELD) - mapped
    if unaccounted:
        raise ImportError(
            "selector computes %s but writer neither passes nor withholds them. "
            "Add each to PAYLOAD_FIELDS or to SELECTOR_WITHHELD with a reason — "
            "an unaccounted field is how a rule goes inert (see R3 notes above)."
            % sorted(unaccounted))


class WriterError(RuntimeError):
    pass


class _ServerError(WriterError):
    """5xx / transport — a fallback provider MAY be tried."""


def _soul() -> str:
    return SOUL.read_text(encoding="utf-8")


def system_prompt(format_contract: str) -> str:
    """Everything the model is told before it sees a fact.

    ★ E2.5: memory is appended HERE and nowhere else, so there is exactly one
    place a memory entry can enter a draft — which is what makes "a pending
    entry never reaches a draft" a provable statement rather than a hope.
    memory.for_prompt() returns approved entries only, and "" when none are.
    """
    out = _soul() + "\n\n" + format_contract
    mem = MEM.for_prompt()
    if mem:
        out += "\n\n" + mem
    return out


def build_payload(*, hook_facts: list[dict], release: dict | None,
                  moment: dict | None, price_permitted: bool,
                  display_name: str, task: str, format_contract: str,
                  occasion: dict | None = None,
                  lineage: list[dict] | None = None,
                  support_facts: list[dict] | None = None) -> dict:
    """The whitelist. Only these keys, ever."""
    payload = {
        # text/tag/id only — never the whole fact object, never a spec fact
        "hook_facts": [{"id": f["id"], "tag": f["tag"], "text": f["text"]}
                       for f in hook_facts if f["tag"] != "spec"],
        # SUPPORTING COLOUR ONLY — never a hook. GOAT's designer field describes
        # the SILHOUETTE, so it may appear inside a lead hooked elsewhere and
        # must never be the reason a post exists (G1).
        "lineage": [{"text": f["text"]} for f in (lineage or [])],
        # SUPPORT — may EXTEND a lead hooked elsewhere, never carry a post.
        # Capped and ranked upstream by distinctiveness, not order of appearance.
        "support_facts": [{"id": f["id"], "text": f["text"]}
                          for f in (support_facts or [])],
        "release": ({"release_date": release.get("release_date"),
                     "year": release.get("year")} if release else None),
        # ★ WHY THE POST EXISTS TODAY. Without this the writer sees only
        # "X designed the Y" and correctly DECLINES — measured on the first
        # live call, which returned {"lead": null} for aj3_mocha_og's 25th
        # because the anniversary was never passed. The selector computes
        # anniversary_age; it is the hook, and the designer is the payload.
        "occasion": occasion,
        "moment": ({"title": moment.get("title"), "year": moment.get("year"),
                    "text": moment.get("text")} if moment else None),
        "format_contract": format_contract,
        "price_permitted": bool(price_permitted),
        "display_name": display_name,
        "lead_budget": LEAD_BUDGET,
        "task": task,
    }
    extra = set(payload) - PAYLOAD_FIELDS
    assert not extra, "payload widened beyond the whitelist: %s" % sorted(extra)
    assert all(f["tag"] != "spec" for f in payload["hook_facts"]), "spec fact leaked"
    return payload


FORMAT_CONTRACT = """\
You return JSON: {"lead": "<one line>", "body": null, "fact_id": "<id>"}

HARD CONSTRAINTS
- `fact_id` is the id of the ONE fact in hook_facts your lead is built on. The
  image is composed from that same fact, so naming a fact you did not use
  produces a picture about one thing and a sentence about another. If you write
  no lead, return "fact_id": null.
- `lead` must be at most %d characters. This is not a target, it is a ceiling.
- Use ONLY the facts given to you. Every date, name and number must appear in
  hook_facts, release, or moment. Inventing one detail is worse than writing
  nothing, because a fluent post with one false detail costs the account its
  credibility permanently.
- Do NOT write the attribution sentence ("Its card is in CYPHER..."). It is
  appended for you. Do not mention the app, a link, or a price unless
  price_permitted is true and the figure was given to you.
- No hashtags. No emoji unless the fact itself is playful. No "check this out".

REGISTER — WRITE LIKE A SNEAKERHEAD, NOT LIKE A PRODUCT DATABASE
Literal-but-unnatural phrasing FAILS this bar even when it passes every rail.
"Travis Scott's first sneaker collaboration in female sizing" is accurate, and
no person in this culture has ever said "female sizing".

  say                      not
  ----------------------   ------------------------------
  women's sizing / (Wmns)  female sizing, women-oriented
  colorway                 color scheme, colour variant
  dropped / released       arrived, became available, launched onto the market
  pair / pairs             item, unit, product
  collab                   collaboration piece, co-branded release
  on foot                  when worn, in wear

Contractions are fine. Fragments are fine. Say "the 3" or "AJ1" the way people
do. Do not explain the culture to itself — a reader who needs "the Swoosh (the
Nike logo)" explained is not the reader.

THE ONE TEST THAT MATTERS — THE SWAP TEST
If your line still reads fine with a different shoe's name swapped in, it has
failed. "2019. $150 retail. The Travis Scott x Jordan 1 debuted as the first
collaboration in women's sizing" is a database row wearing a sentence — every
shoe has a year and a retail price. Only one shoe has the story. Write the line
only this shoe could carry.

If the facts you were given cannot support such a line, return
{"lead": null, "body": null, "fact_id": null}. Silence is a valid and expected
output. A missed day costs nothing; a filler post costs attention we cannot buy
back.
""" % LEAD_BUDGET

TASK_GENERAL = """\
Write the opening line of a post for a sneaker trading-card app's X account.

`support_facts` are DETAIL, never a hook. They describe the shoe — materials,
packaging, construction. THE ASYMMETRY MATTERS:
  - they may EXTEND a lead that is already hooked on something else
  - they may NEVER carry the post. A post whose content is entirely support
    material IS a spec post, and the swap test exists to reject exactly that
  - a lead that could be swapped onto another shoe still FAILS even if a
    support fact makes it longer
BUT USE THEM WHEN THEY EARN IT. A support fact that names a concrete, surprising
thing — an object, a place, a number, a piece of packaging — is often the detail
a reader actually stops for. "It came in a hexagonal red candy box with an
interior tray" is worth more than another clause about the shoe. Lead with the
hook, then let ONE such detail land.

What does NOT earn it: materials and construction. "Full hairy suede", "rubber
cupsole", "padded tongue" describe every shoe of that type and will fail the
swap test on their own.

LENGTH IS NOT THE GOAL. A 98-character post that lands beats a 240-character
post padded with materials copy. If no support fact carries a concrete detail,
leave them all out and write the short post.

`lineage` is SUPPORTING COLOUR, never a hook. It names the silhouette a shoe is
built on and who designed THAT SILHOUETTE — not this colorway, collab or SP. So
never write "the [this shoe] designed by [name]"; that is false. You may write
"built on the silhouette [name] drew" inside a line hooked on something else.

`occasion` tells you WHY THIS POST EXISTS TODAY — an anniversary, a moment.
If there is an occasion, IT is your hook and the facts are the payload:
"25 years ago today, ..." lands where "X designed the Y" does not. If
occasion is null and the facts carry no story of their own, decline.

WHAT A GOOD POST DOES: a sneakerhead is scrolling. Your line has to make them
stop, feel something, and want in. The feeling you are aiming for is either
"I didn't know that" or "I remember that day". Not "here is a shoe" — a reason
this shoe is worth a sentence TODAY.

You are not writing a caption. You are writing the one line that earns the
three seconds before someone scrolls past."""

TASK_MOMENT_LINK = """\
A verified cultural moment is being posted VERBATIM — you must not rewrite it,
quote it, or restate it. It is already written and already approved.

Write ONE short line that connects that moment to the card shown, so the post
does not read as two unrelated halves. It should feel like the same voice
finishing the thought. If you cannot add anything the moment does not already
say, return {"lead": null} — the moment and the card alone are a complete post."""


def _call(payload: dict, env: dict, failed_rails: list[str] | None = None) -> tuple[dict, dict]:
    key = env.get("XAI_API_KEY")
    if not key:
        raise WriterError("XAI_API_KEY absent")
    user = json.dumps(payload, ensure_ascii=False, indent=1)
    if failed_rails:
        user += ("\n\nYOUR PREVIOUS ATTEMPT WAS REJECTED by these content rails: "
                 + "; ".join(failed_rails)
                 + "\nRewrite so none of them trip. Do not argue with them.")
    body = {"model": MODEL, "temperature": 0.9,
            "messages": [{"role": "system",
                          "content": system_prompt(payload["format_contract"])},
                         {"role": "user", "content": user}],
            "response_format": {"type": "json_object"}}
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer %s" % key,
                 "Content-Type": "application/json",
                 "User-Agent": "cyphermarketer/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        if 500 <= e.code < 600:
            raise _ServerError("xAI %s: %s" % (e.code, detail))
        raise WriterError("xAI %s (NOT retried on another provider): %s" % (e.code, detail))
    except Exception as e:
        raise _ServerError("transport: %s" % type(e).__name__)
    txt = raw["choices"][0]["message"]["content"]
    usage = raw.get("usage") or {}
    cost = (usage.get("prompt_tokens", 0) / 1e6) * COST_PER_M_IN + \
           (usage.get("completion_tokens", 0) / 1e6) * COST_PER_M_OUT
    try:
        out = json.loads(txt)
    except Exception:
        m = re.search(r"\{.*\}", txt, re.S)
        out = json.loads(m.group(0)) if m else {"lead": None, "body": None}
    return out, {"usage": usage, "cost_usd": round(cost, 6), "model": MODEL}


def make_draft_fn(*, hook_facts, release, moment, price_permitted, display_name,
                  env, occasion=None, lineage=None, support_facts=None,
                  meter: list | None = None):
    """A draft_fn for daily_digest.draft_with_gate8. Returns {"lead","body"}."""
    task = TASK_MOMENT_LINK if moment else TASK_GENERAL
    payload = build_payload(hook_facts=hook_facts, release=release, moment=moment,
                            price_permitted=price_permitted, occasion=occasion,
                            lineage=lineage, support_facts=support_facts,
                            display_name=display_name, task=task,
                            format_contract=FORMAT_CONTRACT)

    valid_ids = {f["id"] for f in payload.get("hook_facts") or []}

    def draft_fn(ctx, attempt, failed_rails):
        out, meta = _call(payload, env, failed_rails)
        if meter is not None:
            meter.append(meta)
        # ★ E5: the fact the model says it wrote from. The SCENE is composed from
        # this same fact, which is what makes the image and the text about one
        # thing. An id outside the payload is not trusted — see fact_id_or_none.
        claimed = (out or {}).get("fact_id")
        fid = claimed if claimed in valid_ids else None
        lead = (out or {}).get("lead")
        if not lead or not str(lead).strip():
            return None                     # the model declined — silence is valid
        return {"lead": str(lead).strip(), "body": None, "fact_id": fid,
                "fact_id_claimed": claimed}
    return draft_fn


_assert_selector_boundary()      # HARD FAILURE at import, never a silent omission
