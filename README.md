# cyphermarketer

X marketing agent for CYPHER, posting as **@appCYPHERR**.

**Scope contract:** `~/Documents/openclaw/CYPHER/CYPHER/CYPHER_MARKETING_AGENT_STRATEGY.md`
(locked 2026-08-19). **Voice + rails:** `~/.hermes/profiles/cyphermarketer/SOUL.md` (canonical).
Anything not ruled in the contract is a HALT-and-ask, not a judgement call.

## Layout

| Path | Role |
|---|---|
| `x_client.py` | X posting client — media upload + create tweet, OAuth 1.0a |
| `content/` | exact post texts, one file per post (byte-verbatim) |
| `ledger/posts.jsonl` | append-only record of every attempt / post / failure |
| `.env` | credentials, chmod 600, **never committed** (`.env.example` is the template) |

## Grounded decisions (build session 2026-08-19)

- **v2 endpoints only** — `POST /2/media/upload`, `POST /2/tweets`. The v1.1 media
  endpoint still answers 200 despite its 2025-06-09 sunset; it is treated as dead.
- **OAuth 1.0a for everything.** Probed live: `/2/media/upload` accepts it and takes a
  simple single-request multipart for images — no INIT/APPEND/FINALIZE. Public docs
  contradict each other on this point; the probe is the authority.
- **Hand-rolled signer**, no OAuth library (none installed on the mini; the surface is
  two endpoints). ⚠️ Query-string params must be folded into the signature base string;
  body params must not. A GET that skips this 401s.
- **Telegram uses a SIBLING bot token**, never CPA's. `getUpdates` is destructive
  per-token — a second poller on CPA's token permanently consumes CPA's approval
  decisions. Same chat is fine; same token is data loss.
- **Card art v1 = repo imagesets.** CPA's renderer binary may later be invoked
  read-only; **never run `swift build` in `cpa/CypherCardRenderer/`** — CPA's live
  proposal path depends on that built binary. No third `SneakerCardView` fork, ever.

## Rails enforced in code

- Explicit `--post` required; default is a dry run.
- Hard cap 4 posts / rolling 24h, counted from the ledger.
- Refuses text over X's 280 weighted chars (URLs count 23, emoji 2).
- Ledger is append-only: intent recorded *before* the network call, outcome after, so a
  crash mid-flight is still visible.
- Credentials load by path and are never logged, echoed, or written to the ledger.

## Usage

```sh
python3.12 x_client.py --text-file content/<post>.txt --image <path>          # dry run
python3.12 x_client.py --text-file content/<post>.txt --image <path> --post   # publish
```
