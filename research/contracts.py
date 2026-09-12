#!/usr/bin/env python3.12
"""
contracts.py — the pipeline input contract. Fails at IMPORT, never silently.

★★ THE PATTERN THIS EXISTS TO STOP
Five times a mechanism was built correctly and the information never reached
it. Each time the code was LOCALLY CORRECT, so no file's review found it — the
defect lived in the GAP BETWEEN components, which is exactly where reading one
file at a time does not look:
  D1 signal 2   — cross-check drew its tokens from a source that already
                  encoded signal 1, so it "confirmed" what it existed to catch
  F4.1          — anniversary precedence lost to pool order; the rule was
                  implemented and completely inert
  F4.4          — the selector computed `occasion`; nothing passed it to the
                  writer, which then correctly declined to write
  G4            — detect_hook read row["description"] and never the dossier,
                  so the verified fact that justified a post was invisible to
                  the component choosing its hook
Four of the five were caught by a strict test or by reading output. NONE was
caught by reading code.

THE RULE: a field this pipeline PRODUCES and no decision-maker READS is an
ImportError. That is the inert-rule signature — a value exists, and nothing
consumes it — converted from a silent behavioural defect into a build failure.

Deliberate non-consumption stays legal, but must be EXPLICIT: name the field in
WITHHELD with a one-line reason. The failure mode here is silence, not
omission, so the fix is to make silence impossible rather than to ban omission.

★★ WHAT THIS DOES **NOT** CATCH — READ THIS BEFORE TRUSTING IT
A component that reads the WRONG input PASSES this contract. D1 signal 2 is
exactly that: the field was declared, it was read, and it was the wrong field —
`name` already contained the silhouette, so the "independent" corroboration
corroborated nothing. Every declaration in this file would have been satisfied
while the gate was broken.

★★ AND IT CATCHES FEWER OF THE FIVE THAN FIRST CLAIMED — MEASURED, NOT GUESSED
The proposal said this "catches F4.4 and G4 cleanly". Building it and testing
it showed that is WRONG about G4, and the reason is structural:

  The question this contract asks is "is this field read by AT LEAST ONE
  decision-maker?" — not "is it read by the RIGHT one."

  F4.4 (occasion): read by NOBODY. CAUGHT.
  G4 (hook_facts): read by the WRITER. detect_hook not reading it leaves the
                   field consumed, so the contract stays green while the hook
                   selector is blind to the dossier. NOT CAUGHT.
  D1 signal 2:     the field was declared and read; it was the WRONG field.
                   NOT CAUGHT.
  F4.1:            precedence/ordering, not a field at all. NOT CAUGHT.

So the honest tally is ONE of four, plus every future instance of the same
shape — a value produced and consumed by nothing. That is still worth having,
because it is the most common shape and it converts a silent behavioural defect
into a build failure. But it is not the general cure the proposal implied.

WHAT THE REMAINING THREE NEED:
  wrong-input (D1)    an ADVERSARIAL TEST: feed the component input it should
                      reject and assert that it does
  wrong-consumer (G4) a per-consumer expectation — "detect_hook MUST read
                      hook_facts" — which is a different and heavier contract
                      than this one
  ordering (F4.1)     a test that the SELECTOR RETURNS the thing, never that
                      the calendar CONTAINS it
Do not read this module and conclude the gap class is closed. It is not.
"""
from __future__ import annotations
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import editorial                                   # noqa: E402
import daily_digest as DD                          # noqa: E402
from research import selector as SEL               # noqa: E402
from research import dossier as DOS                # noqa: E402
from research import writer as WR                  # noqa: E402
from research import compose_text as CT            # noqa: E402

# ── what the pipeline PRODUCES ───────────────────────────────────────────────
PRODUCED: dict[str, frozenset] = {
    "selector": SEL.SELECTOR_OUTPUT_FIELDS,
    "dossier": DOS.DOSSIER_OUTPUT_FIELDS,
    "release_dates": frozenset({"release_date", "year", "style_code"}),
    "catalog": frozenset({"description", "retail_price", "estimated_resale",
                          "brand", "scene", "display_name"}),
    "rails": frozenset({"price_verified"}),
    "composition": frozenset({"composition", "card_shows_value", "tentpole"}),
    "rotation": frozenset({"rotation_history"}),
    "writer": frozenset({"lead", "body"}),
    "moments": frozenset({"moment_post_text", "moment_id"}),
}

