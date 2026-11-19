# LDI value proposition and funding options

First draft, 2026-10-28. Mark Torres (lab engineer, Northwestern) prepared this for William Brady (Billy, Kellogg) to use before their next meeting. Billy asked for a document he can take to people at Kellogg and Northwestern when he asks what support exists for this app, and who the right person to talk to is.

The app is the lab data integrations interface, called LDI in this draft. The live preview is [https://ldi-ui-preview.mind-technology-lab.workers.dev](https://ldi-ui-preview.mind-technology-lab.workers.dev). A person with a Northwestern email can sign up.

MirrorView is still the bandwidth priority. LDI is a side project with a longer planning horizon, and it is also work that keeps Stanley (a student working with Mark) busy. This draft is not a request to change that priority. It is the note Billy asked for so he can ask around.

Items marked TODO are facts Mark still has to fill in. Items marked estimate are calculations, not measurements from the AWS bill. Where a program page and a second page disagree, the draft says so.

## 1. Value proposition

A Northwestern researcher can ask for the Bluesky posts a study needs and get a file back in minutes, from an archive that already exists, instead of spending weeks building a collector. With a labeling budget on the order of $500 to $1,000 a month, the same file can come back already classified, which is the step the current users still do by hand.

The two sentences above are the answer to the question Nour has pressed, and the question Billy expects other people to press. The value at the end of the day is researcher time on a shared archive. Daniel needed the words people were actually using about five Democratic candidates, inside a couple of weeks, so he could set realistic attribute levels for a conjoint experiment. He got 71,786 posts. Tony, working with Tessa and Nour, was ready to rebuild a scraper himself to get Bluesky posts for a rhetoric project. The app is the alternative to that rebuild. The archive and the query exist today. Returning rows that are already labeled is the layer the monthly growth budget is for, and it is the layer Tony, Tessa, and Nour already need. On 2026-10-08 they were scoring news passages from 0 to 100 against their own labels. A calibrated classifier, Jev, from TypeSafe, agreed with those manual labels better than DeepSeek V4 Flash, especially when the passage was long and the prompt included a few labeled examples. They need rows, and they need labels.

What the app is not, and what a skeptical reader will ask, should be said plainly. It is not a general chatbot, and it does not replace the analysis or the theory. Billy already offered to help Daniel on the analysis and theory side. The file is the input to that work.

## 2. What exists today

The repository describes LDI as a social data platform for academic researchers. It keeps a multi-terabyte Bluesky dataset and puts a natural language query interface in front of it, so that getting a dataset for a paper takes minutes rather than the weeks that collecting it yourself would. That description is in `README.md`. The rest of this section cites the files that implement it. The repository does not record the current dollar bill or a live post total, so those two figures are Mark's reports from 2026-10-28, not numbers checked against AWS.

### 2.1 Architecture

The project has three parts, named in `README.md`. Iceberg, named below, is a table format stored as files in Amazon S3. Athena is Amazon's service for running a database query against those files, and Athena's bill depends on how many bytes the query reads.

1. Live ingestion. `bluesky_ingestion_jetstream` reads the Bluesky Jetstream firehose, a continuous stream of new posts, likes, reposts, and follows. Buffers are written to Apache Iceberg tables on Amazon S3 when the set hits 2 GB or 30 minutes, whichever comes first. The resume cursor is written to DynamoDB only after that write succeeds, so a restart does not skip rows that were not stored. A batch that fails its retries is set aside on S3 so it can be inspected later. Daily and weekly jobs compact small files, remove duplicate rows, and expire old table snapshots. Those jobs run in AWS Step Functions, and a failure raises a CloudWatch alarm. The design is in `docs/design_docs/2026-07-13_bluesky_ingestion_jetstream.md` and the maintenance description is in `README.md`. The AWS region in code is `us-east-2` (`lib/aws/constants.py`).

2. Historical backfill. `bluesky_backfill_app` calls Bluesky's getRepo API for past posts of selected users, lands Parquet files on S3, and a weekly Athena job merges those files into the same Iceberg tables the live stream writes. The merge design is `docs/design_docs/2026-09-19_bluesky_backfill_merge.md`. The earlier design for the collector is `docs/design_docs/2026-07-17_bluesky_backfill_app.md`.

3. Query. `backend/agentic_search` turns a researcher's question into a checked SQL query, runs it on Athena, and emails the file. One model call turns the question into a structured intent, which is record type, columns, and date range. Plain code then rejects nonsense input, columns the table does not have, and dates outside coverage. An invalid query never reaches Athena. The endpoint returns HTTP 202 and does the work in the background, so a long scan does not hold the browser open. Results, validation problems, and errors are all emailed. That flow is in `README.md` and `backend/agentic_search/`. Keyword filters on post text are described in `docs/runbooks/agentic_search_keyword_matching.md`.

Before a query runs, `backend/agentic_search/query_postprocessing/check_scan_cost.py` estimates bytes read from Iceberg metadata and refuses the query when the estimate is over 10 GB. The comment in that file, and the design note in `docs/design_docs/2026-07-09_agentic_search_system_design.md`, treat Athena as $5 per TB scanned. At that rate, the 10 GB cap is about $0.05 of Athena charges. A person who needs a wider pull is told to narrow the date range. That is why Tony's plan starts with two weeks in the app, and why a full year is a job Mark would run.

The interface is a Next.js app in `ui/`, deployed as the Cloudflare Worker `ldi-ui-preview` (`ui/cloudflare.config.ts`). It calls the API Worker `ldi-api-preview`. FastAPI routes live in `backend/routes`, and `backend/auth.py` requires a Supabase bearer token on `/query`. Infrastructure for the bucket, the Glue database, the cursor table, Athena, and the maintenance jobs is under `terraform/`.

### 2.2 Data scale and the current bill

Mark's report on 2026-10-28 is that the app can get all Bluesky posts, and that the archive is in the range of 1 to 2 billion posts. In September 2026, when Daniel's file was pulled, the platform had collected every Bluesky post since about 2026-08-10, around 50 million posts, plus likes, reposts, and follows. The repository does not store a current total, so the 1 to 2 billion figure should be treated as Mark's report until someone queries the table and writes the number down.

The repository does record one measured slice. On 2026-08-09 and 2026-08-10, the `bluesky_raw.posts` table held 3,124,215 and 3,463,641 posts, about 6.6 million posts over two days (`experiments/perspective_api_labeling_2026_08_11/README.md`). `README.md` calls the dataset multi-terabyte. Likes, reposts, and follows are separate tables, so a "post" count and a "row" count are not the same number.

TODO for Mark. Query the current row counts for posts, likes, reposts, and follows, and replace the 1 to 2 billion range with those four numbers and the date of the query. Also state the earliest and latest `created_at` in the posts table.

Mark's report is that the running system costs about $20 a month. The repository does not itemize an invoice at that number. A different estimate is already in the deploy runbook. `docs/runbooks/HOW_TO_DEPLOY_TO_CLOUDFLARE.md` says the Workers Paid plan is $5 a month, and that one always-on `standard-1` container, which is the Jetstream collector, is roughly $35 to $60 a month before logs and before data leaving Cloudflare for AWS. The API is described as scaling down when it is idle. The runbook dates those container rates to the Cloudflare pricing pages as of 2026-10-05 and 2026-10-21. Mark's $20 and the runbook's $35 to $60 are not the same bill. Neither one includes labeling. Section 4 is about the labeling budget. Billy should not quote $20 as the Cloudflare collector cost until Mark reconciles it with last month's invoice.

TODO for Mark. Paste the last full month's AWS and Cloudflare totals, split into storage, Athena, ingestion compute, and the Cloudflare plan. Do not paste account IDs, keys, or Terraform output into this draft.

### 2.3 Security

Two different gates exist in the repository, and only one of them is described as live.

Signup is limited to `@kellogg.northwestern.edu`, `@u.northwestern.edu`, and `@northwestern.edu`. The form check is in `ui/src/lib/constants.ts`. The check that actually blocks an account is a Supabase database hook, because the signup API can be called without the form. The hook is in `docs/runbooks/HOW_TO_ENABLE_SELF_SERVE_SIGNUP.md`. A new user verifies the address with a 6 digit code emailed to them, then lands in the app. That is the emailed code Mark described. The API still checks the Supabase token on every query (`backend/auth.py`, `docs/runbooks/HOW_TO_ENABLE_DDOS_PROTECTION.md`).

Cloudflare Access is specified, and the deploy runbook says it was not turned on when that runbook was written. `cloudflare/access/apply_preview_access.py` would put a one time PIN in front of the preview UI and API, limited to the same Northwestern domains, plus one maintainer Gmail address. `docs/runbooks/HOW_TO_DEPLOY_TO_CLOUDFLARE.md` says the Access API returned `access.api.error.not_enabled`, and that someone has to enable Access in the Cloudflare dashboard before the script can apply. The same runbook says `/health` and `/query` are designed to skip Access even after it is on, because the browser calls the API on a different host. Supabase still rejects a missing or bad token on `/query`. Jetstream and the backfill worker are outside this policy. Backfill start and stop use a separate bearer token.

TODO for Mark. Confirm whether Access has been enabled since that runbook was written. Until that is confirmed, Billy should say that signup is Northwestern email plus an emailed code, and that a second Cloudflare PIN gate is written and not yet confirmed as on.

Cloudflare filters traffic to the Workers. That is network filtering, not a login. The runbook is `docs/runbooks/HOW_TO_ENABLE_DDOS_PROTECTION.md`.

### 2.4 Current users

The repository does not name these people. The accounts below are from Mark, from an email thread and from Slack. Affiliations are included only where Mark stated them. Nour is in both use cases. She is the person Billy expects to press on the value proposition in section 1.

**Daniel, with Billy, Nour, and Mark. Email, 2026-09-09 to 2026-09-11.** Daniel wanted common criticisms, from the center and from the left, of prominent Democratic candidates since their respective primaries. The candidates were Abdul El-Sayed, James Talarico, Xavier Becerra, Roy Cooper, and Jon Ossoff. The goal was to validate realistic attribute levels for a conjoint experiment. It was time sensitive, because he needed the language finalized within a couple of weeks. He said even a random selection of critical posts from recent weeks would help, and he did not know how time intensive the request would be.

Mark delivered all Bluesky posts from the past month that mentioned those candidates, as a Parquet file. The fields were `text`, `matched_candidate`, and `url`. There were about 71,786 posts. El-Sayed had 27,769, Talarico 18,866, Becerra 1,326, Cooper 797, and Ossoff 23,028. Cooper was matched on the exact phrase "roy cooper", because "cooper" alone is too common. At that time the platform had collected every Bluesky post since about 2026-08-10, around 50 million posts, plus likes, reposts, and follows.

Billy said he is broadly interested in rhetoric around progressive candidates and offered help on the analysis and theory side. The delivery is a completed example of a fast extract for a conjoint design. It is also a possible collaboration, and that collaboration is not a completed paper.

TODO for Mark. Add whether Daniel used the file, whether the conjoint launched, and whether any of the 71,786 posts were labeled. Do not add sample post text to this draft.

**Tony, with Tessa and Nour. Slack, 2026-10-22 to 2026-10-28.** The project is detecting rhetorical language in text across several topics, which are Israel and Palestine, Ukraine and Russia, and the MeToo movement. They had been using news articles from 2008 onward, filtered by keyword, for example text matching `palestin*` and `israel*`. They now want to expand to social media. Tony asked how to get Bluesky data after seeing the tool at a lab meeting. He offered to work it out himself from the scraping code. That offer is the manual alternative, stated by the user.

The request is all Bluesky posts about Israel and Palestine for this year. As of 2026-10-28, Mark has sent the app link. The plan is that Tony signs up with a Northwestern email, queries the last two weeks first to check fit, and then, if that file is useful, Mark sets up a full year. A query in the app takes about 5 to 10 minutes, and the results are emailed as a file. That 5 to 10 minutes is Mark's report about the live app, not a timer log in the repository.

The labeling need is separate and earlier. On 2026-10-08, Tony, Tessa, and Nour were classifying news passages on a 0 to 100 scale against manual labels. Jev, from TypeSafe, agreed with their manual labels better than DeepSeek V4 Flash, especially with long context and few-shot prompts. LDI does not yet return those labels. The comparison is evidence that this group needs both the rows and a classifier, which is the growth case in section 4.

TODO for Mark. Record whether Tony completed signup, what the two week file contained (row count and columns only), and whether a year pull was started. Do not paste post text.

No other named users are documented. Stanley is a student working with Mark on the project. This draft does not describe a study of Stanley's.

## 3. Before and after examples

The first two examples are the real requests in section 2.4. The third is illustrative, meaning it is a realistic social science request and not a person who has used the app. Time and cost figures are estimates. The reasoning sits next to each figure.

Mark's estimate, from the 2026-10-28 conversation with Billy, is that scraping and labeling social media data that would take someone weeks to build, even with a general model such as Claude or ChatGPT, can be done in 5 to 10 minutes in the app. The 5 to 10 minutes matches the live query path for a request inside the 10 GB scan cap. It does not match a year long pull, and it does not match labeling, because labeling is not in the product yet. "Weeks" is Mark's estimate of the manual build. Nobody timed a researcher building the scraper for these examples.

### 3.1 Daniel, conjoint wording, September 2026

Daniel's request happened.

Before, the manual path. A researcher, or a researcher plus Claude, would need a Bluesky collector, a place to store a month of posts, a filter for five names, and a rule that "cooper" is too common to match alone. They would then export `text` and a URL. Daniel did not know whether that was days or weeks, and he had a couple of weeks to finalize language. Mark's estimate for that build, even with a general model, is on the order of weeks of engineering, plus whatever the researcher spends reading posts afterward. The reading is still required. The app does not write the conjoint attributes.

After, what Mark delivered. One Parquet file, about 71,786 posts from the prior month, with `text`, `matched_candidate`, and `url`, and the per candidate counts in section 2.4. The repository does not record how many minutes that September extract took, so this draft does not claim it took 5 to 10 minutes. The current app is built so that a later request of this shape, if it stays under the 10 GB scan cap, returns by email in about 5 to 10 minutes of wait time. Athena cost for a scan at the cap is about $0.05, using $5 per TB from the Athena pricing example. A month of keyword matches on five names is a small slice of the archive, so the Athena charge is likely cents, not dollars. That last sentence is an estimate, not a line from the September bill.

What remains manual. Someone still has to read posts and decide which criticisms are real enough to put in a conjoint. Billy offered to help on the analysis and theory side. That offer is the right split. LDI supplies the posts. The study design stays with the researchers.

### 3.2 Tony, Tessa, and Nour, rhetoric on social media, October 2026

Tony's request is in progress. Tony has the link and has not, in the notes Mark provided, finished the two week check.

Before, the manual path. Tony offered to work from the scraping code. That is the concrete version of the weeks long build. They already filter news with keywords such as `palestin*` and `israel*`, from 2008 onward, and they wanted the same kind of filter on Bluesky for this year. Building that means a collector, storage, a keyword rule, and an export. Separately, they already label text. On news passages, Jev agreed with their 0 to 100 manual labels better than DeepSeek V4 Flash. Doing that labeling by hand, or by calling a model post by post from a laptop, is the second cost. A year of Bluesky posts that mention a high volume topic can be far larger than a news corpus. This draft does not have the row count, because the year pull has not been run.

After, the plan Mark and Tony agreed. Tony signs up with a Northwestern email. He queries the last two weeks in the app. Mark's report is that a query takes about 5 to 10 minutes and the file arrives by email. If the two week file fits the project, Mark runs the year, because a year of text is likely to exceed the 10 GB self serve cap in `check_scan_cost.py`, and the app will tell the user to narrow the dates. The year pull is staff time, not a 5 minute click. Labeling is not in this plan yet. If they want each post scored the way they scored news passages, that is the classifier budget in section 4, and it is a batch job, not part of the 5 to 10 minutes.

Cost estimate for the two week check. Wait time is about 5 to 10 minutes. Athena dollars are about $0.05 if the scan sits at the 10 GB cap, and less if the keyword and the date range prune the scan. Staff time for the later year pull is not estimated here.

TODO for Mark. After the two week file exists, add the row count and the Athena bytes scanned, and delete this TODO.

### 3.3 Illustrative example, survey wording for a health behavior

The health behavior example is not a current user. It is here so Billy can describe a psychology use case that is not the two political projects above.

A researcher wants the words people use about a health behavior, over a two week window, before writing survey items. The manual path is the same collector, filter, and export, which Mark estimates at weeks even with Claude or ChatGPT. In LDI, a two week keyword query is the kind of request the app is built to answer inside the scan cap, with about 5 to 10 minutes of wait time and an emailed file. Athena cost is on the order of cents to about $0.05 if the scan approaches 10 GB. Adding a label to every post, for example a topic tag the researcher defines, is not available in the app today. That label is the growth case, and the cost depends on how many posts match, as calculated in section 4.

## 4. Growth plan and cost model

The $500 to $1,000 a month is for running classifiers and model labeling over the archive, plus the compute, storage, and query cost that grows with that work. It is not the cost of keeping today's collector running. Today's collector is the $20 a month Mark reports.

The right shape for that money is a sample labeled by a cheap model, a small classifier trained on that sample, and the small classifier applied to a much larger set of posts. Labeling 1 to 2 billion posts with a frontier model does not fit this budget. The arithmetic is below. Every dollar figure in this section is an estimate unless the sentence names a pricing page.

### 4.1 Prices used

| Item | Rate used | Source | Status |
| --- | --- | --- | --- |
| Athena SQL, per TB scanned | $5 | [Amazon Athena pricing](https://aws.amazon.com/athena/pricing/), worked example on the page ("3 * $5/TB = $15") | Read on the pricing page, 2026-10-28 |
| S3 Standard, first 50 TB per month | $0.023 per GB-month | AWS Price List API extract for us-east-1, publication timestamp 2026-10-15, as reported by [DevZero's 2026-10-15 writeup](https://www.devzero.io/blog/aws-s3-pricing). The official [S3 pricing page](https://aws.amazon.com/s3/pricing/) describes the charge but the per GB table did not appear in the static page text. | Secondary source. The archive is in us-east-2, and this rate is us-east-1. Treat it as within a few percent until someone checks the Ohio line. |
| Claude Haiku 5.5, prompts up to 100,000 tokens | $0.10 per million input tokens, $0.50 per million output tokens | [Anthropic model pricing](https://platform.claude.com/docs/en/about-claude/pricing) | Anthropic's API price, read 2026-10-28. The Bedrock model card says Haiku 5.5 is billed through the AWS Marketplace and points at the Bedrock pricing page. Haiku 5.5 rates were not in the static Bedrock pricing HTML retrieved the same day. A secondary October 2026 summary lists the same $0.10 and $0.50 on Bedrock. Recheck Bedrock before submitting a budget. |
| Self serve scan cap | 10 GB, about $0.05 at $5 per TB | `backend/agentic_search/query_postprocessing/check_scan_cost.py` | Code, not a bill |

An on-demand `g6.xlarge` in US East (N. Virginia) was $0.8048 per hour on the EC2 price list read on 2026-10-28. Left running all month, that is about $590, which consumes most of a $500 to $1,000 budget before any labels. A GPU should be a batch that stops. The archive region is us-east-2, so the Ohio rate still has to be checked.

### 4.2 What one labeled post costs

Assumption, not a measurement. A Bluesky post plus a short instruction is 200 input tokens. The model returns about 20 tokens, which is enough for a label and a short reason. The instruction is counted on every post, which is the expensive case. Prompt caching would lower the input side, and this draft does not take that credit.

At Haiku 5.5 rates, one post costs about 200 / 1,000,000 * $0.10, plus 20 / 1,000,000 * $0.50, which is $0.00002 plus $0.00001, or $0.00003.

At that rate, $500 labels about 17 million posts, and $1,000 labels about 33 million posts. A one time pass over 1 billion posts would be about $30,000. A pass over 2 billion posts would be about $60,000. Spread over a year, $1,000 a month is $12,000, which labels about 400 million posts and does not finish a 1 to 2 billion corpus.

The post counts above are why the growth plan should not be "run Haiku on every post." A frontier model is worse. Anthropic's published price for Claude Sonnet 5.5 is $2 per million input tokens and $10 per million output tokens, about 20 times the Haiku input price. The same 200 plus 20 token assumption would be about $0.0006 a post, or about $600,000 for 1 billion posts. A billion post run at Sonnet prices is not a $1,000 a month project.

### 4.3 Storage and queries

Assumption, not a measurement. One compressed post, with the columns a study needs, is about 1 KB. One billion posts is then about 1 TB, which is about 1,000 GB times $0.023, or about $23 a month of S3 Standard. Two billion posts is about $47 a month. A multi terabyte archive, which is what `README.md` claims, is on the order of $25 to $100 a month of storage if it is a few terabytes, before request charges. Likes, reposts, and follows add more. This is the same order of magnitude as Mark's $20 a month report, which supports treating $20 as the collector and the archive, and treating $500 to $1,000 as new labeling spend. It is not a reconciliation to an invoice.

Athena stays cheap when scans stay bounded. A query at the 10 GB cap is about $0.05. A query that scans 1 TB is $5. The design risk, already written in `docs/design_docs/2026-07-09_agentic_search_system_design.md`, is one wide query, not the number of users. The 10 GB check is the control. Staff run the pulls that fail the check, as with Tony's planned year.

### 4.4 What $500 to $1,000 a month buys

A practical month inside this band looks like the following. The figures are estimates, using the rates above, and they assume the $20 collector bill continues beside them.

| Line | What it is | Estimate per month |
| --- | --- | --- |
| Collector and current storage | Mark's report, not remeasured | about $20, outside this band |
| Extra storage as the archive and the label files grow | A few terabytes at $0.023 per GB-month | about $25 to $100 |
| Cheap model labels on a sample | About 10 million posts at $0.00003, Haiku class rates | about $300 |
| Small classifier applied to a much larger set | Train on the sample, score posts on CPU or a short GPU batch | A us-east-1 on-demand `g6.xlarge` was $0.8048 per hour on the EC2 price list read on 2026-10-28. Left on all month, that is about $590. A batch of tens of hours fits inside this band. Recheck us-east-2 before buying. |
| Athena for researcher queries | Tens of capped queries, plus a few staff runs | about $10 to $50 unless someone scans terabytes repeatedly |
| Room for a second topic or a rerun | What is left of a $1,000 cap | the remainder |

At $500, cut the Haiku sample or skip a long GPU rental. At $1,000, keep a sample, a short GPU or CPU batch, and a second topic. The corpus gets a cheap score from the small model. Only the sample gets a model generated label.

A cheaper hosted model changes the sample size. The AWS Bedrock price list read on 2026-10-28, for US East (N. Virginia), listed Amazon Nova Micro batch at $0.0175 per million input tokens and $0.07 per million output tokens. At the 200 input and 20 output token assumption above, that is about $0.0000049 per post, or about $4,900 for a billion posts in one pass. A billion posts still does not fit in one month of this budget. Ten million posts would be about $49. Haiku remains the expensive end of the "cheap model" range. These Nova rates were not on the static Bedrock HTML page retrieved the same day, and they are not the us-east-2 price. Recheck the console before a job.

The Perspective API experiment is the closest thing in the repository to a production labeling path, and it is not production. `experiments/perspective_api_labeling_2026_08_11/README.md` says that as of 2026-09-22 the experiment no longer runs, because it imported `data_platform/`, which was removed. When it ran, stable throughput was about 60 to 70 requests a second, and a day of about 3 million posts took many hours. That is evidence that scoring a full day is an overnight batch, not a click in the UI. Public Perspective API prices were not confirmed for this draft.

### 4.5 Cheaper alternatives

1. Keep doing what Tony is doing. Pull two weeks, decide the file is useful, then pay for a wider pull. Most questions do not need the whole corpus.
2. Label tens of thousands to a few million posts with a cheap model, train a small classifier, and apply the small classifier to the rest. That is the only way the full corpus fits in $500 to $1,000 a month.
3. Ask Northwestern IT for a university AWS account. The cloud account page says the institutional discount is 4.5 percent on most AWS services, and that most egress fees are waived. Links are in section 5. The discount does not change the conclusion about frontier models. It changes the bill by a few percent.
4. Use Quest for training the small classifier on a sample, if the sample fits in a Quest allocation. Quest general access storage is 1 TB at Research I and 2 TB at Research II, which is not a home for the multi terabyte archive. Section 5 has the allocation page.
5. Do not buy a second cloud for its own sake. Google, Azure, OpenAI, and Anthropic credit programs are in section 5. They are smaller than a year of this budget, or they are aimed at a different kind of project. They are worth a form if the form is short. They are not the plan.

### 4.6 What blows the budget

Labeling every post with a frontier or even a mid size model blows the budget, as the Sonnet arithmetic shows. Removing the 10 GB scan cap without a human check also blows it, because one query over a terabyte is $5 and a careless pattern of those queries is the long tail the design doc already warns about. Storing many full copies of model outputs next to the raw archive adds storage, but storage is the small term. Tokens are the large term.

## 5. Funding and infrastructure options

Programs below were checked against public pages on 2026-10-28. Amounts and deadlines appear only when a page stated them. A missed page is listed at the end of the section rather than filled in. Named people appear only when a page listed them.

The best near term asks are Kellogg Research Support, for a faculty research account and for the Kellogg Data Cloud, and Northwestern IT, for a university AWS account and a conversation about research credits. The best grant match found is the Russell Sage Foundation's Margaret Olivia Sage grants, with a letter of inquiry due 2026-12-01. The Northwestern Nexus Labs competition is real and soon, and it fits only if LDI is part of a larger cross school project. NSF CSSI and HNDS both say they are waiting for a new publication, so they are not a proposal to start this month. A NAIRR Pilot allocation is the open compute route, if the lab can make the labeled output public.

### 5.1 Kellogg

**Kellogg Research Support.** This is the first office Billy should call. The public page gives the office, the email `rs@kellogg.northwestern.edu`, and the phone 847-491-3300. URL: [kellogg.northwestern.edu/academics-research/research-support/](https://www.kellogg.northwestern.edu/academics-research/research-support/). The page does not list a seed grant amount or a deadline. What the office does publish, on subpages, is computing that is close to this app.

The Kellogg Linux Cluster is for Kellogg researchers and their collaborators. Tenure line faculty and PhD students have access. Others ask Research Support. A project directory holds up to 2 TB at no charge, and more quota is $39 per TB per year. Normal priority is 24 CPU cores at a time. URL: [Kellogg Linux Cluster](https://www.kellogg.northwestern.edu/academics-research/research-support/computing/kellogg-linux-cluster/). It can hold a sample and a small classifier job. It is not the firehose archive. The public faculty page does not say whether Billy's appointment is tenure line, so automatic access should be confirmed with Research Support rather than assumed.

The Kellogg Data Cloud is an Amazon Athena platform that hosts Kellogg datasets. Access is granted per database, by emailing `rs@kellogg.northwestern.edu`. Login uses a NetID through Northwestern IT, and the account name on the page is `ksm-rch-data`. URLs: [Kellogg Data Cloud](https://www.kellogg.northwestern.edu/academics-research/research-support/computing/kellogg-data-cloud/) and [data hosting](https://www.kellogg.northwestern.edu/academics-research/research-support/computing/kellogg-data-hosting/). This is the closest existing Kellogg service. LDI already queries Iceberg with Athena. The question for Research Support is whether a Bluesky posts database can sit there, who may query it, and whether a faculty research account can pay the $500 to $1,000 labeling bill. Amount and deadline are not published.

Computational consulting on the same site offers help collecting and curating data, including web collection, and help with machine learning. URL: [computational consulting](https://www.kellogg.northwestern.edu/academics-research/research-support/services/computational-consulting/). That is staff time, not a grant. It is a fit for a researcher who wants help with a dataset LDI already returned.

The Kellogg Behavioral Lab runs human subject studies for Kellogg faculty, PhD students, and postdocs. Contact on the FAQ page is `behavioralrs@kellogg.northwestern.edu`. URL: [researcher FAQ](https://www.kellogg.northwestern.edu/academics-research/research-support/behavioral-research/kellogg-researcher/faq-researcher/). It is the wrong office for cloud bills. It is a relevant later stop if Daniel's conjoint, or a similar study, needs participants. The lab requires an IRB approval letter before data collection.

**Kellogg PhD research funding.** Up to $2,700 from the Dean's office in a fiscal year, for Kellogg PhD students, with quarterly deadlines. Joint projects with faculty are not eligible. Fall 2026 applications were due 2026-10-15, which has passed. The next published dates are a winter pre work form on 2027-01-04 and an application on 2027-02-05. URL: [doctoral research funding](https://www.kellogg.northwestern.edu/doctoral-intranet/student-services/research-funding-resources/). Fit is weak. Stanley is described as a student working with Mark, not as a Kellogg PhD student, and a project Billy is part of cannot use this fund. TODO for Mark. Confirm Stanley's program. Do not pursue this fund unless he is an eligible Kellogg PhD and the project is his, not a faculty project.

**Kellogg research fellows.** These are predoctoral jobs, not project money. The public openings page lists a behavioral fellow deadline of 2027-01-29 and empirical fellow deadlines of 2026-12-17, for named faculty who are not this project. URL: [research fellow applications](https://www.kellogg.northwestern.edu/academics-research/research-support/research-fellows/apply/). Mention it only if someone asks about staffing. It does not pay the AWS bill.

**Center for Research in Technology and Innovation, faculty research grants.** The opportunities page says Kellogg faculty can get grants for projects related to the center's focus, and that grants can support data collection and research assistance. No amount and no deadline are published. Contact `crti@kellogg.northwestern.edu`. URL: [CRTI opportunities](https://www.kellogg.northwestern.edu/academics-research/research-technology-innovation/opportunities/). This is the closest Kellogg cash grant found on topic. It is an inquiry, not a confirmed award, until the office says infrastructure software qualifies.

**Global Poverty Research Lab grants.** Rolling, data purchase up to $5,000, research assistance up to $5,000, for Northwestern faculty and graduate students working on global poverty, including randomized trials. Email `Poverty-Research@Northwestern.edu`. URL: [GPRL funding](https://www.kellogg.northwestern.edu/academics-research/global-poverty-research-lab/research-support/funding-opportunities-grants/). Poor fit. LDI is not a poverty study. A later project that used the archive for a development question could apply for the data or assistance cap. The platform itself should not.

### 5.2 Northwestern research computing

**Quest, through ColdFront.** General access compute and storage are free to the researcher. Research I is up to 100,000 compute hours a year and 1 TB of storage. Research II is up to 500,000 hours and 2 TB, by proposal. Allocations last a year and can be renewed. As of 2026-06-26, requests go through ColdFront, and Research II upgrades are reviewed on a rolling basis. URLs: [Quest access and allocations](https://www.it.northwestern.edu/departments/it-services-support/research/computing/quest/quest-access-and-allocations.html) and [ColdFront transition](https://rcdsdocs.it.northwestern.edu/systems/coldfront/transition-to-coldfront.html). Fit is the classifier training step on a sample. The storage caps are below a multi terabyte archive, so Quest is not a replacement for S3.

**University cloud accounts.** Any Northwestern researcher, including students and postdocs, can request AWS, Google Cloud, or Azure. The form needs a chartstring. AWS and Google Cloud also need a blanket purchase order. The page states an institutional AWS discount of 4.5 percent on most services, a Google Cloud discount of 5 percent on most services, and waived egress for most transfers. NIH funded projects can get larger discounts. LDI is not described as NIH funded, so the NIH rates should not be assumed. URL: [requesting a cloud account](https://rcdsdocs.it.northwestern.edu/systems/Cloud/cloud-accounts.html). Northwestern's own guidance says research data produced at Northwestern should sit in university approved systems, which is a reason to move the bill onto a Kellogg or university account even if the dollar discount is small.

**Data science and AI project support.** Research Computing and Data Services will work with any Northwestern faculty member on data collection, analysis, and software, typically for a quarter of exploration or 2 to 12 months if the goal is a research product. The page says there is no cost for most services, and that researchers pay for cloud or storage that continues after the project. Kellogg researchers are pointed back to Kellogg Research Support and may be referred there. Contact `nuit_rcds@northwestern.edu`. URL: [collaborative project support](https://www.it.northwestern.edu/departments/it-services-support/research/data-science-statistics-visualization/collaborative-project-support.html). Fit is help designing the classifier. It is not a subsidy for the monthly bill.

**Credits and a sandbox, same group.** The cloud support page lists an AWS sandbox for learning, not for research data, requested by emailing `servicedesk@northwestern.edu` with `#cloudops` in the subject. It also says researchers may be eligible for AWS Cloud Credits for Research, and that the way to explore eligibility is to contact the research computing team through the Research Cloud Consult. NIH Cloud Lab is $500 for 90 days and is limited to NIH grant funded projects, so it is a mismatch. URL: [cloud support](https://rcdsdocs.it.northwestern.edu/systems/Cloud/cloud-support.html). The service catalog entry is [Research Computing Cloud](https://services.northwestern.edu/TDClient/30/Portal/Requests/Service/86/Research-Computing-Cloud).

### 5.3 Other Northwestern offices and competitions

**Northwestern Nexus Labs.** Announced 2026-10-13. Up to $250,000, to be spent in 12 to 18 months, plus convening space and help pursuing external funding. Teams need at least two full time regular faculty, preferably from different departments or schools. A letter of intent is due 2026-11-30. Proposals are due 2026-12-15. An informational webinar is 2026-11-02, 1 to 2 p.m. Up to 10 teams pitch in the first week of March 2027, and winners are to be announced by 2027-03-15. URL: [sites.northwestern.edu/nexuslabs](https://sites.northwestern.edu/nexuslabs/). The news story is [Northwestern Now, 2026-10-13](https://news.northwestern.edu/stories/2026/10/northwestern-invests-in-the-future-of-discovery). Fit is partial, and the mismatch matters. The competition wants projects that can become institutes or centers and that have a path to large external funding. A request to cover $1,000 a month of AWS does not match that bar. A proposal in which LDI is the data layer for a cross school question, with a second faculty member, and with Russell Sage or NSF as the external path, could match. Billy should go to the 2026-11-02 webinar before deciding. He should not send this draft in as the proposal.

**Northwestern Network for Collaborative Intelligence, Collaborative Intelligence Research Awards.** Up to about $35,000 for one year, faculty and staff, collaboration across at least two units, data acquisition allowed. The published deadline was 2026-07-31, and awards were announced afterward. That cycle is closed. Total pool on the RFP was up to $350,000. Contact `nnci@northwestern.edu`. URLs: [call for proposals](https://nnci.northwestern.edu/news-events/news/2026/call-for-proposals-nnci-collaborative-intelligence-research-awards.html), the [RFP pdf](https://nnci.northwestern.edu/docs/rfp-nnci-collaborative-intelligence-research-awards.pdf), and the [2026 awardees](https://nnci.northwestern.edu/research/collaborative-intelligence-research-awards.html). William Brady and Ágnes Horvát are already 2026 awardees, for a feed ranking project titled "Countering the Spiral of Silence with an LLM-Calibrated 'Rebalanced Visibility' Feed-Ranking Algorithm." The awardee page does not give their dollar amount, and it does not say the award pays for LDI. A future LDI proposal would be a different project, would still need a second unit, and has no published next deadline.

**Institute for Policy Research seed grants.** A 2026-08-06 IPR news story says IPR awarded six seed grants earlier in 2026, around a few thousand dollars each, to IPR faculty and doctoral students. URL: [IPR news](https://www.ipr.northwestern.edu/news/2026/seed-grants-carve-paths-to-possible-future-funding.html). Contact on that page is `ipr@northwestern.edu`, 847-491-3395. An open call and a deadline were not on that page. Billy's public IPR profile lists him as an IPR Associate, not as a fellow, and the profile still says Assistant Professor, which may lag his Kellogg title. URL: [IPR profile](https://www.ipr.northwestern.edu/who-we-are/faculty-experts/william-brady.html). The news story does not say associates can apply. The awards are the right size for a pilot survey, and they are small relative to a year of labeling. Worth a question to IPR. Not worth a proposal until eligibility is confirmed.

**Buffett Institute, Global Working Group grants.** Up to $200,000 over two to five years. Groups must be co led by two tenured Northwestern faculty from two disciplines, plus at least two more Northwestern faculty. The page, read 2026-10-28, lists the submission deadline as 2027-02-15. Decisions are sent in April. The research director listed on the page is Harrington Weihl, `Harrington.Weihl@northwestern.edu`. URL: [Buffett Global Working Group grants](https://buffett.northwestern.edu/programs/faculty-funding/global-working-group-grants/). Poor fit for an operating bill. Possible fit if a tenured pair wants a multi year global project that uses the archive. Billy's tenure status was not on the pages checked, so a co lead role should not be assumed.

**The Garage.** Student startup programs. Open to full time degree seeking Northwestern students. Jumpstart is a 10 week summer program with $10,000 and mentorship. VentureCat has a prize pool of $175,000 for student founded startups. Contact `thegarage@northwestern.edu`, 847-467-7155. The executive director listed in the university directory is Mike Raab. URL: [programs](https://www.thegarage.northwestern.edu/programs). Mismatch. LDI is a faculty research tool, not a student company, and MirrorView remains the priority. Stanley could look at Tinker or Residency only if he wants startup programming. That is not the funding path for the AWS bill.

**Libraries.** Digital Scholarship and Data Services offers consultations, data management plans, and a data library of commonly used datasets. URL: [digital scholarship](https://www.library.northwestern.edu/use-the-libraries/research-teaching/digital-scholarship/). The library main line on related guides is (847) 491-7658. An earlier organization-chart URL for Academic Innovation returned 404 on 2026-10-28, so it is not cited. The library is a reasonable question for a data management plan and for publishing a small public extract. It is not a host for the archive and not a source of cloud credit.

**Office for Research, internal funding index.** The research development office keeps a list of internal programs and can be reached at `researchdev@northwestern.edu`, 847-491-3741. URL: [internal funding programs](https://ord.northwestern.edu/funding/pilot-and-seed-funding-programs.html). Several entries on that list are cancer, sleep, or global health, and they are poor fits. The office is still the right place to ask what social science or data infrastructure seed funds exist that are not on the public list. The Pat and Shirley Ryan Family Research Acceleration Fund, $100,000 to $300,000, deadline 2026-03-01, is for life sciences commercialization. URL via the School of Communication research office: [Ryan fund notice](https://research.soc.northwestern.edu/pat-and-shirley-ryan-family-research-acceleration-fund-due-mar-1-2026/). Mismatch, and the deadline has passed.

**NICO.** A February 2026 NUCATS and NICO symposium offered teams a chance to apply for up to $50,000, aimed at human health and disease. URL: [NUCATS news](https://www.nucats.northwestern.edu/about/news/2026/nucats-and-nico-spark-collaboration.html). That was a one day competition with a health frame. It is not an open LDI fund. A standing NICO seed program with a future deadline was not confirmed.

### 5.4 External grants and credits

**Russell Sage Foundation, Margaret Olivia Sage grants.** This is the strongest external match found. One of four priority areas is data infrastructure for social science research, including digital traces and platform data, and another is the societal impact of artificial intelligence. Democracy is a third, which is closer to Daniel's project than to the platform in the abstract. Grants are up to $750,000 in direct costs over three years, plus 15 percent indirect costs. A renewal of up to $500,000 for two more years is possible for promising projects. PIs and co PIs must hold a doctorate, and the team must be multi disciplinary or interdisciplinary. A letter of inquiry is due 2026-12-01 at 2 p.m. Eastern. Invited proposals are due 2027-02-22. The news post says funding would start on or after 2027-09-01. URLs: [announcement](https://www.russellsage.org/news/new-margaret-olivia-sage-grants-competition), [RFP](https://www.russellsage.org/research/priorities/mos-grants/rfp-mos-grants), [eligibility](https://www.russellsage.org/apply/info/eligibility), [budget](https://www.russellsage.org/apply/info/budget), [deadlines](https://www.russellsage.org/apply/application-deadlines). Fit is real if Billy can recruit a co PI from another discipline and if the proposal is a research and data project, with a plan to share data and to reach people outside the university. A proposal that only asks for AWS operations will read as a mismatch. The core Russell Sage programs are a weaker vehicle for the platform itself. For the 2026-10-28 deadline, which is today, the foundation is accepting letters only in Social, Political and Economic Inequality, Future of Work, and one admissions initiative. Behavioral Science and Decision Making in Context is not accepting applications. The old Computational Social Science special initiative no longer accepts unsolicited proposals. URL: [completed CSS initiative](https://www.russellsage.org/research/completed/computational-social-science-special-initiative).

**NSF CSSI.** The program page, read 2026-10-28, says "Waiting for new publication" and "No upcoming due dates." URL: [CSSI program page](https://www.nsf.gov/funding/opportunities/cssi-cyberinfrastructure-systems-scientific-innovation). The old solicitation, NSF 22-632, listed December 1 annually after 2025-12-01, and Elements awards up to $600,000 over 3 years. URL: [NSF 22-632](https://www.nsf.gov/funding/opportunities/cssi-cyberinfrastructure-systems-scientific-innovation/nsf22-632/solicitation). That annual date is not a live deadline while the program page says there is none. Do not start a proposal against 2026-12-01. The contact on the program page is `CSSIQueries@nsf.gov`. Ask when the new publication is coming. SBE participated in the old solicitation. A campus tool for one lab was already a tight fit for a program aimed at community infrastructure.

**NSF HNDS, solicitation NSF 23-568.** Human Networks and Data Science, Infrastructure track (HNDS-I), is the social science infrastructure program CSSI points at. The NSF program page, read 2026-10-28, says status "Waiting for new publication" and "No upcoming due dates." URL: [HNDS program page](https://www.nsf.gov/funding/opportunities/hnds-human-networks-data-science). Grants.gov still listed a closing date of 2026-08-06, which has passed, and an award range from $10,000 to $1,200,000 on the old solicitation number. URL: [Grants.gov listing](https://simpler.grants.gov/opportunity/348260). Do not treat August 2026 as a live deadline. The right step is to ask the program officer when the new publication is coming. HNDS-I is a better topical fit than CSSI if it reopens, because it funds databases that make new social science possible.

**AWS Cloud Credit for Research.** Faculty and research staff at accredited institutions can apply. Students are capped at $5,000. Faculty and staff awards are not capped, and applicants may not receive the full request. Credits last one year. The program supports a finite proof of concept, a shared tool, or a workshop. The FAQ says research credit will not support ongoing or established research, general lab projects, or operations. URLs: [program page](https://aws.amazon.com/government-education/research-and-technical-computing/cloud-credit-for-research/) and [FAQ](https://aws.amazon.com/government-education/research-and-technical-computing/cloud-credit-for-research/faqs/). The two AWS pages disagree on review time. The FAQ and the apply page say a typical review is 30 to 60 days. The main program page says 90 to 120 days. Plan for the longer number. Free Tier accounts are ineligible as of 2026-02-16, according to the apply page. Fit is a finite labeling pilot or a public query tool, framed as a new capability. Fit is poor if the application says "please fund our lab's monthly bill." Apply from a university email, with an AWS account that already exists. Northwestern's research computing group asked to be contacted first, through the cloud support page in section 5.2.

**NAIRR Pilot allocations.** NSF and partner compute, including cloud credits, for AI research. Open until the pilot ends or the resources are committed. Awards last 12 months. Requests in by the 15th of a month are typically decided by the end of the next month. Results have to be open and publishable, and the PI name, affiliation, title, and abstract are posted. A dollar cap is not published. URL: [NAIRR allocations](https://nairrpilot.org/opportunities/allocations). Fit is a 12 month labeling or classifier allocation, if the lab can make the method or a labeled sample public. A Northwestern-only archive conflicts with that openness rule. It does not replace the standing ingest bill.

**Google Cloud research credits.** Faculty, postdoctoral, and nonprofit lab researcher awards are up to $5,000. PhD students are up to $1,000. Credits expire 365 days after issuance. The program is open to any academic field. URL: [program FAQ](https://support.google.com/google-cloud-higher-ed/answer/10723679?hl=en) and the [application](https://edu.google.com/intl/ALL_us/programs/credits/research/). $5,000 is a short pilot on a second cloud. Moving the Iceberg archive for that credit is a poor trade.

**Microsoft Azure research credits.** The academic research page describes credits for a proof of concept, a migration, or a research tool, and it does not publish an amount or a deadline. URL: [Azure for academic research](https://www.microsoft.com/en-us/azure-academic-research/). Amount not published. Same caution as Google. Northwestern already has an Azure agreement, described on the cloud account page, if a specific Azure service is the point.

**OpenAI Researcher Access Program.** Up to $1,000 of API credits for 12 months, for academic and nonprofit researchers, reviewed quarterly in March, June, September, and December. The program wants work on responsible deployment, risk, and societal impact. URL: [FAQ](https://help.openai.com/en/articles/10139500-researcher-access-program-faq) and [application](https://openai.com/form/researcher-access-program/). $1,000 is a few weeks of the cheap labeling sample in section 4, not a corpus strategy. Fine as a supplement for a methods comparison. Not the growth plan.

**Anthropic AI for Science.** Up to $20,000 of API credits for 6 months, reviewed on the first Monday of each month. The program says it is aimed at high impact science, with a particular focus on biology and life sciences. Social science can fall under "other fields," and the page does not promise that. URL: [program description](https://support.claude.com/en/articles/11199177-anthropic-s-ai-for-science-program). $20,000 is meaningful next to the $12,000 a year labeling sketch, and the life sciences focus is a real risk of a decline. Apply only with a scientific question, not with a request for general lab credits.

**Alfred P. Sloan Foundation, Open Source in Science.** The program page says grants focus on tooling, institutions, and incentives around research software, and that the program is not funding individual open source development projects. URL: [Open Source in Science](https://sloan.org/programs/digital-technology/open-source-in-science). No current deadline or amount was on that page. Weak fit for an AWS bill. Possible fit later if the ask is about how a university sustains a research data tool, and even then the page warns against individual build grants.

**Knight Foundation.** An open 2026 research competition that would fund this app was not confirmed. Knight has funded Northwestern journalism projects in the past, including a 2024 generative AI and news grant. That award is a different project. Do not cite it as a path for LDI.

### 5.5 What was not confirmed

1. A live total of posts in the archive, and an invoice that reconciles Mark's $20 a month report with the deploy runbook's $35 to $60 estimate for the always-on collector.
2. Whether Cloudflare Access is enabled.
3. The us-east-2 S3 Standard price, as distinct from the us-east-1 rate of $0.023 per GB-month.
4. Current Bedrock token rates for Haiku 5.5, as distinct from Anthropic's API rates.
5. The us-east-2 hourly price for a `g6.xlarge`. The $0.8048 figure is the us-east-1 list price.
6. A Perspective API price.
7. A Kellogg faculty research account policy, including whether $500 to $1,000 a month of AWS is an allowed charge. The office exists. The policy was not on the public pages.
8. Whether Stanley is eligible for any student fund.
9. An open IPR seed call, and whether an IPR Associate can apply. Billy's public profile lists him as an Associate.
10. Billy's tenure status, which the Buffett co lead rule requires. The 2027-02-15 deadline itself is on the Buffett page.
11. The next NNCI Collaborative Intelligence cycle.
12. A standing NICO seed grant.
13. Whether Digital Scholarship consultations extend to a social media corpus, beyond the service description on the library page.
14. When NSF will republish CSSI. The program page says there is no upcoming due date. The old December 1 line is not a live deadline.
15. When NSF will republish HNDS.
16. An open Knight Foundation program for this kind of data infrastructure.
17. A Sloan deadline or a Sloan amount for research software operations.
18. An Azure research credit amount. Google's faculty cap of $5,000 is published.

## 6. What feasible has to mean

Nour's question, and the question Billy expects from Kellogg, is what the value is at the end of the day. A feasible answer is a small set of facts, not a longer architecture description. The facts that would change a skeptic's mind are the following.

1. More than one research group has asked for data, and at least one request has been delivered. Daniel's 71,786 post file is the delivered example. Tony's two week file, once it exists, is the second. Two projects is a start. It is not a user base.
2. A person other than Mark has signed in and received a file without Mark writing the query by hand. That has not been recorded yet. Tony is the test.
3. The cost per delivered file is small and known. Section 4 puts a capped query at about $0.05 of Athena charges. The missing piece is the staff minutes. If a year long pull takes Mark half a day, that labor is the real cost, and it should be written down.
4. A paper, a preregistration, or a conjoint that used an LDI file. None is documented in this draft. Daniel's study is the closest candidate, and the outcome is a TODO.
5. The labeling layer, once it exists, agrees with human labels on a sample the researchers care about. Tony, Tessa, and Nour already did a version of this comparison on news text, with Jev and DeepSeek. The same comparison on Bluesky posts is the feasibility test for the $500 to $1,000 budget. Agreement on news text is not agreement on posts.
6. The login story Billy can repeat without a caveat. Today that story is Northwestern email plus an emailed 6 digit code, and a token check on the query API. The Cloudflare PIN is not confirmed as on.

Metrics to start tracking, before the next time someone asks. These are not collected in the repository today.

| Metric | Why it answers the skeptic |
| --- | --- |
| Named users who have signed up, and which Northwestern domain | Shows the audience is real and inside the access rule |
| Queries submitted, queries refused by the scan cap, queries that emailed a file | Separates interest from delivered data |
| Rows and bytes in each delivered file, and Athena bytes scanned | Ties use to the cost model |
| Staff minutes per file that exceeded the cap | Shows whether "5 to 10 minutes" survives contact with real requests |
| Monthly AWS and Cloudflare dollars, split into storage, Athena, ingestion compute, and labeling | Replaces the $20 report with a bill |
| Row counts by table, and the oldest and newest post time | Replaces the 1 to 2 billion range |
| Studies that used a file, and what they produced | The end of the day question |
| For any classifier, agreement with a human sample, and cost per 1,000 labeled posts | The growth budget |

A reasonable bar for a follow up conversation, and this is a recommendation rather than a funder's published rule, is three delivered files to at least two research groups, a one month bill with the split above, and one sentence on what Daniel or Tony did with the file. A paper is stronger, and it is not required to have the first conversation with Research Support.

## 7. Recommended next steps

In the order Billy should spend his conversations. MirrorView stays first. These are the LDI asks around that.

1. Email Kellogg Research Support at `rs@kellogg.northwestern.edu` and ask three things. Can a faculty research account pay about $500 to $1,000 a month for labeling. Mark reports about $20 a month to run what exists, and the deploy runbook estimates $35 to $60 for the always-on collector, so quote the invoice once it is attached. Can a Bluesky database be added to the Kellogg Data Cloud, and who would be allowed to query it. Who inside Kellogg, besides Research Support, decides on a tool that several faculty might use. Attach section 1, the Daniel counts, and the cost table in section 4. Do not attach this whole draft unless they ask.
2. Open a Northwestern IT cloud consult, through the Research Cloud Consult linked from the [cloud support page](https://rcdsdocs.it.northwestern.edu/systems/Cloud/cloud-support.html), and ask for a university AWS account in Billy's or the lab's chartstring. Mention the 4.5 percent discount and waived egress only as context. Ask them to say whether an AWS Cloud Credit for Research application should be filed, given that AWS will not fund ongoing lab operations. The sandbox is the wrong product, because it is not for research data.
3. Decide whether the Russell Sage letter on 2026-12-01 is a real attempt. It is the best grant match, and it needs a second discipline and a question about democracy, AI's social effects, or public data, with LDI as the instrument. If Billy does not have a co PI in mind, skip this cycle and use steps 1 and 2.
4. Attend or watch the Nexus Labs webinar on 2026-11-02 before writing anything. Submit a letter of intent on 2026-11-30 only if a second faculty member wants a project that could grow into external funding. A standalone request for cloud money will not match the published purpose.
5. Ask `nnci@northwestern.edu` whether another Collaborative Intelligence round is planned, and ask `ipr@northwestern.edu` whether a seed call is open to IPR associates. Billy's public profile lists him as an associate. Both are short emails. Neither should become a proposal until the answer is yes.
6. If a labeling pilot needs compute rather than cash, look at the NAIRR Pilot before buying a year of tokens. The allocation is 12 months, and the results have to be open. A Northwestern-only query app does not meet that rule. A public labeled sample might.
7. Ask a Northwestern research administrator to email `CSSIQueries@nsf.gov` and `sbe-hnds@nsf.gov` about the next publication. Both program pages say there is no upcoming due date. Do not write a CSSI proposal against 2026-12-01.
8. Email `crti@kellogg.northwestern.edu` only after Research Support, and only to ask whether a faculty grant can cover data infrastructure. Amount and deadline are unpublished.
9. Leave The Garage, the Global Poverty Research Lab, the Ryan fund, OpenAI's $1,000, and Anthropic's life sciences credits off the first round of calls. Buffett's Global Working Group deadline is 2027-02-15, and it is a later conversation if a tenured co lead exists. They are in section 5 so Billy can explain why they were considered.

## 8. Open questions for Mark and Billy

1. Can Mark attach a one month AWS and Cloudflare bill, split the way section 6 asks, before the meeting?
2. What are the current row counts, and do the 1 to 2 billion posts include likes, reposts, and follows or only posts?
3. Is Cloudflare Access on, or is the live gate still Supabase plus the emailed code?
4. Did Daniel use the September file in a conjoint, and is there a result Billy can mention without sharing post text?
5. Has Tony signed up, and what did the two week file contain?
6. Does Billy want the labeling pilot framed as help for Tony, Tessa, and Nour, or as a general service? The first framing is easier to defend, because the users and the label comparison already exist.
7. Is there a second faculty member, in another discipline, who would co lead a Russell Sage or Nexus proposal? If not, those two deadlines should not drive the next month of work.
8. Which chartstring would pay a university AWS account, and who has to approve $500 to $1,000 a month?
9. What, if anything, should be shared outside Northwestern? Russell Sage's data infrastructure area wants public value. The current app is Northwestern email only. Those two facts have to be reconciled in any external proposal.
10. How much of Mark's time, and Stanley's time, is available if MirrorView stays the priority? A grant that assumes a full time build will not match the way this project is staffed.

## 9. Sources

Repository files, read in the working copy on 2026-10-28.

1. `README.md`
2. `lib/aws/constants.py`
3. `ui/cloudflare.config.ts`
4. `ui/src/lib/constants.ts`
5. `backend/auth.py`
6. `backend/agentic_search/query_postprocessing/check_scan_cost.py`
7. `cloudflare/access/apply_preview_access.py`
8. `docs/runbooks/HOW_TO_ENABLE_SELF_SERVE_SIGNUP.md`
9. `docs/runbooks/HOW_TO_ENABLE_DDOS_PROTECTION.md`
10. `docs/runbooks/HOW_TO_DEPLOY_TO_CLOUDFLARE.md`
11. `docs/runbooks/HOW_TO_ADD_A_USER.md`
12. `docs/runbooks/agentic_search_keyword_matching.md`
13. `docs/design_docs/2026-07-09_agentic_search_system_design.md`
14. `docs/design_docs/2026-07-13_bluesky_ingestion_jetstream.md`
15. `docs/design_docs/2026-07-17_bluesky_backfill_app.md`
16. `docs/design_docs/2026-09-19_bluesky_backfill_merge.md`
17. `experiments/perspective_api_labeling_2026_08_11/README.md`

Use cases in sections 2.4 and 3 are from Mark's notes of a 2026-09-09 to 2026-09-11 email thread (Daniel, Billy, Nour, Mark) and Slack from 2026-10-22 to 2026-10-28 (Tony, Tessa, Nour, Mark), plus the 2026-10-08 labeling comparison. They are not in the repository.

Pages checked on 2026-10-28.

18. Kellogg Research Support, [https://www.kellogg.northwestern.edu/academics-research/research-support/](https://www.kellogg.northwestern.edu/academics-research/research-support/)
19. Kellogg Linux Cluster, [https://www.kellogg.northwestern.edu/academics-research/research-support/computing/kellogg-linux-cluster/](https://www.kellogg.northwestern.edu/academics-research/research-support/computing/kellogg-linux-cluster/)
20. Kellogg Data Cloud, [https://www.kellogg.northwestern.edu/academics-research/research-support/computing/kellogg-data-cloud/](https://www.kellogg.northwestern.edu/academics-research/research-support/computing/kellogg-data-cloud/)
21. Kellogg data hosting, [https://www.kellogg.northwestern.edu/academics-research/research-support/computing/kellogg-data-hosting/](https://www.kellogg.northwestern.edu/academics-research/research-support/computing/kellogg-data-hosting/)
22. Kellogg computational consulting, [https://www.kellogg.northwestern.edu/academics-research/research-support/services/computational-consulting/](https://www.kellogg.northwestern.edu/academics-research/research-support/services/computational-consulting/)
23. Kellogg Behavioral Lab researcher FAQ, [https://www.kellogg.northwestern.edu/academics-research/research-support/behavioral-research/kellogg-researcher/faq-researcher/](https://www.kellogg.northwestern.edu/academics-research/research-support/behavioral-research/kellogg-researcher/faq-researcher/)
24. Kellogg PhD research funding, [https://www.kellogg.northwestern.edu/doctoral-intranet/student-services/research-funding-resources/](https://www.kellogg.northwestern.edu/doctoral-intranet/student-services/research-funding-resources/)
25. Kellogg research fellow applications, [https://www.kellogg.northwestern.edu/academics-research/research-support/research-fellows/apply/](https://www.kellogg.northwestern.edu/academics-research/research-support/research-fellows/apply/)
26. Global Poverty Research Lab funding, [https://www.kellogg.northwestern.edu/academics-research/global-poverty-research-lab/research-support/funding-opportunities-grants/](https://www.kellogg.northwestern.edu/academics-research/global-poverty-research-lab/research-support/funding-opportunities-grants/)
27. Quest access and allocations, [https://www.it.northwestern.edu/departments/it-services-support/research/computing/quest/quest-access-and-allocations.html](https://www.it.northwestern.edu/departments/it-services-support/research/computing/quest/quest-access-and-allocations.html)
28. ColdFront transition, [https://rcdsdocs.it.northwestern.edu/systems/coldfront/transition-to-coldfront.html](https://rcdsdocs.it.northwestern.edu/systems/coldfront/transition-to-coldfront.html)
29. Requesting a cloud account, [https://rcdsdocs.it.northwestern.edu/systems/Cloud/cloud-accounts.html](https://rcdsdocs.it.northwestern.edu/systems/Cloud/cloud-accounts.html)
30. Cloud support and credits, [https://rcdsdocs.it.northwestern.edu/systems/Cloud/cloud-support.html](https://rcdsdocs.it.northwestern.edu/systems/Cloud/cloud-support.html)
31. Research Computing Cloud service, [https://services.northwestern.edu/TDClient/30/Portal/Requests/Service/86/Research-Computing-Cloud](https://services.northwestern.edu/TDClient/30/Portal/Requests/Service/86/Research-Computing-Cloud)
32. Northwestern Nexus Labs, [https://sites.northwestern.edu/nexuslabs/](https://sites.northwestern.edu/nexuslabs/)
33. Northwestern Now on the Office for Research investments, 2026-10-13, [https://news.northwestern.edu/stories/2026/10/northwestern-invests-in-the-future-of-discovery](https://news.northwestern.edu/stories/2026/10/northwestern-invests-in-the-future-of-discovery)
34. NNCI call, [https://nnci.northwestern.edu/news-events/news/2026/call-for-proposals-nnci-collaborative-intelligence-research-awards.html](https://nnci.northwestern.edu/news-events/news/2026/call-for-proposals-nnci-collaborative-intelligence-research-awards.html)
35. NNCI RFP pdf, [https://nnci.northwestern.edu/docs/rfp-nnci-collaborative-intelligence-research-awards.pdf](https://nnci.northwestern.edu/docs/rfp-nnci-collaborative-intelligence-research-awards.pdf)
36. IPR seed grant story, 2026-08-06, [https://www.ipr.northwestern.edu/news/2026/seed-grants-carve-paths-to-possible-future-funding.html](https://www.ipr.northwestern.edu/news/2026/seed-grants-carve-paths-to-possible-future-funding.html)
37. Buffett Global Working Group grants, [https://buffett.northwestern.edu/programs/faculty-funding/global-working-group-grants/](https://buffett.northwestern.edu/programs/faculty-funding/global-working-group-grants/)
38. The Garage programs, [https://www.thegarage.northwestern.edu/programs](https://www.thegarage.northwestern.edu/programs)
39. Northwestern Libraries digital scholarship, [https://www.library.northwestern.edu/use-the-libraries/research-teaching/digital-scholarship/](https://www.library.northwestern.edu/use-the-libraries/research-teaching/digital-scholarship/). The Academic Innovation organization-chart URL 404'd on 2026-10-28 and is not used.
40. Office for Research internal funding index, [https://ord.northwestern.edu/funding/pilot-and-seed-funding-programs.html](https://ord.northwestern.edu/funding/pilot-and-seed-funding-programs.html)
41. Ryan Family Research Acceleration Fund notice, [https://research.soc.northwestern.edu/pat-and-shirley-ryan-family-research-acceleration-fund-due-mar-1-2026/](https://research.soc.northwestern.edu/pat-and-shirley-ryan-family-research-acceleration-fund-due-mar-1-2026/)
42. NUCATS and NICO symposium, [https://www.nucats.northwestern.edu/about/news/2026/nucats-and-nico-spark-collaboration.html](https://www.nucats.northwestern.edu/about/news/2026/nucats-and-nico-spark-collaboration.html)
43. Russell Sage MOS announcement, [https://www.russellsage.org/news/new-margaret-olivia-sage-grants-competition](https://www.russellsage.org/news/new-margaret-olivia-sage-grants-competition)
44. Russell Sage MOS RFP, [https://www.russellsage.org/research/priorities/mos-grants/rfp-mos-grants](https://www.russellsage.org/research/priorities/mos-grants/rfp-mos-grants)
45. Russell Sage eligibility, [https://www.russellsage.org/apply/info/eligibility](https://www.russellsage.org/apply/info/eligibility)
46. Russell Sage budget, [https://www.russellsage.org/apply/info/budget](https://www.russellsage.org/apply/info/budget)
47. Russell Sage deadlines, [https://www.russellsage.org/apply/application-deadlines](https://www.russellsage.org/apply/application-deadlines)
48. Russell Sage computational social science initiative, closed to unsolicited proposals, [https://www.russellsage.org/research/completed/computational-social-science-special-initiative](https://www.russellsage.org/research/completed/computational-social-science-special-initiative)
49. NSF 22-632, CSSI, [https://www.nsf.gov/funding/opportunities/cssi-cyberinfrastructure-systems-scientific-innovation/nsf22-632/solicitation](https://www.nsf.gov/funding/opportunities/cssi-cyberinfrastructure-systems-scientific-innovation/nsf22-632/solicitation)
50. NSF HNDS program page, [https://www.nsf.gov/funding/opportunities/hnds-human-networks-data-science](https://www.nsf.gov/funding/opportunities/hnds-human-networks-data-science)
51. Grants.gov HNDS listing, [https://simpler.grants.gov/opportunity/348260](https://simpler.grants.gov/opportunity/348260)
52. AWS Cloud Credit for Research, [https://aws.amazon.com/government-education/research-and-technical-computing/cloud-credit-for-research/](https://aws.amazon.com/government-education/research-and-technical-computing/cloud-credit-for-research/)
53. AWS Cloud Credit for Research FAQ, [https://aws.amazon.com/government-education/research-and-technical-computing/cloud-credit-for-research/faqs/](https://aws.amazon.com/government-education/research-and-technical-computing/cloud-credit-for-research/faqs/)
54. AWS apply page, including the Free Tier change, [https://pages.awscloud.com/aws-cloud-credit-for-research.html](https://pages.awscloud.com/aws-cloud-credit-for-research.html)
55. Amazon Athena pricing, [https://aws.amazon.com/athena/pricing/](https://aws.amazon.com/athena/pricing/)
56. Amazon S3 pricing, [https://aws.amazon.com/s3/pricing/](https://aws.amazon.com/s3/pricing/)
57. S3 Standard us-east-1 rate extract, 2026-10-15, [https://www.devzero.io/blog/aws-s3-pricing](https://www.devzero.io/blog/aws-s3-pricing)
58. Anthropic model pricing, [https://platform.claude.com/docs/en/about-claude/pricing](https://platform.claude.com/docs/en/about-claude/pricing)
59. Google Cloud research credits, [https://edu.google.com/intl/ALL_us/programs/credits/research/](https://edu.google.com/intl/ALL_us/programs/credits/research/)
60. Microsoft Azure for academic research, [https://www.microsoft.com/en-us/azure-academic-research/](https://www.microsoft.com/en-us/azure-academic-research/)
61. OpenAI Researcher Access Program FAQ, [https://help.openai.com/en/articles/10139500-researcher-access-program-faq](https://help.openai.com/en/articles/10139500-researcher-access-program-faq)
62. Anthropic AI for Science, [https://support.claude.com/en/articles/11199177-anthropic-s-ai-for-science-program](https://support.claude.com/en/articles/11199177-anthropic-s-ai-for-science-program)
63. Sloan Foundation, Open Source in Science, [https://sloan.org/programs/digital-technology/open-source-in-science](https://sloan.org/programs/digital-technology/open-source-in-science)
64. CSSI program page, no upcoming due date, [https://www.nsf.gov/funding/opportunities/cssi-cyberinfrastructure-systems-scientific-innovation](https://www.nsf.gov/funding/opportunities/cssi-cyberinfrastructure-systems-scientific-innovation)
65. NAIRR Pilot allocations, [https://nairrpilot.org/opportunities/allocations](https://nairrpilot.org/opportunities/allocations)
66. Google Cloud research credits FAQ, [https://support.google.com/google-cloud-higher-ed/answer/10723679?hl=en](https://support.google.com/google-cloud-higher-ed/answer/10723679?hl=en)
67. CRTI opportunities, [https://www.kellogg.northwestern.edu/academics-research/research-technology-innovation/opportunities/](https://www.kellogg.northwestern.edu/academics-research/research-technology-innovation/opportunities/)
68. Northwestern IT collaborative project support, [https://www.it.northwestern.edu/departments/it-services-support/research/data-science-statistics-visualization/collaborative-project-support.html](https://www.it.northwestern.edu/departments/it-services-support/research/data-science-statistics-visualization/collaborative-project-support.html)
69. NNCI 2026 awardees, [https://nnci.northwestern.edu/research/collaborative-intelligence-research-awards.html](https://nnci.northwestern.edu/research/collaborative-intelligence-research-awards.html)
70. William Brady, IPR profile, [https://www.ipr.northwestern.edu/who-we-are/faculty-experts/william-brady.html](https://www.ipr.northwestern.edu/who-we-are/faculty-experts/william-brady.html)
71. Libraries, digital scholarship, [https://www.library.northwestern.edu/use-the-libraries/research-teaching/digital-scholarship/](https://www.library.northwestern.edu/use-the-libraries/research-teaching/digital-scholarship/)
