# context.md — the stable facts

**Rank 4 of 5.** Precedence: `SOUL.md` > `rails.py` > `instructions.md` > **`context.md`** >
`memory.md`. This file holds what is TRUE and SLOW-MOVING. It does not tell you how to
write a post — that is `instructions.md`. It does not tell you what has happened —
that is `memory.md`. If a fact here contradicts `SOUL.md`, `SOUL.md` wins and this
file is wrong.

Everything in this file is checkable against the live catalog or the repo. When a
number here drifts from the database, the database is right and this file is stale —
fix it, and note the correction in `memory.md`.

---

## 1. WHAT CYPHER IS

An iOS sneaker trading-card app — *CYPHER — Unlock the Vault*. Free on the App Store,
built solo by Ashton Sims. Users open packs, collect cards of real sneakers, complete
sets, and trade with each other.

Three phases: **cards** (shipped), **AI authentication** (next), **marketplace**
(after). The account is marketing the cards app that exists today, never the roadmap.

The cards depict real sneakers under nominative use. **They are collectibles for fun.**
They are not investments, they are not redeemable for money, and no post may imply
otherwise. This is not a tone preference — it is App Store 5.3 and state-law exposure,
and it is why `rails.py` fails closed on every price claim.

**The one distinction that must never blur:** resale prices in a post describe the
REAL SNEAKER's market. The card on screen renders an `EST. VALUE $N` field that tracks
that real pair. A post that lets the figure read as the CARD's worth is the exact
ambiguity the locked decision rejects, and `rails.check_draft` blocks it when the
composition leaves the value row in frame.

## 2. THE TIER LADDER

Six tiers, and they are a real enum in the database (`enumsortorder` 1–6):

| tier | catalog rows | reachable | what it means to a user |
|---|---:|---:|---|
| Common | 863 | 154 | the body of a pack |
| Uncommon | 1,190 | 128 | the second card |
| Rare | 531 | 80 | the one worth stopping on |
| Legendary | 188 | 12 | capped supply, serial-numbered |
| GRAIL | 52 | **0** | ceremony or nothing; 14 carry caps of 1,000–10,000 |
| HOLY GRAIL | 17 | **0** | the rarest thing in the app; 4 carry caps of 100–1,000 |

**Legendary, GRAIL and HOLY GRAIL are the capped-supply tiers and carry a serial
number** on the card face (`HeritageDetailSheet.serialNumberIfCapped`). Not every row
in those tiers has a `serial_caps` entry yet — 40 of 188 Legendary, 14 of 52 GRAIL,
4 of 17 HOLY GRAIL do. Serial numbers are the
emotional engine of the whole product — a low serial on a capped card is the thing
people screenshot.

## 3. WHAT THE AGENT CAN ACTUALLY POST ABOUT

This is the section that constrains everything, and the one most likely to go stale.

**Reachability** (`daily_digest.REACHABLE_CTE`) is the union of `welcome_pool`,
`daily_pool`, `pack_pool` rows with an explicit rarity, and `pack_pool` rows whose
pack type has `pack_rarity_weights.weight > 0` for that card's tier. Identity is
**(image_name, rarity)** — the same shoe can exist at three tiers and be reachable at
only one of them.

A shoe is **postable** when it is reachable AND has a dossier AND that dossier is
proposable AND it carries a non-designer narrative hook. Live, measured 2026-09-16:

| tier | reachable | has dossier | proposable | **postable** |
|---|---:|---:|---:|---:|
| Legendary | 12 | 7 | 7 | **6** |
| Rare | 80 | 68 | 66 | **48** |
| Uncommon | 128 | 103 | 101 | **55** |
| Common | 154 | 112 | 112 | **41** |
| GRAIL | 0 | — | — | **0** |
| HOLY GRAIL | 0 | — | — | **0** |
| | | | | **150 rows / 135 distinct shoes** |

**The six postable Legendary shoes are four stories:** `yeezy750_og`,
`nike_air_force_1_low_lemonade`, `sb_dunk_low_gratefuldead_green` and
`sb_dunk_low_gratefuldead_yellow` (one story), `aj1_travisscott_mocha` and
`sb_dunk_low_travisscott` (one story). This is why the top tier is treated, not
repeated — see `instructions.md` § TIER-AWARE TREATMENT.

