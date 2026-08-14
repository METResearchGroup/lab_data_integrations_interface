# Step 4: Enrich DIDs with getRepo and classify validity

## Goal

For each discovered DID, load the account repo, compute stored profile fields and six month activity, overlay AppView follower counts, and mark whether the account is valid.

## Scope

The main caller is `analyze_dids(dids: list[str], workers: int) -> tuple[list[ProfileStats], dict]`, called from `run_experiment.py` after each discovery.

The work in this step is importing relay and public clients, calling `getRepo`, decoding activity counts, batching AppView profiles for followers and handles, applying validity rules, and returning rows plus analysis metrics.

Changing discovery algorithms, writing the final `RESULTS.md` narrative, and production ingestion are out of scope.

## Files to inspect

- [`experimentation/aoc_followers_backfill/client.py`](../../../experimentation/aoc_followers_backfill/client.py) for `create_relay_client` and `create_public_client`
- [`experimentation/aoc_followers_backfill/mst.py`](../../../experimentation/aoc_followers_backfill/mst.py) for `decode_repo`
- [`experimentation/aoc_followers_backfill/backfill.py`](../../../experimentation/aoc_followers_backfill/backfill.py) for date parsing and record type handling
- [`experiments/did_sync_experiment_2026_08_11/constants.py`](../../../experiments/did_sync_experiment_2026_08_11/constants.py)

## Files allowed to change

- `experiments/did_sync_experiment_2026_08_11/analyze.py`
- `experiments/did_sync_experiment_2026_08_11/constants.py` only for collection type constants if needed
- `tests/experiments/did_sync_experiment_2026_08_11/test_analyze.py`
- `experiments/did_sync_experiment_2026_08_11/run_experiment.py` only to wire `analyze_dids` if Step 5 has not done so yet

## Files forbidden to change

- `experimentation/aoc_followers_backfill/**` (import only; do not copy Merkle Search Tree code into the experiment package)
- `data_platform/**`
- Discovery algorithm bodies, except shared type imports

## Enrichment rules

1. For each DID, call `com.atproto.sync.get_repo` on the relay client from `create_relay_client()`.
2. Prefer importing `decode_repo` from `experimentation.aoc_followers_backfill.mst`. If memory use on large repos is too high during smoke testing, a streaming walk that counts without retaining every record is allowed. The streaming walk must reuse the same CID and Merkle Search Tree walk rules as `mst.py`. Document why the import alone was not enough.
3. Count lifetime follow records as `followees`.
4. Count lifetime post records as `posts`.
5. Inside the 183 day window, classify records as follows.
   - Original posts are posts with no `reply` field.
   - Replies are posts with a `reply` field.
   - Quotes are posts whose embed type is `app.bsky.embed.record` or `app.bsky.embed.recordWithMedia`.
   - Likes are `app.bsky.feed.like`.
   - Reposts are `app.bsky.feed.repost`.
   - Bookmarks or saves are bookmark collection records when present.
   - Missing collections count as zero.
6. `interactions_6m` equals likes plus reposts plus replies plus quotes plus bookmarks in the window. A quote that is also an original post counts for both the original post rule and the interaction total.
7. Batch AppView `get_profiles` for follower counts, handles, and created dates. Follower count must come from AppView because a user's own repo does not contain inbound follower edges.
8. `account_created_at` prefers the AppView created date when present. Otherwise use the profile record `createdAt` from the repo. Otherwise use the earliest record timestamp seen while decoding.
9. An account is valid only when all four rules pass. Followers must be at least 10. Followees must be at least 10. Original posts in the window must be at least 20. Interactions in the window must be at least 20.
10. On `getRepo` failure, keep the DID row with `error` set and `valid` false or null, then continue. Count rate limited failures in analysis metrics.

Analysis metrics in the returned dict must include at least these fields:

- `getrepo_request_count`
- `getrepo_error_count`
- `getrepo_rate_limit_event_count`
- `getrepo_runtime_seconds`
- `appview_profile_request_count`

## Unit tests required

Use fixtures of decoded record dicts or tiny fake archive builders. Do not hit the live relay in unit tests.

1. Validity is true when all four thresholds are met.
2. Validity is false with an explicit reason when original posts in the window are below 20.
3. Quote posts increment both original posts (when not a reply) and interactions.
4. Reply posts do not increment original posts, and do increment interactions.
5. Missing bookmark records do not raise, and contribute zero.
6. AppView follower count overlays onto the row when provided by a mocked profile batch.

## Pass

- `PYTHONPATH=. uv run pytest tests/experiments/did_sync_experiment_2026_08_11/test_analyze.py -q` exits 0.
- A fixture account with 10 followers, 10 followees, 20 original posts in the window, and 20 likes in the window is marked valid.
- Analyze code imports clients from `experimentation.aoc_followers_backfill.client`.

## Fail

- Using AppView alone for six month likes or bookmarks, because those fields are not available that way for an arbitrary user.
- Copying a second Merkle Search Tree implementation into the experiment without documenting why import failed.
- Stopping the whole batch when one DID fails.