# ── what each DECISION-MAKER reads ───────────────────────────────────────────
READS: dict[str, frozenset] = {
    "editorial.detect_hook": editorial.DETECT_HOOK_READS,
    "editorial.choose_format": editorial.CHOOSE_FORMAT_READS,
    "daily_digest.build_one": DD.BUILD_ONE_READS,
    "daily_digest.pick_composition": DD.PICK_COMPOSITION_READS,
    "daily_digest.gate8": DD.GATE8_READS,
    "daily_digest.occasion_for": DD.OCCASION_READS,
    "research.writer": WR.PAYLOAD_FIELDS,
    "research.compose_text.compose": CT.COMPOSE_READS,
}

# ── deliberate non-consumption, each with a reason ───────────────────────────
WITHHELD: dict[str, str] = {
    "lane": "routing, not content — which lane won says nothing to a decision-maker",
    "day": "reaches consumers inside `occasion`, which also says WHY",
    "image_name": "an identifier, not a fact; display_name is passed instead",
    "moment": "the entry object; only moment_post_text and moment_id are consumed",
    "moment_text": "alias of moment_post_text, kept for the selector's own shape",
    "supporting_facts": "reaches the writer as `release` after field selection",
    "eligibility": "reaches the writer as `occasion` — the hook, not the bookkeeping",
    "dossier_usable": "a gate result applied upstream; no downstream decision reads it",
    "name_match": "a dossier-build gate result, not a drafting input",
    "spec_facts": "ranked and capped into support_facts; the raw bucket is not consumed",
    "narrative_detail_facts": "ranked and capped into support_facts alongside spec_facts; the raw bucket is not consumed",
    "fact_sensitivity": "applied inside dossier.build() before any bucket exists — it REMOVES facts from hooks, support and lineage; no drafting decision reads the field itself",
    "lineage_facts": "reaches the writer as `lineage` after field selection",
    "release_date_fact": "reaches consumers as `release_date` from release_dates",
    "style_code": "rails input only; no drafting decision reads it",
    "hook_type": "produced by detect_hook and read by choose_format (declared there)",
    "format": "produced by choose_format and read by pick_composition (declared there)",
    "headline": "drop_correspondent input, declared by detect_hook",
    "source": "candidate provenance, declared by detect_hook",
    "occasion": "produced by occasion_for, consumed by the writer (declared there)",
    "lineage": "writer payload field, fed from lineage_facts",
    "hook_facts": "read by detect_hook and the writer (declared in both)",
    "text": "gate8 input, produced by compose",
    "format_contract": "static writer scaffolding, not a pipeline value",
    "price_permitted": "the writer's name for price_verified",
    "lead_budget": "a constant, not a produced field",
    "task": "static writer scaffolding",
    "linking_line": "the writer's lead on a moment day",
    "last_format": "rotation state read by choose_format (declared there)",
    "avoid_codes": "reject-reason feedback read by choose_format (declared there)",
    "anniversary_age": "computed by the selector, consumed by occasion_for (declared there)",
    "release_date": "read by occasion_for for the anniversary check (declared there)",
}


def unconsumed() -> dict[str, str]:
    """Produced fields that no decision-maker reads and nobody withheld."""
    consumed: set[str] = set()
    for r in READS.values():
        consumed |= set(r)
    out = {}
    for producer, fields in PRODUCED.items():
        for f in fields:
            if f not in consumed and f not in WITHHELD:
                out[f] = producer
    return out


def assert_contract() -> None:
    orphans = unconsumed()
    if orphans:
        raise ImportError(
            "PIPELINE CONTRACT VIOLATION — these fields are PRODUCED and read by "
            "no decision-maker:\n" +
            "\n".join("  %-24s produced by %s" % (f, p) for f, p in sorted(orphans.items())) +
            "\n\nThat is the inert-rule signature: a value exists and nothing "
            "consumes it. Either add the field to a decision-maker's READS, or "
            "name it in contracts.WITHHELD with a one-line reason. Do not delete "
            "this check.")


assert_contract()          # HARD FAILURE at import, never a silent omission
