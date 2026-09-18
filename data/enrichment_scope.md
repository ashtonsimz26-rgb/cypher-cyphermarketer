# enrichment_scope.md — the 111, and what it would take

**Status: SCOPE ONLY. Nothing here is built. Approved in conversation 2026-09-14
and never written down; written 2026-09-17 with what was settled then plus what
has been measured since.**

## SEQUENCING — READ THIS BEFORE COSTING IT AGAIN

**This work goes AFTER the stem-and-trigger question. Do not run it first
because it is the cheapest item on the list.** (Ashton's ruling, 2026-09-17.)

At $1–4 and 2–3 hours it is cheap enough to run on a whim, and that is precisely
the risk. The diagnosis in `research/story.py` says the problem a reader
actually sees is **concentration** — 43% of keyed shoes land on two frames — and
enrichment does not touch it. Worse, the third of the 111 that would land is the
third that already had the most story, so it adds shoes to the same crowded
frames.

Cheapness is not priority. A cheap item run first still spends the sequencing
decision, and this one would leave the visible problem exactly where it was
while making the numbers look better.

> The failure this file fixes is not that the scope was wrong. It is that an
> approved scope lived only in a conversation, so the next session could neither
> execute it nor argue with it. A decision that exists in one person's memory is
> a decision the repo does not have.

---

## 1. THE TARGET

**111 shoes.** Pool-reachable, carrying a dossier, with **no hookable fact** —
so the scene path cannot see them and they draw the category backdrop.

They are not a tagging failure, and this was checked before scoping the work:

| | keyed group (139) | the 111 |
|---|---|---|
| GOAT `story_html` length | median 487 chars | **median 481 chars** |
| carries narrative language | 85% | **7%** |

GOAT wrote the same amount and described the product. Of the 86 narrative-shaped
sentences sitting in their non-hookable facts, **83 (97%) are one template** —
`"Built on the X silhouette, designed by Y"` — which fails the swap test by
construction. Retagging yields **3 shoes**. There is nothing to extract, so the
only route is a second source.

**The goal is one narrative sentence per shoe.** Not a dossier rewrite, not more
specs. One sentence that could open a post: a reason the shoe exists, a moment it
belongs to, a person who made a decision about it.

---

## 2. SOURCE PRECEDENCE

1. **Brand newsroom** — nike.com/news, adidas news, Jordan editorial
2. **Dated sneaker media** — a named publication with a visible publication date
3. **Press archive** — dated release announcements, brand PR distribution

**Never forums. Never listicles.** Both are unattributable by construction: a
forum post has no editorial standard and a listicle's claims are themselves
uncited, so verifying against one launders an unsourced claim into a sourced-
looking fact. The precedence is a *stop* list, not a preference — if a claim
appears only in tier 4, the shoe is skipped.

---

## 3. THE VERIFICATION CONTRACT

Every candidate fact passes through `research/verify.py:verify_fact` **against
the page it was extracted from**, and the caller branches on `outcome`, never on
`ok`:

| outcome | meaning | action |
|---|---|---|
| `found` | page loaded, every term present | accept, record the URL |
| `contradicted` | page loaded, a term absent | **retry with phrasing variants first** |
| `unverified` | page did not load — 404, timeout, DNS | **withhold, do not delete** |

Two rules from `verify.py`'s own header, restated because enrichment is exactly
where they get broken:

- **`unverified` is not evidence against a fact.** Treating it as a rail failure
  silently discards true facts and starves the pipeline. An unreachable source
  means *withheld pending a reachable source*, and the candidate stays on disk.
- **`contradicted` is phrasing-sensitive and is not proof of falsehood.** Term
  matching is order-preserving, so a variant phrasing returns `contradicted` on a
  page that plainly supports the claim. Retry variants before concluding
  anything; deleting on a single `contradicted` will delete true entries.

---

## 4. SHOE IDENTITY — THE TWO-SIGNAL GATE, AND THE COST DRIVER

The gate from `research/dossier.py` applies unchanged. A fact is about **this
shoe** only when both hold:

- **Signal 1 — SILHOUETTE.** The catalog silhouette appears in the source's name.
- **Signal 2 — an INDEPENDENT distinctive token.** Not a silhouette word, or it
  corroborates nothing.

`nike_air_foamposite_one_wu_tang` is why. A real GOAT story, a real source, the
gate satisfied, and the post still false — because nothing checked the source was
about the same shoe. Signal 2 excludes silhouette tokens precisely because
"foamposite" alone once satisfied it.

**This is the cost driver, not fetching.** Fetching 111 pages is minutes.
Proving each sentence is about *that colourway* — not the silhouette, not the OG,
not a different year of the same name — is the work. A 2019 retro carrying its
1995 original's story is the most likely failure mode here, and it is
`silhouette_lineage` content wearing a narrative coat.

---

## 5. WHAT AN LLM MAY AND MAY NOT DO

- **May: extract CANDIDATES.** Read a fetched page, propose a sentence, propose
  the terms to verify.
- **May not: decide.** `verify_fact` decides. A candidate is a claim until a page
  says otherwise.
- **Hallucinated candidates are logged and discarded, never retried.** A model
  that invents a sentence about the wrong shoe will invent it again on the same
  input; retrying is spend with no new information. Log it so the rate is
  visible.
- **`extracted_by: "llm"` is recorded permanently** on every fact it touched, and
  never rewritten to look human-sourced. A future session must be able to ask
  "which facts came from a model" and get an answer.

---

## 6. THE HOOK GATE

**No enriched fact becomes a `hook_candidate` without a verified source URL on
the fact itself.** Not a URL for the shoe, not a URL for the source site — the
page the sentence came from, stored on the fact, re-checkable later.

This closes the loop against the pattern this repo keeps finding: a rail that
cannot fail. A fact with no URL cannot be re-verified, so a check over it would
pass forever.

---

## 7. COST, HONESTLY

### Per shoe

| Step | Estimate | Notes |
|---|---|---|
| Search + fetch candidate pages | 20–40s | 2–4 pages, `HOST_DELAY` 0.5s, `TIMEOUT` 30 |
| LLM candidate extraction | 5–10s | one call per page, short output |
| `verify_fact` + phrasing retries | 10–30s | cached under `state/url_cache` |
| Identity gate + reject/accept | 5s | local |
| **Total** | **~1–1.5 min/shoe unattended** | ≈ **2–3 hours for 111** |

### Dollars

Model spend only; the sources are free to fetch.

| | |
|---|---|
| Per shoe | **$0.01–0.03** (2–4 short extraction calls) |
| **111 shoes** | **$1–4 total** |

For scale: one backdrop is $0.04. **The entire enrichment pass costs less than
100 backdrops.** Money is not the constraint here and should not be the reason
to defer it.

### Hit rate — my estimate, and it is not half

**I estimate 25–35 of 111, so roughly a third.** The basis, from the snapshots:

- **90 of 111 (81%) are 2020s releases.** Brand mix is Nike 40 / Jordan 37 /
  adidas 34 — mainline, not signature.
- **Only 10 of 111 (9%) have a collab in the product name.** A named collab
  almost always has a newsroom post; these are the reliable tier.
- The bulk are **seasonal colourways of mainline models** — a 2023 Dunk Low in a
  new colour, a Yeezy 450 in Stone Grey. **No newsroom wrote a story because
  there is no story.** The colour is the product decision.

So the tiers:

| Tier | Count | Expected yield |
|---|---|---|
| Named collab / signature | ~10 | 8–9 |
| Retro of a famous silhouette with its own OG moment | ~25 | 10–15, and **only if** the story is about *this* release — an OG story on a retro fails the identity gate and should |
| Seasonal mainline colourway | ~76 | 5–10, mostly incidental |

**If the honest answer were half, I would say half. It is about a third**, and
the third that lands is the third that already had the most story — which means
enrichment raises the keyed floor without touching the concentration problem
(43% of keyed shoes on two frames). Worth doing at $1–4. Not worth expecting it
to fix the sameness.

### What it does to the funnel

Reaching 30 of the 111 moves the hookable-fact population from 139 to ~169 of
332, and the *ceiling* on keyed shoes from 91 (65% of 139) to roughly 115.
**That is a real gain and it does not reach the 80% target**, which remains out
of reach for the reason already recorded in `research/story.py`: 48 shoes name
nothing locatable in time or space, and no source can add a moment that never
happened.
