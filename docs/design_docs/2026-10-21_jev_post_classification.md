<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

- [Proposal: classify Bluesky posts with Jev](#proposal-classify-bluesky-posts-with-jev)
  - [Background](#background)
  - [Goal](#goal)
    - [Questions on research goals](#questions-on-research-goals)
  - [Starter attributes](#starter-attributes)
    - [Questions on attributes](#questions-on-attributes)
  - [Where scoring fits](#where-scoring-fits)
    - [Questions on scope of the data](#questions-on-scope-of-the-data)
    - [Questions on architecture](#questions-on-architecture)
  - [Validation](#validation)
    - [Questions on validation](#questions-on-validation)
  - [Cost, latency, and how much to score](#cost-latency-and-how-much-to-score)
    - [Questions on cost](#questions-on-cost)
    - [Questions on timeline](#questions-on-timeline)
  - [Risks](#risks)
  - [Alternatives](#alternatives)
  - [Out of scope](#out-of-scope)
  - [Sources](#sources)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Proposal: classify Bluesky posts with Jev

The document is a first-pass proposal for you to edit. A batch job would read posts that are already in Iceberg and call Jev once per post. The job would write labels to a separate table keyed by post URI, model id, and question set. You can filter on those labels in the search box once the SQL generator joins the label table and the 10 GB scan check prices both sides. The change is the document only.

## Background

The repo stores Bluesky posts, likes, reposts, and follows as Iceberg tables in the Glue database `bluesky_raw`, under `s3://lab-data-integrations-interface/bluesky/raw/`. Jetstream writes creates with `created_at` on or after 2026-08-01. The ingester drops every commit that is not a create, so a stored post is the original text. A later edit or delete on the network does not change the row. The process flushes its buffers at 2 GB or at 30 minutes, and it advances the cursor only after the flush commits.

The backfill app writes earlier repos as Parquet under `landing/bluesky/backfill/`, for records dated 2022-11-17 through 2026-08-07. `docs/design_docs/2026-09-19_bluesky_backfill_merge.md` describes moving those files into `bluesky_raw`, and the Terraform in this repo does not do it yet. A label job for history waits for the merge, or reads the landing files.

A natural-language question becomes one `QueryIntent`. The intent has a record type, a column list, and a date range. The columns the intent may name come from the Arrow schemas in code. SQL then reads one table, `bluesky_raw.<record type>`, and filters on `created_at`. Athena runs the query, and the CSV is emailed. The scan check refuses a planned scan over 10 GB before Athena starts.

The query path has no label columns. `feature_generation/perspective_api/` can still call Perspective, and the August 2026 experiment wrote local Parquet for part of two days. PR #215 removed the `data_platform/` feature CSVs and the batch engine around them. A new label has to land in Iceberg before the search box can return it.

Jev is TypeSafe's System One model. You send a post and one or more typed questions, and one call returns a structured answer per question. Choice, Score, and Noul are the text primitives.

- A Choice picks one option from a list you supply. The answer is the option, a probability for every option, and a confidence.
- A Score places the post on ordered levels you write, and the value may fall between two levels. The answer includes the score, a probability per level, and a confidence.
- A Noul is the probability that a yes/no question is yes. There is no separate confidence, because the single number already says how sure the yes is.

Questions in one call are judged independently against the same post. A checklist belongs in one request, and SQL can combine the columns afterward. TypeSafe's docs, read on 2026-10-21, price input at $0.042 per million tokens and charge nothing for output. The model page lists `jev-1.14.0` and `jev-1.13.0` at $0.042 per million tokens. Each request is limited to 64k tokens. The alias `jev-latest` pointed at `jev-1.13.0`, and `jev-preview` pointed at `jev-1.14.0`. Every response includes the versioned model id that answered.

Your 2026-09-19 writeup compared Jev with Perspective and several Bedrock models on 1,000 posts from a private set of 26,000 Twitter moral outrage labels. Jev's F1 was 0.7323, accuracy 0.717, precision 0.6272, and recall 0.8795. Perspective's F1 was 0.7253, with precision 0.7816 and recall 0.6765. Jev latency was 130.9 ms at the median (p50), 186.6 ms at the 90th percentile (p90), and 274.4 ms at the 99th percentile (p99). You also found Jev's probabilities less bunched than Perspective's. Perspective's scores pile up near 0, 1/3, 2/3, and 1, because three annotators vote. The writeup says Perspective is scheduled to shut down at the end of 2026. The writeup's cost cell for Jev is $0. The text says input tokens were not split out from the 374,632 total tokens. The $0 cell is not a bill you can reuse.

The API key is already in AWS Secrets Manager in us-east-2, which is the region in `lib/aws/constants.py`, under the name `jev-typesafe-api-key`. A job should read the secret at startup. The value stays out of git and out of logs.

## Goal

Researchers should be able to ask for posts by social label, and to download the posts with the probability still on the row. Toxicity is the first label to add. The starter set adds the other attributes you named. Each question stays small enough to check against a person, or against a label you already trust.

The first milestone is a checked sample, then one day of labels you can query in Athena by writing SQL. Putting the same columns in the natural-language path is a later milestone. The join and the scan check both have to change, and both should wait until you trust the probabilities.

### Questions on research goals

1. Who is the first reader of the labels, you for a paper, or any person who can use the query UI?
2. Which artifact do you want first, a methods comparison of Jev and Perspective on Bluesky, a table of labels, or labels inside the search box?
3. Which questions have to return rows in the first version? Candidates you can accept or replace:
   - toxic posts per day over a week you name
   - moral outrage split by political stance
   - posts with hostility above a threshold in a date range you name
4. Do you need one row per post in the CSV, with the probability on the row, or are daily counts enough for the first paper?
5. Is Jev the replacement for Perspective, or a second label source you want beside Perspective until the shutdown?
6. Are toxicity and hostility on a named account acceptable for anyone who can query posts today, or do those columns need a smaller audience than `bluesky_raw.posts`?

## Starter attributes

Each attribute below is one question in a single Jev call. The state is the post text. SQL combines attributes after the fact, so "hostile and political" is a `WHERE` clause on two columns. One combined question would mix two judgments into one number, and changing the mix would mean a new score of every post.

| Attribute | Primitive | What you store | Why it is in the starter set |
| --- | --- | --- | --- |
| Toxicity | Noul | Probability the post is toxic, column `prob_toxic` | The search case you named, and the Perspective column the August Parquet already has |
| Moral outrage | Noul | Probability the post expresses moral outrage, column `prob_moral_outrage` | The one attribute where you already measured Jev, on the Twitter set |
| Political content | Noul | Probability the post discusses politics, elections, or public policy | Separate from stance, so a sports post is not assigned a side |
| Political stance | Choice | One of `left`, `right`, `unclear`, `not_political`, plus the probability of each option and the confidence | The old mirrorview filter kept `left` and `right`. `unclear` and `not_political` cover posts with no clear side |
| Hostility | Noul | Probability the post is hostile toward a person or group | You asked for hostility. It overlaps toxicity, and attribute question 4 asks whether the first version keeps both |
| Constructiveness | Noul | Probability the post gives reasons, evidence, or a workable point, column `prob_constructive` | The Perspective client in this repo copies the reasoning score onto `prob_constructive`. The same call can return it next to toxicity |
| Primary emotion | Choice | One of `anger`, `fear`, `sadness`, `joy`, `disgust`, `neutral`, plus probabilities and confidence | One emotion label. A Score of intensity per emotion can wait until the Choice is too coarse |

Binary attributes are Nouls because you want a probability SQL can threshold. Your writeup compared probabilities. A Score is a position on levels you write. A middle score does not mean "probably toxic". Add a Score later if you want named levels such as mild, harsh, and extreme.

Leave the rest of the Perspective catalog for a later question set. The deferred list covers severe toxicity, insult, identity attack, threat, profanity, spam, and the experimental scores (affinity, compassion, curiosity, nuance, personal story, respect, alienation, fearmongering, generalization, scapegoating, flirtation, sexually explicit). Each added question needs its own wording and its own check. Adding one changes the question set id, so old rows keep the meaning they had when you scored them.

The wording is part of the label. A wording change is a new question set, even when the column is still called `prob_toxic`. You should write the instructions and the yes/no criteria, or sign them, before any run past the validation sample. TypeSafe does not send the question id to the model, so the instruction text has to carry the full definition. Where a column name matches Perspective (`prob_toxic`, `prob_moral_outrage`, `prob_constructive`), keep the name, so the August Parquet joins without a rename.

### Questions on attributes

1. Confirm the starter set, or name the attributes to drop before any sample is scored.
2. For toxicity, do you want one Noul, or the Perspective split in the first call (toxic, severe, insult, identity attack, threat, profanity)?
3. For political stance, are `left`, `right`, `unclear`, and `not_political` the right options? Add `center` only if you can say what a reader should treat as center on a post.
4. Do you want hostility in the first version? If yes, write the sentence that separates hostility from toxicity, so the two Nouls are different questions.
5. For emotion, is one Choice of the primary emotion enough? If you want intensity, name the emotions that get a Score, and name the levels on each Score.
6. Which missing Perspective attributes does a current project still need? Name them, or say none.
7. Should any starter attribute be a Score rather than a Noul or a Choice? Name the attribute and the levels.
8. Who writes the instruction text and the yes/no criteria, and who has to approve the text before a question set is scored past the sample?

## Where scoring fits

Score posts that are already committed in `bluesky_raw.posts`. A Jev call inside the Jetstream process would hold the cursor until the calls finished, and a flush can be 2 GB or 30 minutes of posts, likes, reposts, and follows together. The scoring job should read after the commit and write a different table.

Use `bluesky_raw.posts` as the only input for the Jetstream era, which is `created_at` on or after 2026-08-01. The August experiment counted 3,124,215 posts on 2026-08-09 and 3,463,641 posts on 2026-08-10 in that table. History before the cutoff still sits in landing Parquet. Score history after the merge is built, so the job has one input and the same `uri` and `created_at` the search path already uses. A second run for the same `uri`, `model_id`, and `question_set_id` should not call Jev again. Saturday dedup on the raw tables masks duplicate URIs for the last 21 days. A duplicate uri outside that window, or between Saturday runs, should still cost one Jev call.

Leave `POST_SCHEMA` alone. Bootstrap creates Iceberg tables and does not alter a table that already exists. Label columns will change every time the question set changes. Raw posts stay a record of creates.

The label table, with the name open to you:

- Glue database `bluesky_features`, table `post_classifications`.
- Location `s3://lab-data-integrations-interface/bluesky/features/post_classifications`.
- A separate database keeps the raw maintenance state machine, daily `OPTIMIZE` plus weekly dedup and `VACUUM`, from compacting label files on the raw schedule. Add maintenance for the label table once the files are large enough to need it.
- Partition by day of the post's `created_at`, the same transform as `bluesky_raw.posts`, so a one-day query prunes both sides.
- One row per attempt for a `(uri, model_id, question_set_id)`, whether the call succeeded or failed.
- Columns to plan on: `uri`, `created_at`, `cid`, `model_id`, `question_set_id`, `scored_at`, `input_tokens`, a success flag, an error string on failure, one float per Noul, and for each Choice the chosen value, the confidence, and the probability of every option.
- Store the versioned id from the response, such as `jev-1.14.0`, including when the request sent an alias.
- `question_set_id` is a short name plus a hash of the instructions and criteria. The wording should be recoverable from git by that id, so a paper can cite the text that produced the column.
- Skip the call when a success row already exists for that triple. Retry a failure row on the next run. Record a blank `text` as a skip, so an empty post is not sent on every run.
- Send the post text as the whole state. Leave `langs` and `reply_parent_uri` out of the state in the first version. The label then means the text alone, which is what Perspective saw. Adding reply context later is a new question set, because the answers will move.

Freshness is the schedule you pick. Jev's 130.9 ms p50 is the time for one post. An hourly or daily job over posts that lack a success row is enough for a research query. Matching the firehose within a second would be a separate requirement.

The natural-language path cannot see the new table. `extract_intent` lists columns from the four Arrow schemas. `generate_sql` emits a select from `bluesky_raw.<record type>` with a `created_at` filter. The posts schema has no `prob_toxic` column, and the generator does not emit a join.

When you want the search box to filter on a label, the SQL joins `bluesky_raw.posts` to `bluesky_features.post_classifications` on `uri`. The join keeps the pinned `model_id` and `question_set_id`. It also applies the same `created_at` bounds on both tables, so both sides prune. The 10 GB check plans a single table from Iceberg file metadata. The check has to price both sides of the join before a label question is allowed through. A question such as "toxic posts in 2026" can read much more than the cap if the check ignores the join. The check can also refuse a join it does not know how to measure. Keep thresholds in SQL, for example `prob_toxic > 0.7`. A threshold change does not write new rows. A wording change does, under a new `question_set_id`.

Athena, with SQL you write, is the right first milestone. The search box follows after the sample looks right.

### Questions on scope of the data

1. Score every create in `bluesky_raw.posts`, including replies and posts with a quote or other embed, or only rows whose `reply_parent_uri` is null?
2. Which languages are in scope? Pick one: `langs` contains `en`, every language, or `en` plus posts whose `langs` is missing. TypeSafe's docs say English is where accuracy is currently best, and other languages need a check on your own posts.
3. What should the job do with a blank or very short `text`? Skip it, or send it?
4. A post can have an `embed_type` and little or no text, and the table does not store the image or the quoted record. Score the text you have, or skip rows where `text` is empty?
5. Which corpus is the first scored table? Pick one: a single recent day, every Jetstream post after a date you name, a backfill window you name, or everything back to 2022-11-17.
6. If you want history, name the start date and the end date. One Iceberg day is the natural unit, because of the partition. Scoring history also waits on the backfill merge, unless you explicitly want the job to read landing Parquet.
7. Score every post in the corpus, or a sample? If a sample, give the rate and how to split it, for example by day, by language, or by a cheap prefilter.

### Questions on architecture

1. Is a batch job over committed rows in `bluesky_raw.posts` the placement you want?
2. How fresh do the labels need to be for the first reader: the next day, later the same day, or within an hour of the post landing?
3. Do you accept a separate table, `bluesky_features.post_classifications`, keyed by `uri`, `model_id`, and `question_set_id`? Columns on `bluesky_raw.posts` mean every new question set alters the table the ingester writes.
4. Is a new Glue database acceptable, so raw maintenance does not compact the label files?
5. Partition the label rows by the post's `created_at` day, so they prune with the posts they join to?
6. For a Choice, store the probability of every option, or only the winning option and its confidence?
7. Store the raw Jev response, or only the columns a query will read? The response helps a later check of the wording. It also widens every row.
8. On a failed call, write a failure row and retry it on the next run, or leave the uri absent until someone looks?
9. For the first version of search, is Athena SQL that you write enough? If the search box must filter on a label in the first version, the join and the 10 GB check land in the same change.
10. Where should the job run once it is past a manual script: Step Functions, on the pattern of table maintenance, or a Railway worker?
11. Confirm the job should read `jev-typesafe-api-key` from Secrets Manager in us-east-2. Name a different account or region if the key should move.

## Validation

Check Jev on posts you can already judge, and on a Bluesky slice a person labels, before you pay for a full day.

Your Twitter moral outrage result is the baseline the wording has to meet. On the sample of 1,000 posts, Jev's F1 was 0.7323, recall 0.8795, and precision 0.6272. Score a changed wording for moral outrage on the same sample, or on a fresh draw from the 26,000, before you trust the wording on Bluesky. The posts are Twitter. A match means the new text still does what the September text did. The Twitter match does not measure Bluesky.

The August experiment already has Perspective scores for posts in `bluesky_raw.posts`. There are 124,748 successful labels on 2026-08-09, and 1,690,436 successful labels on 2026-08-10, as Parquet under `experiments/perspective_api_labeling_2026_08_11/`. Pair Jev and Perspective on the shared column names for a sample of those URIs. Agreement tells you whether the two scores move together. Agreement does not tell you which score matches a person. Perspective is a comparison point here, and your writeup documents the bunching near 0, 1/3, 2/3, and 1. The experiment's download scripts import `data_platform/`. PR #215 removed that package, so use the Parquet already in the repo.

Hand labels on Bluesky are the check that can stop you from scoring a full day. Draw the labels across the probability range, including posts Jev places near 0.5. A sample of only easy posts will overstate how often Jev matches a person on the firehose. Your writeup checked moral outrage by eye. High probabilities looked unambiguous to you, and close probabilities were posts you were also unsure about. For toxicity and moral outrage, use a count you pick and a second reader. A reliability diagram plots the predicted probability against the share of posts the readers marked yes. Validation question 4 asks whether you want one diagram per attribute before any threshold is written down.

Store the probability. The Perspective client writes a 0 or a 1 when the score crosses 0.5. The research table should keep the float, so a threshold can change in SQL. Choose the threshold per attribute on a slice you did not use to tune the wording. Write the threshold next to the question set, and apply the threshold in the query. For a Noul, a filter should act on values near 0 and near 1. Values in the middle stay numbers, with no boolean, so a paper can choose the cutoff later. For a Choice, low confidence is a reason to keep the second-best probability on the row.

When the wording or the pinned model changes, append rows under the new `question_set_id` or `model_id`. Old rows stay, so a paper can name the pair it used. Promoting a pair means changing the id the query path pins. Promotion leaves the previous rows in the table. Re-score a corpus when you want every uri present under the new id. A partial re-score makes "newest row per uri" mix two definitions, so the query path should pin an id.

Send a pinned model id in the request. A request that sends `jev-latest` can change answers when TypeSafe moves the alias, with no commit in this repo. Store the versioned id the response returns even when the request was pinned, so the row records what actually ran.

### Questions on validation

1. May the private set of 26,000 Twitter posts be the moral outrage benchmark here, with F1 0.7323 as the number a new wording has to meet?
2. How many Bluesky posts will you label by hand, for which attributes, and who is the second reader?
3. What result is good enough to score a full day? Name the metric and the cutoff for toxicity, and the same for moral outrage. Your writeup treated recall and F1 as the headline numbers, and the sample's precision was 0.6272.
4. Do you want a reliability diagram per attribute, on the hand labels, before any threshold is written down?
5. What should a probability between 0.3 and 0.7 mean in a filtered query: keep the row and the number, drop the row from the filter, or send the post to a person?
6. When the wording changes, keep the old rows under the old id, or delete them?
7. Which model id should the first table pin, `jev-1.13.0` or `jev-1.14.0`? On 2026-10-21 the docs had `jev-latest` on 1.13.0 and `jev-preview` on 1.14.0.
8. How large a drop in F1, or how far off a reliability curve, forces you to re-score posts you already paid for?

## Cost, latency, and how much to score

Jev bills input tokens at $0.042 per million, and output tokens are free. The September writeup's $0 cell is not usable, because the 374,632 tokens on 1,000 posts were not split into input and output. If all 374,632 tokens had been input, the bill would have been about $0.016. Measure input tokens per post on the first call this repo makes, with the real starter questions. Until you have the measurement, the dollars below assume 800 input tokens per post, for the text plus the starter questions in one call. One post at 800 tokens is about $0.000034.

Apply the assumption to the Athena counts from the August experiment:

- 2026-08-09, 3,124,215 posts, about $105.
- 2026-08-10, 3,463,641 posts, about $116.
- A sample of 10,000 posts, about $0.34.

Halve the dollars if the measured prompt is 400 tokens, and double them if it is 1,600. A filter that keeps only posts whose `langs` contains `en` multiplies the bill by the English share. The share is not measured in the repo.

A backfill price needs a row count from Athena or from the landing files. The August daily rate may not match earlier months, and the total from 2022-11-17 is not measured here. Count the days you intend to score, then multiply.

The dedup SQL in `terraform/bluesky_ingestion_jetstream/maintenance.tf` says an unbounded scan is 213 million rows, and the comment does not name the table. If those rows are posts, 213 million times 800 tokens at $0.042 per million tokens is about $7,160. Treat 213 million as the comment's figure, and recount in Athena before you approve a full scan of `bluesky_raw.posts`.

Latency in your writeup, on the one-question task, was 130.9 ms at p50 and 274.4 ms at p99. TypeSafe says extra questions in the same call add little time, because the questions run in parallel. The first call in this repo that sends the full starter set should check the claim. The two August days average about 36 and about 40 posts per second, from the daily counts divided by 86,400. One serial worker at 130.9 ms completes about 7.6 posts per second. About 5 calls in flight match the faster day at the p50. At 274.4 ms the same day needs about 11 calls in flight. The pool size is an estimate from latency, and the account rate limit can be lower. TypeSafe sets tokens per second and requests per second per organization. The numbers are in their console. A 429 or a 529 is retried by their SDK. Cap the pool, and keep the retry backoff inside the cap.

Perspective is free, and the August experiment already called it. Before the shutdown, the cost comparison is Perspective versus Jev. The client comments a ceiling of 100 queries per second. The experiment notes that batches of 20, with a 0.25 second delay, held about 60 to 70 queries per second, and that larger batches drew 503s. At 70 queries per second, the 3,124,215 posts of 2026-08-09 take about 12 hours. Your writeup prefers Jev on F1 and recall for moral outrage, and on the shape of the probabilities. The writeup also cites the higher cost and latency of the frontier Bedrock models, and the Perspective shutdown. On the same 1,000 posts, DeepSeek V3.1 was 318.6 ms at p50 and about $0.076. Qwen3 32B was 387.6 ms and about $0.029. The frontier models were about 1.6 to 1.9 seconds at p50 and about $0.13 to $0.84. Jev's implied bill, if the 374,632 tokens were all input, is about $0.016. The implied bill is close to Qwen and far under GPT 5.6 Terra. The large dollar gap is against the frontier chat models. Jev's p50 is lower than every model in the writeup's table, and Qwen's p50 is about 3 times 130.9 ms.

The sequence to spend against:

1. Measure input tokens, latency, and the account rate limit on a few hundred posts, using the starter questions in one call.
2. Score 10,000 posts from one recent day, restricted the way you answered the language question, paired with Perspective where the URI overlaps, and hand-label a slice.
3. Score one full day only after you accept the check and the measured daily cost.
4. Turn on a schedule for new days, with a dollar cap that stops the job.
5. Score older days once you have named the window and the cap covers the count. The merge also has to be in place, unless you accept landing files as the input.

### Questions on cost

1. Is about $100 for a full day, at the 800-token assumption, a number you want to plan with? Or should the sample's measured tokens replace it before anyone treats a figure for a full day as real?
2. What monthly dollar ceiling should stop the job until a person raises it?
3. Do you want every new post that is in scope scored, or a daily token cap, with a sample of whatever remains after the cap?
4. What dollar ceiling, if any, are you willing to spend on history across the whole backfill?
5. Should every label row store `input_tokens`, so the next month's cost is a sum over the table?

### Questions on timeline

1. What do you want in hand first: the token measurement, the check on 10,000 posts, one day loaded into the Iceberg table, or a search-box query that filters on a label?
2. Your writeup puts the Perspective shutdown at the end of 2026. Does that date set the schedule for a replacement, or is the shutdown background?
3. Is there a paper, talk, or demo date the labels should be ready for? Name the date, or say there is not one.
4. Who else has to read the question wording before the job scores more than the sample?

## Risks

- The Twitter moral outrage result can fail on Bluesky. The 26,000 labels were made on Twitter, and `bluesky_raw.posts` is Bluesky.
- Jev is strongest in English, according to TypeSafe's language note. A `langs` value can be missing or wrong. A filter on `en` will drop some posts you wanted and keep some you did not.
- The organization rate limit has not been read. A pool of 5 to 11 calls can still receive 429s. The hourly lag is then the limit, not the latency estimate.
- A request that sends `jev-latest` lets a TypeSafe release change labels with no commit here. Pin an id, and store the id the response returns.
- A wording edit creates a new label even when the column name stays `prob_toxic`. Queries that pin `question_set_id` stay on one definition. Queries that take the newest row per uri mix definitions whenever a re-score covers only part of the table.
- The 10 GB scan check estimates one table. A search-box join that leaves the check unchanged can refuse a safe query. The same join can also allow a scan well past 10 GB.
- Perspective scores bunch together, and disagreement with Jev is expected on those bunches. Use the hand labels as the bar for scoring a full day.
- Toxicity and hostility on a named account are more sensitive than a keyword match. Whoever can query `bluesky_raw.posts` today would be able to query those scores once the columns are on the search path.
- If you send an empty post, or a post that is only an embed, the score mostly reflects the empty string. If you skip the row, record the skip on the success flag. A count of successful labels is then separate from a count of posts.
- A post deleted on Bluesky can remain in `bluesky_raw.posts`, because the ingester drops non-create commits. The label remains with the row.
- TypeSafe's launch post says they cannot prove the $0.042 price is unsubsidized, and that they expect the price to fall. If the price rises, multiply every dollar figure in the cost section by the same ratio.
- `docs/runbooks/HOW_TO_ADD_NEW_BATCH_DATA_JOB.md` still describes `data_platform/`, which PR #215 removed. The job should follow the Iceberg tables and Athena, on the pattern of the Jetstream maintenance state machine.

## Alternatives

Perspective is the alternative you already ran. The client lives in `feature_generation/perspective_api/`, and the August Parquet is a partial label of two days of `bluesky_raw.posts`. The API is free. Your writeup says it shuts down at the end of 2026. The probabilities bunch at the annotator vote shares. The client turns each score into a 0 or a 1 at 0.5. The attribute list is the one Perspective publishes.

Bedrock chat models, on your sample of 1,000 moral outrage posts, landed near Jev on F1. GPT 5.6 Luna was 0.7395, Claude Sonnet 5 was 0.7512, Qwen3 32B was 0.7490, and DeepSeek V3.1 was 0.7529. They were slower. Qwen was the cheap one, and the dollar and latency figures are in the cost section. Asking a chat model to print a confidence does not give you the probability your writeup compared. Use a Bedrock model again if a hand-label check shows Jev missing an attribute and a chat model hitting it. The bill goes up, and the wait goes up. Store the result under its own model id, so the two label sets stay apart.

A small model you train and serve is what you used for moral outrage in 2021, before Perspective. You own the weights, and you pay for the GPU. Your writeup's reason for trying Jev is that each new attribute would need its own fine-tune and its own serving path. Keep training a small model for any attribute where the hand labels show a stable miss.

Scoring inside the search request fits a handful of posts. At 130.9 ms each, 100,000 posts are about 3.6 hours on one worker. The person is waiting on mail that today comes from an Athena scan. The labels need to be columns before the question is asked.

## Out of scope

The first version scores post text only. Likes, reposts, and follows stay unlabeled. Images and video stay unlabeled, because the Jev docs say the model does not take audio or video. The proposal uses the shared Jev weights TypeSafe already serves. TypeSafe does not offer per-customer fine-tuning. PR #215 removed the CSV feature pipeline, and this proposal builds on the Iceberg tables. The change contains no code, Terraform, or scheduled job.

## Sources

- TypeSafe, "Introducing System One Models & Jev" (2026-09-15), and the model, primitive, and error docs at `https://docs.typesafe.ai`, read 2026-10-21.
- Mark Torres, "Is Jev useful? Testing it against other models and LLMs for social science research" (2026-09-19), `https://markptorres.com/research/2026-09-19-using-jev-for-classification`.
- Post counts and Perspective coverage in `experiments/perspective_api_labeling_2026_08_11/README.md` and `RESULTS.md`.
- Flush limits, the ingester that keeps creates only, the query path, and the 10 GB cap in `bluesky_ingestion_jetstream/` and `backend/agentic_search/`.
