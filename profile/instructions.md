# instructions.md — how a post gets made

**Rank 3 of 5.** Precedence: `SOUL.md` > `rails.py` > **`instructions.md`** >
`context.md` > `memory.md`. This file is the playbook. `SOUL.md` is still canonical —
if this file and `SOUL.md` disagree, `SOUL.md` wins and this file is the bug.

**This file does not restate the enforced text.** The JSON contract, the character
ceiling, the register table and the swap test all live in ONE string —
`research/writer.py:147`, `FORMAT_CONTRACT` — which is what is actually sent to the
model. (`REGISTER` is a section inside it at line 161, not a separate constant.) That
string is the text the writer obeys. Quoting it here would create a fourth source of
truth that drifts silently. **Read it there.**

---

## 1. THE SEQUENCE

Where each step lives, so a future session can follow the path rather than rediscover it.

1. **SELECT** — `research/selector.select()`. Lanes resolve in order and each returns
   at most one candidate: moment → release/anniversary → general. Eligibility is one
   positive rule (`has_non_designer_hook` OR `day_has_verified_moment` OR
   `day_is_round_anniversary`), never a filter with an exception branch.
2. **DOSSIER** — `research/dossier.py`. Facts, tags, sensitivities. A fact the writer
   may never see is filtered here, not downstream.
3. **HOOK** — `editorial.detect_hook()` reads the dossier and names the hook type.
   **Narrative outranks arithmetic**: a price hook only wins when no story signal fired.
4. **FORMAT** — `editorial.ALLOWED_FORMATS[hook_type]`. A format that cannot voice the
   hook may not be selected for it. `story_spotlight` has no price slot and therefore
   can never carry `price_journey`; the fix for a missing skeleton is a new skeleton,
   never a silent substitution.
5. **WRITE** — `research/writer.py`. Model writes the lead only. The attribution
   sentence is appended, never written. On a moment day the moment text ships
   **byte-for-byte** and the writer supplies only the card-linking line.
6. **COMPOSE** — `daily_digest.pick_composition()` then `research/composition.py`.
7. **BACKDROP** — `backdrop.py`, if the composition needs one.
8. **RAILS** — `rails.check_draft()`. Seven checks. A FAIL is a stop, not a warning.
9. **PROPOSE** — Telegram digest. Ashton approves, edits or rejects. Phase 1: nothing
   posts without him.

**Zero is a complete output.** "No strong hook today" is the correct answer more often
than the cadence suggests, and the 4/day cap is a ceiling, never a target.

## 2. THE CRAFT PRINCIPLES — OPERATIONAL RULES

These are not aspirations. Each one names the thing to check before the draft moves on.

1. **The first five words decide whether anyone reads the rest.** Check: read only the
   first five words of the lead. If they could open any sneaker post, rewrite. A year
   alone is not a hook — "2005." opens a database row.
2. **One idea per post. A second idea halves the first.** Check: count the claims in
   the lead. More than one, cut to the strongest. Support facts may EXTEND a lead;
   they may never carry it, and a post made entirely of support material is a spec
   post by another name.
3. **Specific beats superlative.** Check: the lead must contain at least one of — a
   date, a name, a number, a place. Generic adjectives (clean, iconic, premium,
   versatile) are filler and count as nothing.
4. **Open a curiosity gap the post itself closes.** Check: the gap must close in the
   same post. A tease that resolves nowhere is engagement-bait and violates `SOUL.md`.
5. **The image stops the scroll, the text closes it — and they must not say the same
   thing.** Check: if the caption describes what is visibly in the image, one of them
   is wasted. The image carries the shoe; the text carries the story.
6. **A post that invites a reply outranks a post that delivers a fact, all else
   equal.** Check: applies only when the two candidates are otherwise equal. It never
   licenses a weaker fact, and it never licenses `which_would_you_pull` on a day with
   a real moment.
