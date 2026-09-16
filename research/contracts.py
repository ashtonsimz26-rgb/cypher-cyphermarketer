#!/usr/bin/env python3.12
"""
contracts.py — the pipeline input contract. Fails at IMPORT, never silently.

★★ THE PATTERN THIS EXISTS TO STOP
Six times a mechanism was built correctly and the information never reached
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
  R2 (09-12)    — a CHILD-SAFETY rail placed in selector.eligibility() would
                  have gated nothing: daily_digest.candidates() builds its pool
                  straight from Supabase and never calls it, and the dossiers
                  needing the gate cleared the pool filter ON MERIT, so there
                  was nothing anomalous to notice. See dossier.py's "A RAIL
                  GOES ON EVERY DOOR": one rail per entry point, one test per
                  path
  RAIL RETRY      — gate8 was called TWICE inside draft_with_gate8: once on the
  (09-16)           composed text and once on the bare retry. The pair that
                    proves obtainability was threaded into the first call and
                    not the second, so the primary path enforced the rail and
                    the RETRY path walked around it — on the same rail, in the
                    same function, four lines apart
Four of the first six were caught by a strict test or by reading output. NONE was
caught by reading code; the sixth was caught only by asking which code path
actually runs at 09:00 — a different question from whether the code is
correct.

★★★ AN EQUALITY TEST THAT SHOULD HAVE BEEN A MEMBERSHIP TEST (2026-09-16)
★★★ AND THE FIRST BUG HERE THAT WOULD HAVE SHIPPED AS A COHERENT POST

Every other entry in this file fails visibly: a crash, an empty morning, a
missing dossier, a rail that lets something through. This one would have
PUBLISHED, and the output would have looked like a decision somebody made.

    composition.render():   fn(card, bd, size, card_b) if name == "two_card"
                            else fn(card, bd, size)

    two_card_crop also accepts card_b, and E4 FORCES two_card_crop for
    which_would_you_pull. So the second card was dropped and the composite drew
    `(card_b or card, card)` — THE SAME CARD, TWICE, side by side, under the
    caption "Which one are you pulling for?"

  ★ THE SHAPE: A MEMBERSHIP TEST WRITTEN AS AN EQUALITY TEST, CORRECT WHEN
  WRITTEN AND SILENTLY WRONG ONCE A SECOND MEMBER EXISTED. When render() was
  written, `two_card` was the only composition taking a second card, so
  `== "two_card"` and "is a two-card composition" were the same predicate. They
  stopped being the same predicate the moment two_card_crop was added, and
  nothing announced it, because the equality was still TRUE of everything it had
  ever been true of. The code did not change. Its meaning did.

  THE RULE: when a branch tests one name, ask what the branch actually MEANS. If
  the answer is a category ("compositions that draw two cards", "formats that
  can voice a price", "tiers that are serial-numbered") then name the category
  as a frozenset and test membership, at the moment you write it — not when the
  second member arrives, because nobody is watching then. An equality against a
  literal is only safe when the literal is genuinely the whole category and
  always will be.

  ★ WHY IT IS BANKED HARDEST: the failure mode is a COHERENT-LOOKING ARTIFACT.
  Two identical cards under "which would you pull" reads as a person's mistake —
  a bad copy-paste, a sloppy afternoon — not as a system fault. Nothing would
  have errored, no rail would have fired, the ledger would have recorded a
  normal post, and the weekly report would have counted it as a
  which_would_you_pull that shipped. The only detector was a human noticing the
  two pictures were the same. Every OTHER entry in this file at least fails.

  It was found by READING render() for an unrelated reason (the clear-zone
  ownership question), three commits after E4 shipped, and E4's own suite was
  green before and after — it tested pair SELECTION thoroughly and never
  followed the pair into the compositor. A suite that proves the right pair is
  chosen proves nothing about whether both cards are drawn.

★★★ A STALE VALIDATOR DENIES, AND DENIAL LOOKS LIKE CORRECTNESS (2026-09-16)
This is its own lesson and not a variant of the inert rail. Read it before the
numbered list.

  research/moments.py validated every moment's linked_image_names against
  state/_reachable_cache.json. NOTHING WROTE THAT FILE. Not one line in the
  repo. It had been sitting there since 2026-09-09 while the obtainable set
  grew, so links to newly obtainable cards were being dropped — correctly, by
  the rule, against a snapshot that had stopped being true.

  AN INERT RAIL PERMITS. A STALE VALIDATOR DENIES. That asymmetry is the whole
  point. When a rail goes inert, bad things get through and eventually somebody
  sees one. When a validator's reference data goes stale, good things are
  refused — and a refusal produces no artifact, no error, and no symptom. The
  system looks conservative. It looks like it is working. There is nothing to
  notice.

  load_reachable() made it worse by returning set() on ANY exception. An empty
  reference set does not permit everything; it REFUSES everything, one link at
  a time, quietly.

  THE RULE, two halves:
    1. Any cache a check reads NAMES ITS WRITER IN ITS OWN HEADER — in the file
       it writes, and in the module that reads it. A literal path is invisible
       to whoever greps for the writer, which is precisely how this one came to
       have none.
    2. A check whose reference data is missing, undated or stale FAILS CLOSED
       AND SAYS SO. Never an empty set, never a silent skip. "I cannot validate
       this" and "this is invalid" are different answers and must not share a
       code path.

  A DELIBERATE SWEEP of state/ on 2026-09-16 found one more, and it is a
  DIFFERENT failure — see the next entry. Everything else under state/ is read
  and written by one module (drop_queue, seen_headlines, telegram_offset,
  health_streaks, last_format), is a scratch file for the SQL CLI (_dq, _q,
  _card_input), or already had a TTL and a named writer (url_cache,
  _set_routes).

  THIRD OCCURRENCE OF THE DOCSTRING TRAP, same session: the test written to
  prove this cache has exactly one literal path FAILED, on the comment inside
  refresh_set_routes explaining that the file used to have no writer. Three
  times in one session — twice against the rule's own author, once against a
  comment describing the very bug the test covers. Treat "grep the source for a
  token" as a habit to be interrupted, not a technique to be used carefully.

  It was found BY ACCIDENT, while checking whether a moment's links resolved.
  Nobody was looking for it. That is the expected way to find this class, which
  is the argument for the rule rather than for vigilance.

★★ "REFRESHES ONLY WHEN ABSENT" IS NOT THE SAME BUG AS "HAS NO WRITER"
dossier.load_catalog() is the second half of the state/ sweep and deserves
separating, because it fails in a way the first does not LOOK like.

  A file nothing writes is visibly orphaned: grep for the writer, find nothing,
  and the problem announces itself to anyone who asks. load_catalog() is the
  opposite. It has a writer, in the same function, four lines below the read.
  It is self-healing on a fresh checkout. It LOOKS maintained. And it refreshed
  only `if not CATALOG_CACHE.exists()`, so after the first run it never
  refreshed again — stale by construction, for the life of the machine.

  What it feeds DENIES: dossier.main() does `if not cat: continue`, so a card
  the snapshot predated gets no dossier, no error and no log line.

  ★ IT WAS HARMLESS BY COINCIDENCE, AND THE NEXT SESSION SHOULD KNOW THAT. When
  it was checked on 2026-09-16 the cache held 1,485 image_names and the live
  catalog held 1,485 — identical, no drift. Not because anything kept them in
  step. Because the server catalog happened not to have changed in the seven
  days since the file was written. CPA adds cards continuously; the additions
  had gone to the Swift side rather than to catalog_cards. One ordinary CPA
  batch would have produced silently dossier-less cards, and the first symptom
  would have been "why does that shoe never post". It worked by luck, not by
  design, and the luck was one commit wide.

  THE RULE: a cache with a TTL of "forever" is a snapshot, and a snapshot read
  by a check is stale the moment its source moves. `if not exists()` is not a
  refresh policy. Give it an age, or re-fetch every run, or do not cache it.

★★ A TEST FIXTURE CAN HIDE THE BUG IT WAS WRITTEN TO CATCH (2026-09-16)
The cypher:// resolver was built and tested against a GRAIL and shipped green.
It was wrong for four of the six tiers.

  catalog_cards.rarity is the sneaker_rarity ENUM, mixed case — Common,
  Uncommon, Rare, Legendary, GRAIL, HOLY GRAIL. owned_cards.rarity is TEXT under
  a CHECK constraint, UPPERCASE. THEY AGREE ON EXACTLY TWO VALUES: GRAIL and
  HOLY GRAIL. The fixture was one of the two.

  So the test passed for a reason that had nothing to do with the code being
  right, and the passing test was evidence of nothing. Asked for a minted
  Legendary the resolver returned a rendered "NOT MINTED" document — and because
  that is an ANSWER rather than a failure, verify_fact reported a TRUE claim as
  "contradicted" rather than "unverified". That is the sharpest instance of that
  distinction in this repo: the module's own header warns that a caller may act
  against a fact on a contradicted result, and this would have handed it one.

  THE RULE: when two systems use different vocabularies for the same concept,
  choose a fixture where they DISAGREE. A value the two happen to share tests
  the code against itself. Where no disagreeing value exists yet, write the
  normaliser anyway and test it directly.

  It was found only because an unrelated question was asked — a schema audit
  about write-path validation, on the same column, for a different reason. The
  resolver's own suite was green before and after.

★ AND THE FIRST REPORT OF THAT SCHEMA ISSUE WAS WRONG, WHICH IS PART OF THE
RECORD. It was first reported as an integrity hole: "owned_cards.rarity is not
constrained by the enum at all, so a malformed rarity string can be written
today." Checking rather than asserting produced owned_cards_rarity_check, a
second constraint coupling rarity to serial numbering, no Postgres function
writing the table, and RLS enabled with a single SELECT-own policy and no write
policy — so a client cannot write it at all. It was downgraded to a consistency
problem in the same session. The first version was a plausible inference from
one true fact (the column is `text`) and it was wrong about the consequence.
Keep both in the record: the correction is the useful part, because the
inference was reasonable and still wrong.

★★ THE EIGHTH: A FILTER THAT REMOVED WHAT THREE COMMITS WERE BUILT TO ENABLE
The first seven are all "a value existed and nothing read it". The eighth is the
mirror image and it is worse, because the work looked finished:

  daily_digest.candidates() built its standout pool with
  `where c.is_set_reward = false`. Three commits had just gone in to make the
  three set rewards postable — SOUL amended, the rail widened and made to
  actually run, build_one's guard made conditional, dossiers imported, scenes
  resolved, a copy skeleton written. Every one of them worked. And the cards
  could still never appear, because a where clause four layers away removed them
  from the pool before any of it was consulted. drop_correspondent carried the
  same clause, byte for byte.

  THE RULE: PERMISSION AND PRESENCE ARE DIFFERENT CLAIMS. When a rail is widened
  to admit something new, do not test that the rail permits it — test that it
  REACHES THE POOL. Ask "what would actually select this card at 09:00", follow
  that path all the way to the query, and read every where clause on it.

The 2026-09-16 audit of that path found FOUR more, all removing cards the rails
now permit: the drop-queue drain and the on-this-day seed both gated on
is_reachable() (pool route only, so a set reward matched to a headline or a date
was dropped before rails saw it); drop_correspondent's twin is_set_reward
clause; and moments.py validating linked_image_names against
state/_reachable_cache.json — a file WRITTEN BY NOTHING, last touched a week
earlier, so a moment linking a newly-obtainable card had that link silently
dropped. Four filters, one rail, and the rail was never wrong.

★★ THE SEVENTH IS A NEW SHAPE, AND THE FIRST CAUGHT BY AST SCAN
The first six are all "the information never arrived". The seventh is different:
the information arrived on the MAIN path and not on the RETRY path. "A rail goes
on every door" (dossier.py) was already the rule, and it was not enough, because
a retry is not a door anyone thinks of as a door — it is the same door, taken
twice, and the second time with different arguments.

  THE RULE: every gate must have its RETRY path checked, not just its primary
  call site. Wherever a check is invoked more than once in one function — a
  retry, a fallback, a bare-text second pass, a catch-block re-run — each
  invocation is a separate enforcement point and needs its own assertion.

It is also the first instance in this list found by SCANNING THE AST rather than
by a symptom. `tests/test_obtainability_rail.py` asserts `draft_with_gate8` calls
gate8 exactly twice and that BOTH calls pass the pair. No output was wrong yet;
the bypass had simply never been exercised on a card that would fail. That is
worth noticing: reading the code would not have found it either, because both
call sites look correct in isolation — only COUNTING them and comparing their
arguments does.

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

★★ A TEST CAN MATCH ITS OWN DOCSTRING (banked 2026-09-16, self-inflicted)
Writing the earn-route suite, a check meant to prove the widening never filters
on TIER did this:

    fn = src.split("def reachable_shoes")[1].split("\ndef ")[0]
    ok("GRAIL" not in fn, "the SQL never names a tier")

It failed — on the docstring directly above the SQL, which explains that the 63
GRAIL cards stay out. The code was correct; the test was reading the wrong
bytes, and the wrong bytes were its own explanation. A more careful wording
would have hidden the bug rather than fixing it.

  ★★ THE PROHIBITION — not a caution, and not "be careful with":

      NEVER SCAN A FUNCTION'S SOURCE TEXT FOR A LITERAL. Extract it via AST.
      ALWAYS. Including in a test you expect to be trivial, including when the
      token is obviously unique, including when you have just finished writing
      this rule.

  Prose about a constraint and the constraint itself are the same bytes to `in`,
  and comments are where a constraint gets DESCRIBED — so full-text scanning is
  biased toward precisely the false positive it will hit. Three occurrences in
  one session, two of them by the author of the rule, is enough evidence that
  intention does not hold. The habit is faster to reach for than the correct
  tool, and knowing better does not slow the hand down. Remove the option.

★ IT HAPPENED TWICE IN ONE SESSION, THE SECOND TIME TO THE PERSON WHO HAD JUST
WRITTEN THE RULE. About an hour after banking the paragraph above, the E2.5
memory-loader suite asserted:

    ok(not any(w in src for w in ('!= "true"', "!= \'true\'")),
       "and no `!= true` shortcut")

and failed — on memory.py's own comment, which reads

    # `!= "true"` would admit "no", "0", "False", "" and anything a future
    # editor invents.

That is: a test checking that a shortcut was not used, defeated by the comment
explaining why the shortcut was not used. Written by the same session, against
its own newly-written rule, in the next file it touched.

Record the recurrence rather than the possibility. "This can happen" invites a
future session to believe care is sufficient. It is not: the first instance
survived review, and the second was written by someone who had the rule in
working memory. The habit — grep the source for a token — is faster to reach for
than the correct tool, and knowing better does not slow the hand down. Only the
AST does.

Same family as the entries above: the check looked right and measured the wrong
thing. It differs in being cheap to catch — it fails immediately, rather than
passing for a year. The dangerous version is the inverse: a full-text scan that
PASSES because a comment happens to contain the token it was looking for. Both
instances here were the loud kind. The quiet kind has not been caught yet, which
is not evidence it has not happened.

★★ A CHECK OVER AN EMPTY COLLECTION PASSES (four instances, 2026-09-16)

THE PATTERN IS NOT A KEYWORD. Start with the instance that proves it, because a
session grepping for `all(` / `any(` / `not exists` will not find this one:

    _phrase_rx(terms) builds a word-bounded alternation by joining `terms` with
    "|". Given an EMPTY list it compiles the empty pattern — and

        re.compile("").search("literally anything")  ->  True

    An empty vocabulary does not match nothing. It matches EVERYTHING. A curated
    entity list that failed to load would silently promote every sentence in
    every dossier to "names a person". There is no `all` in sight.

`all([])` is the same failure wearing a recognisable face; `not exists (...)`
over an empty set is the SQL face; `re.compile("")` is the face nobody
recognises. State it as the behaviour, never as the syntax:

  A CHECK OVER AN EMPTY COLLECTION PASSES. Every "all of X must hold" becomes
  "nothing was checked" when X is empty, and it does so silently, wearing the
  shape of a pass.

  THE RULE: before writing any quantifier — all, any, not exists, a joined
  alternation, a regex built from data, a loop that sets a flag — ask what the
  EMPTY case returns, and guard it EXPLICITLY. A non-empty assertion next to the
  quantifier, never a comment promising the collection is never empty.

Where this repo already guards it, so the shape is recognisable:

  dossier._phrase_rx       guarded upstream by _load_list's `not v` — the
                           empty-regex case above, and the reason that guard is
                           load-bearing rather than defensive
  dossier.has_all_tokens   `if not h or not ph: return False` before
                           `all(t in h for t in ph)` — without it, a shoe with
                           no distinctive tokens MATCHES EVERY name. D1's
                           signal 2 lives here
  rails.obtainability      a set carrying zero requirement rows is refused
                           before `all(q["reachable"] ...)` is reached
  goat_import              `exists (select 1 from set_requirements ...)` beside
                           `not exists (unreachable requirement)`, because the
                           second is vacuously true over an empty set — the same
                           guard, in SQL

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
