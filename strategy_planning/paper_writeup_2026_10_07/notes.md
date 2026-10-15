# Notes while writing this

What are comparable datasets?
- Moral Foundations Twitter Corpus
- Civil Comments/Jigsaw
- Twitter Decahose/TweetsKB
- https://arxiv.org/pdf/2609.27059

What inference and modeling do we need to do?

- I can design the data models and whatnot for the downstream parts of the codebase.
- I'd like to use Jev or Jev-like models for the large-scale labeling parts of this.

Will treat that as a black box and we'll see how well it does.

We already know that Jev is better than the Perspective API for calibrated moral outrage.

Key benefits / motivation

- one benefit of this approach and our work is that we always have up-to-date data that's not in the LLM pretraining window. (live Bluesky jetstream plus historical backfill, so researchers get current social data that post-dates any model's training cutoff. LLMs can't answer questions about it from memorized knowledge, and the dataset stays valuable as models age.)
