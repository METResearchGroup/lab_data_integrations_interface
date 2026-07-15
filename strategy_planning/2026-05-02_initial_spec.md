<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Initial spec details](#initial-spec-details)
  - [Scope for v1](#scope-for-v1)
    - [In-scope](#in-scope)
    - [Fast-follow](#fast-follow)
    - [Out-of-scope (longer-term build)](#out-of-scope-longer-term-build)
  - [V1 details](#v1-details)
    - [Step 1: Create integration-specific support](#step-1-create-integration-specific-support)
      - [Bluesky](#bluesky)
        - [Getting familiar with Bluesky](#getting-familiar-with-bluesky)
        - [Creating the Jetstream](#creating-the-jetstream)
        - [Getting live posts that meet certain criteria](#getting-live-posts-that-meet-certain-criteria)
      - [Reddit](#reddit)
      - [Twitter](#twitter)
    - [Step 2: Create a unified interface across integrations](#step-2-create-a-unified-interface-across-integrations)
  - [V2 details](#v2-details)
    - [Deploy the API](#deploy-the-api)
    - [Create a frontend](#create-a-frontend)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Initial spec details

Problem: We want a way to reduce the duplicated work related to gathering and scraping data. Academics write the same boilerplate code over and over to scrape data from Twitter, Bluesky, and Reddit.

Ideally we'd have a single interface to do each.

## Scope for v1

### In-scope

- Job scripts for running very specific integrations. We have a use case, the Mirrorview project, that we want to support at the start.

### Fast-follow

- Rewrite to a more consistent interface structure.
- A basic FastAPI app, run locally.
- Deploy ot AWS App Runner

### Out-of-scope (longer-term build)

- Storing the data.

## V1 details

### Step 1: Create integration-specific support

We want to be able to create scripts to get data from Bluesky, Reddit, and Twitter. Each of these will be a separate unit of work.

#### Bluesky

[Bluesky API Docs](https://docs.bsky.app/docs/get-started)

##### Getting familiar with Bluesky

Start with getting familiar with Bluesky. Steps:

1. Create an account on Bluesky. This will create credentials.
2. Get familiar with the basic data types on Bluesky, such as users, posts, and likes.
3. Have an experimental script that fetches the details for Professor Brady's account. The details we care to look at are basic profile identifiers (e.g., name, handle, number of followers, etc.), the last 10 posts he's posted/RTed, the last 10 users to follow him, and the last 10 users he followed.

##### Creating the Jetstream

Once familiar with Bluesky, move on to the next phase, which is to get familiar with [Bluesky Jetstream](https://docs.bsky.app/blog/jetstream). Basically, all data on Bluesky is "open-source" and publicly available (this is what makes it unique from, say, Twitter). Bluesky data is published to their [firehose](https://docs.bsky.app/docs/advanced-guides/firehose) in real-time (here is a [demo](https://firesky.tv/) of posts being published to Bluesky in real time). Please read through the docs and get familiar with how the firehose works, as this pattern will be important to understand for the next phase. [Here is a paper they published about it](https://bsky.social/about/bluesky-and-the-at-protocol-usable-decentralized-social-media-martin-kleppmann.pdf), having some cursory understanding of, for example, the Merkle Tree model would be helpful in working with Bluesky data. The Bluesky Jetstream is an app built on top of the firehose that makes it easier to access records that you care about. The [Github repo](https://github.com/bluesky-social/jetstream) has more details on how it works and also example code.

I [experimented with this](https://github.com/METResearchGroup/bluesky-research/pull/386) in the past myself, feel free to explore that PR (but beware that it's largely AI-generated experimental code).

Your task here is: what content a user likes is one of the few pieces of information that isn't easily found in the Bluesky public API. However, this information is made available via the firehose. Please figure out the last 10 posts that were liked by Dr. Brady's profile. This will give you "like" records, but these records will only have the ID of the like record and the ID of the user who liked the post. Importantly, it won't have any information about the post that was actually liked. To ameliorate this, you will need to use Jetstream to get this information.

Please create an experimental script for this and we'll verify against Dr. Brady's account to see if it matches.

If for some reason there's difficulty with doing this for Dr. Brady's account, please use [my Bluesky account instead](https://bsky.app/profile/markptorres.bsky.social).

##### Getting live posts that meet certain criteria

Using either the Jetstream or the live firehose, please create a CLI app that, given the following query params, returns a .csv file that grabs the latest posts that fit the criteria:

- handle: the handle of the user they care about
- keyword: keywords to look for in the post themselves.
- limit: total number of posts (default=50)

#### Reddit

(TBD: Needs to be discussed with Dr. Brady in more detail).

#### Twitter

(TBD: Needs to be discussed with Dr. Brady in more detail).

### Step 2: Create a unified interface across integrations

Create a single app interface that can be called via CLI commands and collects posts.

Shape would be something like:

- handle: the handle of the user
- subreddits (applicable to only Reddit)
- keyword: key words to search for
- limit: total to collect.

## V2 details

This is pending more detail once we see how the initial builds go, but some initial thoughts:

### Deploy the API

1. Create a FastAPI app around the unified interface.
2. Dockerize the app.
3. Deploy to AWS App Runner (will also require some Terraform).
4. Add API-specific improvements (auth, rate-limiting, caching).

### Create a frontend

Once the API exists, create a user interface on top. Should be easy to use and permit the same queries as previously mentioned.
