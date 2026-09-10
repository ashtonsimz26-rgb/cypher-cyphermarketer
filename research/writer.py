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

ENDPOINT = "https://api.x.ai/v1/chat/completions"
MODEL = "grok-4.3"
COST_PER_M_IN, COST_PER_M_OUT = 1.25, 2.50
LEAD_BUDGET = 202          # weighted chars left after attribution, no link (F4.3)

PAYLOAD_FIELDS = frozenset({
    "hook_facts", "release", "moment", "occasion", "format_contract",
    "price_permitted", "display_name", "lead_budget", "task",
})


class WriterError(RuntimeError):
    pass


class _ServerError(WriterError):
    """5xx / transport — a fallback provider MAY be tried."""


def _soul() -> str:
    return SOUL.read_text(encoding="utf-8")


def build_payload(*, hook_facts: list[dict], release: dict | None,
                  moment: dict | None, price_permitted: bool,
                  display_name: str, task: str, format_contract: str,
                  occasion: dict | None = None) -> dict:
    """The whitelist. Only these keys, ever."""
    payload = {
        # text/tag/id only — never the whole fact object, never a spec fact
        "hook_facts": [{"id": f["id"], "tag": f["tag"], "text": f["text"]}
                       for f in hook_facts if f["tag"] != "spec"],
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
You return JSON: {"lead": "<one line>", "body": null}

HARD CONSTRAINTS
- `lead` must be at most %d characters. This is not a target, it is a ceiling.
- Use ONLY the facts given to you. Every date, name and number must appear in
  hook_facts, release, or moment. Inventing one detail is worse than writing
  nothing, because a fluent post with one false detail costs the account its
  credibility permanently.
- Do NOT write the attribution sentence ("Its card is in CYPHER..."). It is
  appended for you. Do not mention the app, a link, or a price unless
  price_permitted is true and the figure was given to you.
- No hashtags. No emoji unless the fact itself is playful. No "check this out".

THE ONE TEST THAT MATTERS — THE SWAP TEST
If your line still reads fine with a different shoe's name swapped in, it has
failed. "2019. $150 retail. The Travis Scott x Jordan 1 debuted as the first
collaboration in women's sizing" is a database row wearing a sentence — every
shoe has a year and a retail price. Only one shoe has the story. Write the line
only this shoe could carry.

If the facts you were given cannot support such a line, return
{"lead": null, "body": null}. Silence is a valid and expected output. A missed
day costs nothing; a filler post costs attention we cannot buy back.
""" % LEAD_BUDGET

TASK_GENERAL = """\
Write the opening line of a post for a sneaker trading-card app's X account.

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
                          "content": _soul() + "\n\n" + payload["format_contract"]},
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
                  env, occasion=None, meter: list | None = None):
    """A draft_fn for daily_digest.draft_with_gate8. Returns {"lead","body"}."""
    task = TASK_MOMENT_LINK if moment else TASK_GENERAL
    payload = build_payload(hook_facts=hook_facts, release=release, moment=moment,
                            price_permitted=price_permitted, occasion=occasion,
                            display_name=display_name, task=task,
                            format_contract=FORMAT_CONTRACT)

    def draft_fn(ctx, attempt, failed_rails):
        out, meta = _call(payload, env, failed_rails)
        if meter is not None:
            meter.append(meta)
        lead = (out or {}).get("lead")
        if not lead or not str(lead).strip():
            return None                     # the model declined — silence is valid
        return {"lead": str(lead).strip(), "body": None}
    return draft_fn