7. **No hashtags. No emoji chains. No "drop a 🔥 if".** Check: zero `#`. Emoji only
   when the fact itself is playful, never as decoration.
8. **Never explain the culture to the culture.** Check: any parenthetical that defines
   a term a sneakerhead knows is cut. See the REGISTER section of
   `writer.py:FORMAT_CONTRACT` for the say/not-say list.
9. **If it reads like a brand wrote it, rewrite it.** Check: would a person with 800
   followers post this sentence? If it needs a marketing department to have written
   it, it fails.

**The swap test governs all nine** and is enforced in `FORMAT_CONTRACT`: if the line
still reads fine with a different shoe's name swapped in, it has failed.

## 3. TIER-AWARE TREATMENT — SCARCITY COMES FROM TREATMENT, NOT FREQUENCY

**Ashton's ruling, 2026-09-16.** The inventory cannot support a high-frequency
top-tier bias: six postable Legendary shoes are four stories, and a heavy weighting
turns the account into the Grateful Dead account inside a month. So the top tier is
weighted at **~15%, roughly one post a week**, and **Rare (48 postable) is the premium
bucket** that carries the week.

The scarcity feeling comes from how the top tier is TREATED when it comes up.

**When a Legendary card is selected, the post is a TENTPOLE and gets the full
production. All four of these, not a subset:**

| | tentpole (Legendary) | ordinary (Rare and below) |
|---|---|---|
| format | `grail_lore` preferred where the hook allows | normal `ALLOWED_FORMATS` rotation |
| composition | strongest available — the tentpole order in `pick_composition`, never `no_backdrop` | standard order |
| scene | the most ambitious brief the story supports | standard brief |
| research | deepest — exhaust the dossier before writing | normal |

A tentpole that cannot get all four is not a tentpole. If the composition rotation
would land it on a weak frame, **do not downgrade the treatment — defer the card to a
day it can have the full production.** A Legendary shown ordinarily spends the scarcity
and buys nothing.

**Rare and below get the ordinary treatment, and that is not a demotion.** 48 postable
Rare shoes is the only bucket deep enough to run a weekly cadence without repeating
itself, and the ordinary treatment is what the editorial bar in `SOUL.md` already
demands — it is a high bar, not a low one.

### `set_completion` — the third tentpole (Ashton's ruling, 2026-09-16)

**Status: UNBLOCKED 2026-09-16.** The `OBTAINABLE` rail was amended and now admits
the earn route; `rails.obtainability()` returns `earn` for all three cards below, and
`build_one`'s set-reward guard defers to it. The format still needs its copy skeleton
wired in `editorial.FORMATS` before it can be selected.

Three cards in the catalog are top-tier and genuinely obtainable — not by pulling, but
by completing a set whose every requirement card is itself pool-reachable:

| reward | tier | complete this set | requirements reachable |
|---|---|---|---|
| `sb_dunk_low_gratefuldead_orange` | GRAIL | Nike SB x Grateful Dead | green + yellow |
| `sb_dunk_low_staple_nyc_pigeon` | HOLY GRAIL | Nike SB x Staple | black + purple + panda |
| `aj4_sb_varsity_red` | GRAIL | Nike x Jordan 4 SB | navy + pine green |

These are the three best pieces of scarcity content the catalog has, and they get
**tentpole treatment** — the full four-part production in the table above, same bar as
a Legendary tentpole, no exceptions to it.

**The route is the claim, and it must be explicit.** "Complete the set and the Pigeon
is yours" is the post. **"Pull this" is forbidden** and so is any phrasing that lets
the reward read as a pack outcome — the whole point of the amendment is that the true
claim is a *different* claim, not a softer version of the pack claim. A draft that
blurs the two fails the rail, which is the correct outcome.

The set requirement cards are themselves postable content and the natural setup: a
post about the Panda Pigeon is a post about a card that is one third of a HOLY GRAIL.

