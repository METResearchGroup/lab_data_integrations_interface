<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [The Illinois Social Attitudes Aggregate Corpus (ISAAC): An Open Tool and Reproducible Pipeline for Analyzing Social Group Discourse at Scale](#the-illinois-social-attitudes-aggregate-corpus-isaac-an-open-tool-and-reproducible-pipeline-for-analyzing-social-group-discourse-at-scale)
  - [Abstract](#abstract)
  - [Introduction](#introduction)
  - [The Illinois Social Attitudes Aggregate Corpus (ISAAC)](#the-illinois-social-attitudes-aggregate-corpus-isaac)
  - [Validation Strategy](#validation-strategy)
  - [Method](#method)
    - [Overview of Corpus Construction](#overview-of-corpus-construction)
    - [Ethical Approval](#ethical-approval)
    - [Data Source](#data-source)
    - [Computational Infrastructure](#computational-infrastructure)
    - [Filtering](#filtering)
      - [Step 1: Keyword Matching](#step-1-keyword-matching)
      - [Step 2: Language Filtering](#step-2-language-filtering)
      - [Step 3: Relevance Classification](#step-3-relevance-classification)
      - [Step 4: Complex Pattern Matching](#step-4-complex-pattern-matching)
    - [Filtering Quality Assessment](#filtering-quality-assessment)
    - [Metadata](#metadata)
      - [Reddit Metadata](#reddit-metadata)
      - [User Location Estimation](#user-location-estimation)
      - [Anonymization](#anonymization)
    - [Semantic Labels](#semantic-labels)
      - [Moralization](#moralization)
      - [Sentiment](#sentiment)
      - [Emotion](#emotion)
      - [Generalization](#generalization)
    - [Corpus Access](#corpus-access)
    - [Data Use Agreement](#data-use-agreement)
    - [Adapting and Extending ISAAC](#adapting-and-extending-isaac)
    - [Analytic Strategy](#analytic-strategy)
  - [Results](#results)
    - [Filtering Pipeline Performance](#filtering-pipeline-performance)
    - [Key Descriptive Statistics](#key-descriptive-statistics)
    - [Location Model Evaluation](#location-model-evaluation)
    - [Semantic Label Validation and Performance](#semantic-label-validation-and-performance)
      - [Moralization](#moralization-1)
      - [Sentiment](#sentiment-1)
      - [Emotion](#emotion-1)
      - [Generalization](#generalization-1)
    - [Corpus-Level Validation](#corpus-level-validation)
      - [Volume-Based Validation](#volume-based-validation)
      - [Semantic Validation](#semantic-validation)
  - [Discussion](#discussion)
    - [ISAAC’s Scope of Intended Use](#isaacs-scope-of-intended-use)
    - [Limitations and Possibilities for Expansion](#limitations-and-possibilities-for-expansion)
  - [Conclusion](#conclusion)
  - [Acknowledgments](#acknowledgments)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# The Illinois Social Attitudes Aggregate Corpus (ISAAC): An Open Tool and Reproducible Pipeline for Analyzing Social Group Discourse at Scale

> **Source:** https://arxiv.org/pdf/2609.27059  
> **Coverage:** pages 1–53 (through Conclusion / Acknowledgments; appendices excluded)  
> **Purpose:** Markdown outline with key research/design questions per section, as a **template for a similar lab-data-integrations-interface paper**. Emphasize methods and pipeline design over result numbers. Skip ORCID / Author Note boilerplate.

---

## Abstract

Key questions:

1. What resource is being introduced, and for what scientific problem?
2. What scale, time span, and social-group coverage does the corpus claim?
3. How was relevance ensured, and what labels accompany each post?
4. How can researchers access and extend the infrastructure?

How they answered these:

Positioned ISAAC as an open, modular Reddit corpus of social-group discourse with a human-audited multi-step filter, algorithmic home-region and semantic annotations, convergent external validation, and dual coding-free / programmatic access paths (website, SQL playground, Python package, HuggingFace).

---

## Introduction

*(Untitled in the paper under APA convention; substance is the opening argument.)*

Key questions:

1. Why do social-group attitudes matter across social-science disciplines, and how is “attitude” defined here?
2. What traditional methods study these attitudes, and what do they share that limits ecological validity?
3. What new questions become tractable with computational analysis of organic online discourse?
4. Why does methodological fragmentation block cumulative progress in computational social-group research?
5. What four recurring weaknesses does ISAAC target (filtering noise, single-model labels, missing convergent validation, reliance on curated/formal text)?
6. What existing corpora partially address these needs, and what joint requirements remain unmet?

How they answered these:

Synthesized cross-disciplinary attitude research and contrasted researcher-elicited methods with computational social science on spontaneous text; framed field maturation via shared infrastructure analogies (ImageNet, BNC, CHILDES, SNAP); diagnosed four pipeline/validation failures; surveyed size-, annotation-, bias-probe-, and longitudinal resources; used Table 1 to situate ISAAC against those gaps (naturalistic source, longitudinal span, multi-group curation, multi-label descriptors + semantics, convergent validation, multi-format access).

---

## The Illinois Social Attitudes Aggregate Corpus (ISAAC)

Key questions:

1. What is in the corpus (units, years, six social-group distinctions, label families)?
2. What five design pillars make it suitable for large-scale computational social science?
3. Which classes of empirical questions does this design unlock?
4. What three high-level limitations are acknowledged up front?

How they answered these:

Defined the filtered Reddit submission/comment corpus and variable families (platform metadata, anonymized user ID + hierarchical location, moralization / sentiment / emotion / generalization); argued five pillars—conservative multi-stage filtering with a residual-irrelevance target, scale + continuous coverage under one pipeline, parallel multi-group + broad labels, tiered access for coding and non-coding users, and an open modular construction pipeline; mapped those features to cross-category, temporal, and spatial research uses; flagged aggregate-level focus, language-vs-latent-attitude gap, and single-platform (Reddit) constraints while noting modularity as the mitigation path.

---

## Validation Strategy

Key questions:

1. How is internal (component and end-to-end) fidelity established?
2. How is construct / convergent validity established against external benchmarks?
3. What four categories of macro-societal data serve as external anchors?

How they answered these:

Combined human audits of stratified samples, ensemble agreement checks, and held-out performance for in-house models (releasing validation data with the corpus) with external mapping of volume and semantic markers onto cultural flashpoints, state ballot outcomes, internet search trends, and national survey series.

---

## Method

### Overview of Corpus Construction

Key questions:

1. What are the major construction phases?
2. What three variable families ship with each entry?

How they answered these:

Described a three-phase pipeline (Figure 1): four-step relevance filtering from a raw Reddit archive; attachment of Reddit metadata, in-house user metadata (anonymized ID + hierarchical location), and semantic labels (Table 2 / `variable_list.md`); then access and release packaging.

### Ethical Approval

Key questions:

1. Was IRB review required, and what ethical posture guided development?

How they answered these:

Reported University of Nebraska–Lincoln IRB determination of non–human-participants research under 45 CFR 46.102, while following social-media research ethics guidance (e.g., anonymization; Appendix A).

### Data Source

Key questions:

1. What archive supplied the raw text, and what inclusion/exclusion policy was chosen?

How they answered these:

Built from preexisting Pushshift-formatted Reddit comment and submission archives; retained all content without bot filtering or minimum length so downstream users can impose stricter criteria.

### Computational Infrastructure

Key questions:

1. What compute was used to build and demonstrate the pipeline?

How they answered these:

Developed locally and on HPC (early A100 cluster; release build on Stony Brook AI Innovation Institute with large CPU/GPU parallelism); shipped an interactive website demo of the end-to-end pipeline on a subset.

### Filtering

Key questions:

1. What overall filtering objective and step sequence extract group-relevant discourse?

How they answered these:

Ran a four-step cascade optimized to minimize retained irrelevance (Figure 1), detailed in the following substeps.

#### Step 1: Keyword Matching

Key questions:

1. Why keyword matching across the whole platform rather than subreddit restriction?
2. How were keyword lists built and maintained at archive scale?

How they answered these:

Used expansive, iteratively curated keyword lists for both poles of each distinction (thesauri, Wikipedia slur/slang lists, stratified-sample revisions; released in the Git repo); preferred exact match over heavy regex at this stage for tractability on billions of posts (Appendix E.3).

#### Step 2: Language Filtering

Key questions:

1. How is non-English content removed when keywords collide across languages?

How they answered these:

Kept only posts classified as English by fastText for speed at archive scale.

#### Step 3: Relevance Classification

Key questions:

1. How are irrelevant keyword senses removed?
2. How are per-group classifiers trained, audited, and retrained to a fidelity threshold?

How they answered these:

Fine-tuned a separate RoBERTa relevance classifier per social-group distinction on ~1,500 year- and keyword-count–stratified posts double-annotated by trained raters (Appendix B); treated unclear labels as irrelevant and resolved residual disagreements toward relevance; enforced conditional retraining and conservative thresholds when audits exceeded the 10% residual-irrelevance design target.

#### Step 4: Complex Pattern Matching

Key questions:

1. What residual structural noise survives classifiers, and how is it removed at scale?

How they answered these:

Applied group-specific regex pattern sets (names, pop-culture phrases, etc.) developed from stratified survivors, using a parallelized fast matcher once volume was reduced (Appendix E; patterns in repo).

### Filtering Quality Assessment

Key questions:

1. How is filtering quality monitored and when does development stop?
2. How is rater reliability and transfer to submissions checked?

How they answered these:

Ran an ongoing human annotation loop on stratified samples after each stage (and after retraining); double-annotated comment samples at process start/end; drew submission transfer samples because thresholds were optimized on comments; stopped only when residual irrelevance met the 10% target across post types and all six distinctions.

### Metadata

#### Reddit Metadata

Key questions:

1. Which platform fields are retained, and what privacy constraint applies to identifiers?

How they answered these:

Kept post/parent IDs, GMT time, subreddit, score, post type, and matched keywords for thread reconstruction and linkage; prohibited re-linking identifiers to identifiable Reddit accounts (Appendix A).

#### User Location Estimation

Key questions:

1. How are training labels obtained without ground-truth geolocation?
2. How does the hierarchical model assign and fall back across geographic tiers?
3. What validation evidence and access controls accompany location models?

How they answered these:

Auto-extracted self-disclosures for training labels; trained a hierarchical model on full posting history (word usage, subreddit participation, timestamps) that first separates U.S./non-U.S., then U.S. states (incl. DC) vs. four world regions, retaining coarser or unknown labels when fine-tier confidence is weak; planned five validation strands (manual audit of auto-labels, held-out users, masked self-disclosure ablation, confidence calibration, marriage-equality vote spikes); withheld training data for privacy; released models under a Model Use Agreement by request (Appendix D).

#### Anonymization

Key questions:

1. How are usernames replaced while preserving longitudinal/spatial user linkage?

How they answered these:

Merged comment and submission streams per distinction into a time-ordered set; replaced usernames with persistent random IDs shared across posts and all six distinctions; did not distribute the username↔ID map.

### Semantic Labels

#### Moralization

Key questions:

1. Why train on MFRC, and why a binary rather than foundation-level label?
2. How will validity of moralization labels be probed in the corpus?

How they answered these:

Tuned a classifier on Moral Foundations Reddit Corpus (same platform), collapsing annotations to moralized vs. not (majority vote; ties toward moralized); chose binary for more even performance and broader theoretical agreement; released the model and held-out MFRC metrics; planned distributional contrasts across distinctions/poles (e.g., contested domains more moralized).

#### Sentiment

Key questions:

1. Why use multiple sentiment systems instead of one?
2. How is ensemble consistency and directional validity assessed?

How they answered these:

Applied three deliberately different tools (VADER, TextBlob, Stanza) as separate columns so users can ensemble, agree-gate, or study disagreement; evaluated internal consistency on a year×group stratified subsample (~60k posts); planned pole contrasts expecting more negative tone for marginalized poles.

#### Emotion

Key questions:

1. Why ensemble three emotion models, and what scores are released?
2. How are reliability and validity of emotion labels established?

How they answered these:

Ran three pretrained emotion classifiers jointly so each of six basic emotions plus neutral has three estimates; stored model-specific 0–1 scores for ensemble/disagreement analyses; measured cross-model agreement and planned pole contrasts expecting more negative emotions for marginalized groups.

#### Generalization

Key questions:

1. How is linguistic generalization operationalized at clause level?
2. What outputs ship per post, and where is model documentation?

How they answered these:

Modeled genericity, eventivity, and (for eventives) boundedness/habituality via an in-house clause-segmentation and labeling suite; counted non-statements separately when features are undefined; released clause lists, per-clause labels, and feature counts/proportions; reported held-out metrics with full training docs in a companion paper.

### Corpus Access

Key questions:

1. What five access pathways serve different skill levels and scales?

How they answered these:

Provided (1) coding-free website downloads/stratified samples (CSV), (2) SQL playground for limited queries, (3) `isaac-data` PyPI package with resumable selective loads, (4) HuggingFace Datasets/Models, (5) scripted direct-download instructions (Appendix F).

### Data Use Agreement

Key questions:

1. What legal/ethical constraints govern use of data, tools, and scripts?

How they answered these:

Governed all pathways with a DUA developed with UIUC Legal Counsel (Appendix A): non-commercial academic research only; bans on re-identification, generative AI training, harmful/surveillant uses; limits on redistribution; requirement to use official channels.

### Adapting and Extending ISAAC

Key questions:

1. How can others reuse in-house models without coding, and at what scale?
2. Which pipeline components can be swapped for new groups, languages, platforms, or labels?

How they answered these:

Released modular public scripts; hosted HuggingFace Spaces for relevance, moralization, and generalization labeling (quota-limited; recommend local accel for large jobs); documented swap points—keyword lists, language target, custom relevance/location training, stratified sampling/IRR tools, and non-Reddit readers—while noting discontinued broad Pushshift access makes the released corpus a durable historical slice (Appendix E).

### Analytic Strategy

Key questions:

1. How are model performance, census descriptives, and subsample analyses reported?
2. Which metrics and corpus-level validation checks structure the Results?

How they answered these:

Used held-out/audit point estimates for models; census descriptives without CIs for full-corpus counts; exact tests, native metrics (κ, F1, ρ, r), and bootstrapped 95% CIs for independent/stratified units; emphasized macro-averaged F1 for multi-class balance; skipped power analysis (estimation/validation focus); predefined three macro checks—volume vs. Google Trends, event-locked monthly volumes (plus state marriage-equality location check), and semantic cross-label plus Gallup-aligned sexuality sentiment composite.

---

## Results

### Filtering Pipeline Performance

Key questions:

1. Was the <10% residual-irrelevance target met, and did quality transfer to submissions?
2. How did required pipeline depth and interrater agreement vary by distinction?

How they answered these:

Documented per-distinction step counts (some one-pass; ability/race/skin tone needed reinforced classification and secondary pattern passes); reported final double-rated comment audits under lenient vs. stringent relevance rules and single-rater submission transfer audits (Table 3); pointed to Appendix C for classifier metrics and step-by-step error reduction.

### Key Descriptive Statistics

Key questions:

1. What is the composition of the released corpus by post type, group, and year?

How they answered these:

Reported submission vs. comment shares, relative volumes across the six distinctions (Figure 3), and growth of entries over collection years (Figure 4)—census-style descriptives rather than inferential tests.

### Location Model Evaluation

Key questions:

1. How accurate are auto-extracted training disclosures and held-out hierarchical predictions?
2. How much does performance depend on overt place names (masking ablation)?
3. How are confidence thresholds and calibration used in the released labels?

How they answered these:

Summarized Appendix D: manual audit of disclosure labels; held-out macro F1/accuracy at U.S./non-U.S., region, and state tiers; top-k and centroid-distance error sweeps (Table 4); re-evaluation after stripping place names; conservative tiered confidence assignment across authors; calibration/recalibration mappings shipped with the corpus.

### Semantic Label Validation and Performance

Key questions:

1. How are off-the-shelf vs. in-house labelers evaluated differently?

How they answered these:

Split Table 5 into published creator benchmarks (sentiment/emotion) vs. new held-out evaluations (moralization, generalization), plus ensemble agreement on the stratified subsample (Figure 5).

#### Moralization

Key questions:

1. How does the custom moralization classifier perform on held-out MFRC?

How they answered these:

Reported precision/recall/F1 and macro metrics on a 10% MFRC holdout.

#### Sentiment

Key questions:

1. How consistent are the three sentiment tools, and is the ensemble usable?

How they answered these:

Compared pairwise agreement and baseline skew across VADER/TextBlob/Stanza; tested baseline-adjusted agreement; reported three-model ICC on the stratified subsample relative to known human-agreement ceilings for social-media sentiment.

#### Emotion

Key questions:

1. How much do models agree on categorical vs. continuous emotion scores, and how is consensus formed at corpus scale?

How they answered these:

Reported pairwise κ on top labels (before/after rate equalization), ICCs on continuous intensities, and majority-vote / unanimous consensus rates when applied corpus-wide.

#### Generalization

Key questions:

1. How well do segmentation and feature classifiers perform on held-out gold clauses?

How they answered these:

Cited companion-paper metrics for clause-span coverage, 18-way situation-entity classification, and collapsed F1/accuracy for genericity, eventivity, and boundedness/habituality.

### Corpus-Level Validation

#### Volume-Based Validation

Key questions:

1. Does monthly discourse volume track independent search interest?
2. Do national group-linked events produce detectable volume spikes after growth adjustment?
3. Do location labels capture localized spikes around state marriage-equality votes?

How they answered these:

**Search Interest.** Correlated monthly ISAAC volumes with Google Trends (level and first-difference); for sexuality, also compared platform-share–normalized series to separate platform-growth artifacts (Figure 6).  
**National Event Spikes.** Compared event-month volumes to trailing baselines with post-2013 percentiles and share-adjusted volumes for group-specific anchors (Figure 7), treating age as an informative null.  
**Localized Event Spikes.** Indexed sexuality volume for voting-state users vs. non-voting-state medians around nine ballot measures; tested consistent outperformance (sign test / bootstrap; Figure 8; Appendix C.4).

#### Semantic Validation

Key questions:

1. Do moralization, sentiment, and emotion profiles differentiate groups and poles in theoretically expected ways?
2. Does sexuality discourse tone align with national public opinion over time?

How they answered these:

**Inter-Variable Alignment.** Used volume-weighted samples and the stratified subsample to profile moralization and affect by distinction, moralized vs. non-moralized emotion coupling, and marginalized vs. dominant pole sentiment (Table 6).  
**Validation Against National Public Opinion.** Built an annual three-tool sexuality sentiment composite and correlated it with Gallup marriage-equality support, also checking first-difference co-movement (Figure 9; Appendix C.4).

---

## Discussion

Key questions:

1. How do the major design choices (filtering, location, multi-model semantics) follow from the goal of scalable yet high-quality discourse study?
2. What multi-level validity argument ties component audits to corpus-level external convergence?

How they answered these:

Restated the single goal—at-scale study without sacrificing measurement quality or flexibility—and mapped aggressive multi-stage filtering, conservative tiered location, and multi-model semantics to that goal; argued validity via convergence across component human agreement / residual-irrelevance / model metrics and corpus-level search, event, and survey alignments rather than any single comparison.

### ISAAC’s Scope of Intended Use

Key questions:

1. Where does ISAAC sit relative to surveys and implicit-measure repositories?
2. How does a fixed public pipeline enable cumulative, cross-category, temporal, spatial, and theory-testing work?

How they answered these:

Positioned ISAAC as unobtrusive naturalistic text complementary to ANES/GSS and large implicit repositories for triangulation; argued shared infrastructure ends study-specific silos; stressed identical multi-group processing for artifact-free comparisons; outlined interrupted time-series / DiD and lead-lag designs on the 17-year window; described state–year spatial linkage to regional attitudes and outcomes; pointed semantic labels toward tests of moral outrage, generic/essentialist language, and ML training/evaluation without oversimplified composites.

### Limitations and Possibilities for Expansion

Key questions:

1. What structural limits bind all downstream use (platform, language, text≠attitude)?
2. Which design compromises are mitigated by releasing uncertainty and multi-model outputs?
3. Along what four axes can independent labs extend the open pipeline?

How they answered these:

Acknowledged Reddit demographics, English-only content, platform norms, and the gap from manifest discourse markers to latent attitudes (plus platform-dynamics confounders); treated sparse high-precision state labels and cross-model disagreement as deliberate compromises mitigated by confidence/recalibration artifacts and side-by-side model outputs; listed modular expansions—new keyword dictionaries, alternate platform loaders, multilingual filters, additional semantic labels—operationalized in the open repo (Appendix E).

---

## Conclusion

Key questions:

1. What integrated infrastructure claim does the paper close on?

How they answered these:

Summarized ISAAC as cumulative quantitative infrastructure: multi-decade multi-group text with temporal, geographic, and semantic indicators from a standardized pipeline; multi-pathway distribution; modular open architecture for expansion beyond current limits.

---

## Acknowledgments

Key questions:

1. Who contributed human validation and website development support?

How they answered these:

Credited named assistants for human validation and website development (and continued on the following page beyond the 1–53 scope).
