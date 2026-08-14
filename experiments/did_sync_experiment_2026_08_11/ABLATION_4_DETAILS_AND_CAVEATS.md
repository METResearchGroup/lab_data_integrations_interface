# Ablation 4 details and caveats

Ablation 4 samples Bluesky account IDs (DIDs) via relay
`com.atproto.sync.listRepos` on `bsky.network`, then scores them with the same
validity rules as the other ablations.

In the authoritative run, the first page of that listing (`limit=1000`, no
cursor) produced **475 / 1000** valid accounts (47.5%), with **0** getRepo
errors and **0** rate limits. That is higher than AOC follower BFS (183) and
far higher than either PLC arm (1 each).

This note explains what that result means, and what bias it does **not** remove.

## Validity criteria (shared across ablations)

An account is valid only if all of the following hold:

1. At least 10 followers (AppView `followersCount`)
2. At least 10 followees (`app.bsky.graph.follow` via `getRepo`)
3. At least 20 original posts in the last ~183 days
4. At least 20 interactions in that window (like + bookmark/save + quote +
   repost + reply)

## What `listRepos` actually is

`com.atproto.sync.listRepos` on `bsky.network` is the relay’s inventory of
repos **it currently knows about**. It is not:

- a random sample of all Bluesky accounts
- PLC chronology (registration / identity ops)
- a social-graph neighborhood

On this relay, the cursor is a **sequentially increasing integer ID**. No
cursor means start at the lowest IDs. Ablation 4 took the first page
(`limit=1000`) from that start, so it effectively sampled roughly
**relay-internal IDs 1–1000**.

## Why this slice looked “more valid”

Two different effects show up in the data.

### Versus PLC

`listRepos` almost only returns accounts the relay already tracks as repos, so
`getRepo` worked for **1000 / 1000** in Ablation 4. PLC samples identity-log
DIDs, many of which were unreachable, taken down, or not found (906 and 828
fetch failures in the recent and older PLC arms). An account cannot pass
validity if its repo cannot be loaded.

### Versus AOC followers (both fully fetchable)

Among fetchable accounts, Ablation 4 cleared activity thresholds much more
often than AOC followers:

| Criterion | listRepos (Ablation 4) | AOC followers (Ablation 2) |
|---|---:|---:|
| followers ≥ 10 | 98.7% | 88.7% |
| followees ≥ 10 | 97.1% | 92.6% |
| original posts ≥ 20 | **50.4%** | **19.4%** |
| interactions ≥ 20 | **81.4%** | **47.7%** |

Medians tell the same story: listRepos median original posts ≈ **20** and
interactions ≈ **2238**; AOC followers median original posts ≈ **0** and
interactions ≈ **16**.

So the main gap versus AOC is **recent posting / engagement**, not merely
graph size. AOC’s follower list includes many low-activity lurkers. Relay
`listRepos` page 1 skewed toward accounts that already clear the activity bar.

## Bias induced by this sampling method

### Bias 1: Who even appears in `listRepos`

This is the big structural filter, before page order matters.

The relay only returns accounts in **its** index. Community discussion of
`bsky.network` notes the current relay instance is relatively new (~Nov 2024)
and `listRepos` appears to cover far fewer accounts than total PLC identities
(on the order of ~18M listed vs ~28M+ accounts). Plausible reasons include
accounts seen/active since that relay stood up, incomplete backfill, and
similar indexing gaps.

So Ablation 4 is already conditioned on:

- “known to this relay”
- usually “has a repo the relay can point at”

That alone helps explain **0 / 1000 getRepo failures** versus PLC’s hundreds of
`pds_unreachable` / `RepoNotFound` / `RepoTakendown` outcomes. PLC samples
identity-ledger DIDs; `listRepos` samples “repos this relay already tracks.”

That is a **survivorship / indexing bias**: dead, never-synced, or
never-seen-by-this-relay accounts are underrepresented.

### Bias 2: “Start of enumeration” = earliest relay IDs

Because the cursor is a sequential internal ID, “first page” means **earliest
rows in the relay’s repo table**, not “most popular” and not “random.”

Those early IDs are whoever got assigned low IDs when the relay built or filled
that table—often accounts present early in that relay’s life or ingested
first. That is **correlated with being established enough to be indexed
early**, and in our run those accounts were also highly active.

Important nuance: we **did not** re-score a later page with the same validity
pipeline. A quick live check of later cursors (`200000`, `2000000`) still
showed `active: true` and no status flags in small samples—so “early page vs
late page” may not differ much on the crude `active` flag. The strong activity
skew we measured is firmly established for **page 1**, and only hypothesized to
weaken or change deeper in the list.

So “first page skewed toward established, still-synced repos” is best read as:

1. **Hard fact:** selected from relay inventory + earliest IDs.
2. **Measured fact:** that slice cleared activity thresholds often.
3. **Inference:** earliest relay IDs are a non-random, likely
   older/more-established-looking cohort; we should not assume the same 47.5%
   validity deeper in the cursor space without testing.

### Bias 3: What this does to the experiment’s conclusion

| Comparison | What the bias does |
|---|---|
| vs PLC | Inflates `listRepos` yield by excluding many unfetchable / brand-new / broken hosts that PLC includes. |
| vs AOC followers | Different bias: AOC includes lurkers who follow a celebrity; `listRepos` page 1 does not. That helps `listRepos` on posting/interaction thresholds. |
| as “network quality” | Overstates how good a **generic** DID sample is. 47.5% is “quality of early relay inventory,” not “quality of a random Bluesky user.” |

## Practical takeaway

Ablation 4 answers:

> If we seed from the first chunk of this relay’s `listRepos`, how many pass
> our activity bar?

It does **not** answer:

> What fraction of all Bluesky accounts would pass?

To reduce that bias, useful follow-ups include:

- random cursors across the ID range
- stratified pages (early / mid / late)
- a true random sample from a known complete DID set

then re-run the same validity rules.