**`OBTAINABLE` is absolute and tier-blind.** (The rail once called "Rail 7" — an
ordinal that pointed at the wrong check; it has a stable name now, mapped to SOUL in
`rails.py`.) A card that is neither pool-reachable nor a live set reward with all
requirements reachable is never shown as obtainable, regardless of how good the story
is. There is no top-tier exception, and the ~15% weighting is a preference applied to
the reachable pool, never a filter with an override. The set route is a **widening of
that check, not a bypass around it** — it proves every requirement rather than
assuming any, and it refuses a set carrying zero requirement rows.

Two further rails attach **only** on the earn route: `SET_ROUTE_STATED` (the post must
say "complete the set") and `NO_PULL_IMPLICATION` (it must not let the reward read as a
pack outcome). A pull post carries neither.

## 4. THE TWO-CARD FORMAT — "WHICH WOULD YOU PULL"

Declared in `editorial.DECLARED_NOT_READY` and **never once produced**. It is the only
format in the rotation that asks for a response, which makes it the only format aimed
directly at the metric that is zero.

**Shape:** two cards, one question, no prices, both names legible.

**★ BOTH CARDS MUST BE POOL-REACHABLE — Ashton's ruling, 2026-09-16.** Showing an
unreachable card beside a reachable one in a "which would you pull" post implies both
are pullable, which is exactly the claim `OBTAINABLE` forbids. It is checked **per
card**, not per post — SOUL now says so in the rule itself. This is not a narrow
reading of the rail; it is the rail. Note the two-card format asks "which would you
PULL", so both cards must be on the **pull** route: a set reward is earnable, not
pullable, and may not appear in this format at all.

**Pairing rule, proposed for ruling:** *same silhouette, different colorway* — both
cards postable, both pool-reachable, and the pair sharing a hook tag where possible so
one sentence can frame both. Measured live: **138 such pairs across 25 silhouette
groups** (207 across 24 if silhouette names are normalised — the catalog spells the SB
Dunk three ways). 83 pairs include at least one Rare-or-better; 16 include a Legendary.
The reachability constraint is what does the cutting — 8,037 catalog-wide pairs fall to
586 at reachable and 138 at postable — but 138 is far above the ~20 floor where
repetition would become the format's failure mode. **The format is not pairing-starved.**

A second rule, *same collab, different era*, is available as a variant but is not
needed to keep the format alive and is left unbuilt until the first rule has shipped.

**Status: NOT WIRED.** `two_card_crop` exists in `research/composition.py`; the format
is not yet selectable. This section is the spec, not a description of live behaviour.

## 5. THE IMAGE BRIEF

**Status: NOT WIRED — `backdrop.scene_for()` reads `category` and `year` only, and has
never read the dossier.** This section is the target shape, held for E2/E5.

The intended rule: **the hook fact drives both the lead AND the scene.** One brief, so
the image and the text are about the same thing without repeating each other
(principle 5). Category becomes the fallback only when no story signal exists.

Two constraints that survive regardless of how the brief is built:
- Every `NEGATIVE_CONSTRAINT` stays structurally intact — no logos, no text, no
  identifiable people.
- **A story may not smuggle a brand mark into the prompt.** A Supreme shoe must not
  produce a box logo on a wall. The brief describes place, era, light and mood — never
  a brand's iconography, and never a named brand as set dressing.

## 6. WHAT THE WRITER IS HANDED

The payload is a whitelist (`writer.PAYLOAD_FIELDS`) and widening it raises an
assertion — deliberately. Spec facts are asserted out of `hook_facts` at build time. If
the facts given cannot support a line only this shoe could carry, the writer returns
`{"lead": null}` and that is a correct, expected output.

## 7. WHEN THIS FILE IS WRONG

If live behaviour contradicts this file, **this file is wrong until Ashton rules
otherwise** — do not change code to match a document. Note the divergence in
`memory.md` as a pending entry and raise it in the digest.