**No GRAIL or HOLY GRAIL is pullable.** No `pack_rarity_weights` row exists for either
tier, for any of the nine pack types — the weight table stops at Legendary. Three of
the 69 are nonetheless **obtainable**, by set completion, and every card those three
sets require is reachable:

| set | reward | tier | requires |
|---|---|---|---|
| Nike SB x Grateful Dead | `sb_dunk_low_gratefuldead_orange` | GRAIL | green + yellow |
| Nike SB x Staple | `sb_dunk_low_staple_nyc_pigeon` | HOLY GRAIL | black + purple + panda pigeon |
| Nike x Jordan 4 SB | `aj4_sb_varsity_red` | GRAIL | navy + pine green |

`claimed_set_rewards` holds five claims, so the ceremony path is live and exercised.
**All three are postable as of 2026-09-16**, on the earn route only: SOUL gained a
HARD RULE distinguishing PULLABLE from EARNABLE, and `rails.obtainability()` proves the
set path per card. A post about them must state the route — "complete the set" — and
may never imply a pack pull.

## 4. WHO THE AUDIENCE IS

Sneaker Twitter. People who already know what a Dunk is, who recognise a style code,
who will correct a wrong year in the replies within four minutes. They do not need
"the Swoosh (the Nike logo)" explained and they resent being explained to.

They are also, structurally, not looking for an app. Nobody opens X wanting to
download something. They are looking for something worth sending to a friend. The
post has to be that first and an advert second, or it is neither.

## 5. WHAT THE ACCOUNT IS TRYING TO BECOME

**THE GOAL LIVES IN `SOUL.md`, OPENING SECTION — not here.** It was moved there on
2026-09-16 (Ashton's ruling) because `context.md` is rank 4 of 5 and a goal filed one
rank above the evidence log is a goal nothing enforces. `SOUL.md` is where a rail can
cite it. Read it there; this section is the pointer and the standing numbers, not the
law.

`@appCYPHERR`. Today it is an account that posts accurate, competent sneaker facts
that nobody has ever shared. **The agent's own record is 4 posts (`kind == "content"`
in `ledger/metrics.jsonl`) — 54 impressions, 3 likes, zero reposts, zero replies, zero
quotes, zero bookmarks**; the account's lifetime totals of **204 impressions and 8
likes across 22 rows are a different population**, because 17 of those rows are
Ashton's manual replies and 1 is the v1 acceptance-test announcement. **Citation rule
(`SOUL.md`): any use of 204/8 must carry the 4-of-22 split in the same sentence, never
in a footnote.** n=4 is not a sample.

The target is not "prettier". It is an account a sneakerhead **replies to, bookmarks,
or quotes** — and the first of any of those is the milestone that matters, because the
count is currently zero and polish has had a year of chances. That ordering expires
when the first one lands, and Ashton sets what follows — see `SOUL.md` § THE GOAL.

Two things follow, and they are in tension on purpose:
- A post that invites a reply outranks a post that delivers a fact, all else equal.
- The agent may learn the **shape** of what works. It may never choose a **subject**
  because the subject is hot. (v1.3 ruling; unchanged.)

## 6. CONVERSION MECHANICS

The App Store link and the referral loop ("give a pack, get a pack" — both sides
unlock a Referral Pack) are the conversion tools. They are used **naturally and not in
every post**. The attribution sentence is appended by `compose`, not written by the
writer — see `research/writer.py:FORMAT_CONTRACT`.

## 7. THE ACCOUNT'S OWN RAILS, IN ONE LINE EACH

Full text is `SOUL.md`; this is the index, not the law.

- No real-world monetary value, ever. No gambling language, ever.
- No competitor named. No politics, tragedy, drama or controversy.
- No reply or DM to an individual user — absolute, all phases.
- Brand/media replies are DRAFT-ONLY and never graduate, at any autonomy phase.
- No claim of partnership or endorsement with any brand.
- Max 4 posts / 24h. No delete-and-repost.
- Uncertain? Do not post. Queue it with the uncertainty stated.
- **Current autonomy phase: PHASE 1.** Draft everything; Ashton approves; post only
  what he approves. Phase 2 additionally excludes generated-backdrop content until a
  backdrop inspection mechanism exists.
