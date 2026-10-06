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
    - [ISAAC's Scope of Intended Use](#isaacs-scope-of-intended-use)
    - [Limitations and Possibilities for Expansion](#limitations-and-possibilities-for-expansion)
  - [Conclusion](#conclusion)
  - [Acknowledgments](#acknowledgments)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# The Illinois Social Attitudes Aggregate Corpus (ISAAC): An Open Tool and Reproducible Pipeline for Analyzing Social Group Discourse at Scale

> **Source:** https://arxiv.org/pdf/2609.27059  
> **Coverage:** pages 1 to 53 (through Conclusion / Acknowledgments; appendices excluded)  
> **Purpose:** Markdown outline with key research/design questions per section, as a **template for a similar lab-data-integrations-interface paper**. Emphasize methods and pipeline design over result numbers. Skip ORCID / Author Note boilerplate.

---

## Abstract

Key questions:

1. What resource is being introduced, and for what scientific problem?
2. What scale, time span, and social-group coverage does the corpus claim?
3. How was relevance ensured, and what labels accompany each post?
4. How can researchers access and extend the infrastructure?

How they answered these:

ISAAC is an open, modular Reddit corpus of social-group discourse. The authors built it with a human-audited multi-step filter, then attached algorithmic home-region and semantic annotations. They report convergent external validation, and they ship dual access paths that work without coding or with code (website, SQL playground, Python package, HuggingFace).

---

## Introduction

*(Untitled in the paper under APA convention; substance is the opening argument.)*

Key questions:

1. Why do social-group attitudes matter across social-science disciplines, and how is "attitude" defined here?
2. What traditional methods study these attitudes, and what do they share that limits ecological validity?
3. What new questions become tractable with computational analysis of organic online discourse?
4. Why does methodological fragmentation block cumulative progress in computational social-group research?
5. What four recurring weaknesses does ISAAC target (filtering noise, single-model labels, missing convergent validation, reliance on curated/formal text)?
6. What existing corpora partially address these needs, and what joint requirements remain unmet?

How they answered these:

The opening synthesizes cross-disciplinary attitude research and contrasts researcher-elicited methods with computational social science on spontaneous text. Shared infrastructure examples such as ImageNet, BNC, CHILDES, and SNAP show why fragmented methods stall cumulative progress. After diagnosing four pipeline and validation failures, and after surveying size-, annotation-, bias-probe-, and longitudinal resources, Table 1 situates ISAAC against the remaining gaps: naturalistic source, longitudinal span, multi-group curation, multi-label descriptors plus semantics, convergent validation, and multi-format access.

---

## The Illinois Social Attitudes Aggregate Corpus (ISAAC)

Key questions:

1. What is in the corpus (units, years, six social-group distinctions, label families)?
2. What five design pillars make it suitable for large-scale computational social science?
3. Which classes of empirical questions does this design unlock?
4. What three high-level limitations are acknowledged up front?

How they answered these:

The authors define the filtered Reddit submission and comment corpus and its variable families (platform metadata, anonymized user ID plus hierarchical location, moralization / sentiment / emotion / generalization). They ground suitability in five design pillars: conservative multi-stage filtering with a residual-irrelevance target; scale and continuous coverage under one pipeline; parallel multi-group coverage with broad labels; tiered access for coding and non-coding users; and an open modular construction pipeline. Those features map to cross-category, temporal, and spatial research uses. Up front they flag an aggregate-level focus, the gap between language and latent attitude, and single-platform (Reddit) constraints, and they treat modularity as the mitigation path.

---

## Validation Strategy

Key questions:

1. How is internal (component and end-to-end) fidelity established?
2. How is construct / convergent validity established against external benchmarks?
3. What four categories of macro-societal data serve as external anchors?

How they answered these:

The authors establish internal fidelity with human audits of stratified samples, ensemble agreement checks, and held-out performance for in-house models, and they release validation data with the corpus. For construct and convergent validity, they map volume and semantic markers onto cultural flashpoints, state ballot outcomes, internet search trends, and national survey series.

---

## Method

### Overview of Corpus Construction

Key questions:

1. What are the major construction phases?
2. What three variable families ship with each entry?

How they answered these:

Figure 1 shows a three-phase pipeline. The authors first reduce a raw Reddit archive with four-step relevance filtering. They then attach Reddit metadata, in-house user metadata (anonymized ID plus hierarchical location), and semantic labels (Table 2 / `variable_list.md`). Finally they package access and release materials.

### Ethical Approval

Key questions:

1. Was IRB review required, and what ethical posture guided development?

How they answered these:

University of Nebraska-Lincoln IRB determined the work was non-human-participants research under 45 CFR 46.102. Although that determination removed an IRB requirement, the authors still followed social-media research ethics guidance (e.g., anonymization; Appendix A).

### Data Source

Key questions:

1. What archive supplied the raw text, and what inclusion/exclusion policy was chosen?

How they answered these:

Raw text came from preexisting Pushshift-formatted Reddit comment and submission archives. The authors retained all content without bot filtering or a minimum length, so downstream users can impose stricter criteria themselves.

### Computational Infrastructure

Key questions:

1. What compute was used to build and demonstrate the pipeline?

How they answered these:

The authors developed the pipeline locally and on HPC (an early A100 cluster; the release build ran on the Stony Brook AI Innovation Institute with large CPU/GPU parallelism). They also shipped an interactive website demo of the end-to-end pipeline on a subset.

### Filtering

Key questions:

1. What overall filtering objective and step sequence extract group-relevant discourse?

How they answered these:

The authors ran a four-step cascade to minimize retained irrelevance (Figure 1). The substeps below give the details.

#### Step 1: Keyword Matching

Key questions:

1. Why keyword matching across the whole platform rather than subreddit restriction?
2. How were keyword lists built and maintained at archive scale?

How they answered these:

The authors used expansive, iteratively curated keyword lists for both poles of each distinction (thesauri, Wikipedia slur/slang lists, stratified-sample revisions; released in the Git repo). They preferred exact match over heavy regex at this stage because the archive holds billions of posts (Appendix E.3).

#### Step 2: Language Filtering

Key questions:

1. How is non-English content removed when keywords collide across languages?

How they answered these:

The authors kept only posts that fastText classified as English, which keeps the step fast at archive scale.

#### Step 3: Relevance Classification

Key questions:

1. How are irrelevant keyword senses removed?
2. How are per-group classifiers trained, audited, and retrained to a fidelity threshold?

How they answered these:

The authors fine-tuned a separate RoBERTa relevance classifier per social-group distinction on about 1,500 year- and keyword-count-stratified posts that trained raters double-annotated (Appendix B). Unclear labels count as irrelevant, and residual disagreements resolve toward relevance. When audits exceed the 10% residual-irrelevance design target, the authors apply conditional retraining and conservative thresholds.

#### Step 4: Complex Pattern Matching

Key questions:

1. What residual structural noise survives classifiers, and how is it removed at scale?

How they answered these:

The authors applied group-specific regex pattern sets (names, pop-culture phrases, and similar cases) developed from stratified survivors. Once volume was already reduced, a parallelized fast matcher applied those patterns at scale (Appendix E; patterns in repo).

### Filtering Quality Assessment

Key questions:

1. How is filtering quality monitored and when does development stop?
2. How is rater reliability and transfer to submissions checked?

How they answered these:

The authors ran an ongoing human annotation loop on stratified samples after each stage and after retraining. They double-annotated comment samples at process start and end. Because they optimized thresholds on comments, they drew submission transfer samples to check whether quality holds for submissions. They stopped only when residual irrelevance met the 10% target across post types and all six distinctions.

### Metadata

#### Reddit Metadata

Key questions:

1. Which platform fields are retained, and what privacy constraint applies to identifiers?

How they answered these:

The authors kept post/parent IDs, GMT time, subreddit, score, post type, and matched keywords for thread reconstruction and linkage. They prohibited re-linking identifiers to identifiable Reddit accounts (Appendix A).

#### User Location Estimation

Key questions:

1. How are training labels obtained without ground-truth geolocation?
2. How does the hierarchical model assign and fall back across geographic tiers?
3. What validation evidence and access controls accompany location models?

How they answered these:

Without ground-truth geolocation, the authors auto-extracted self-disclosures for training labels. They trained a hierarchical model on full posting history (word usage, subreddit participation, timestamps) that first separates U.S. from non-U.S., then U.S. states (including DC) versus four world regions, retaining coarser or unknown labels when fine-tier confidence is weak. They planned five validation strands (manual audit of auto-labels, held-out users, masked self-disclosure ablation, confidence calibration, marriage-equality vote spikes). They withheld training data for privacy, and they released models under a Model Use Agreement by request (Appendix D).

#### Anonymization

Key questions:

1. How are usernames replaced while preserving longitudinal/spatial user linkage?

How they answered these:

The authors merged comment and submission streams per distinction into a time-ordered set. They replaced usernames with persistent random IDs shared across posts and all six distinctions, so longitudinal and spatial linkage survives without distributing the username-to-ID map.

### Semantic Labels

#### Moralization

Key questions:

1. Why train on MFRC, and why a binary rather than foundation-level label?
2. How will validity of moralization labels be probed in the corpus?

How they answered these:

The authors trained on the Moral Foundations Reddit Corpus because it is the same platform. They collapsed annotations to moralized versus not (majority vote; ties toward moralized), because a binary label yields more even performance and broader theoretical agreement than foundation-level labels. They released the model and held-out MFRC metrics, and they planned distributional contrasts across distinctions and poles (e.g., contested domains more moralized) to probe validity in the corpus.

#### Sentiment

Key questions:

1. Why use multiple sentiment systems instead of one?
2. How is ensemble consistency and directional validity assessed?

How they answered these:

The authors applied three deliberately different tools (VADER, TextBlob, Stanza) as separate columns so users can ensemble, agree-gate, or study disagreement instead of trusting one system. They evaluated internal consistency on a year-by-group stratified subsample (about 60k posts). They planned pole contrasts expecting more negative tone for marginalized poles.

#### Emotion

Key questions:

1. Why ensemble three emotion models, and what scores are released?
2. How are reliability and validity of emotion labels established?

How they answered these:

The authors ran three pretrained emotion classifiers jointly so each of six basic emotions plus neutral has three estimates. They stored model-specific scores from 0 to 1 for ensemble and disagreement analyses. They measured cross-model agreement for reliability, and they planned pole contrasts expecting more negative emotions for marginalized groups to address directional validity.

#### Generalization

Key questions:

1. How is linguistic generalization operationalized at clause level?
2. What outputs ship per post, and where is model documentation?

How they answered these:

The authors modeled genericity, eventivity, and (for eventives) boundedness/habituality with an in-house clause-segmentation and labeling suite. They counted non-statements separately when features are undefined. They released clause lists, per-clause labels, and feature counts/proportions, and they reported held-out metrics with full training docs in a companion paper.

### Corpus Access

Key questions:

1. What five access pathways serve different skill levels and scales?

How they answered these:

The authors provided five pathways for different skill levels and scales: (1) coding-free website downloads/stratified samples (CSV), (2) SQL playground for limited queries, (3) `isaac-data` PyPI package with resumable selective loads, (4) HuggingFace Datasets/Models, (5) scripted direct-download instructions (Appendix F).

### Data Use Agreement

Key questions:

1. What legal/ethical constraints govern use of data, tools, and scripts?

How they answered these:

The authors governed all pathways with a DUA developed with UIUC Legal Counsel (Appendix A). Use is limited to non-commercial academic research. The agreement bans re-identification, generative AI training, and harmful or surveillant uses. It also limits redistribution and requires users to go through official channels.

### Adapting and Extending ISAAC

Key questions:

1. How can others reuse in-house models without coding, and at what scale?
2. Which pipeline components can be swapped for new groups, languages, platforms, or labels?

How they answered these:

The authors released modular public scripts and hosted HuggingFace Spaces for relevance, moralization, and generalization labeling so others can reuse in-house models without coding. Spaces are quota-limited, so they recommend local acceleration for large jobs. Documented swap points include keyword lists, language target, custom relevance/location training, stratified sampling/IRR tools, and non-Reddit readers. Because broad Pushshift access has been discontinued, the released corpus is also a durable historical archive of that period (Appendix E).

### Analytic Strategy

Key questions:

1. How are model performance, census descriptives, and subsample analyses reported?
2. Which metrics and corpus-level validation checks structure the Results?

How they answered these:

The authors used held-out and audit point estimates for models, and census descriptives without CIs for full-corpus counts. For independent or stratified units they used exact tests, native metrics (κ, F1, ρ, r), and bootstrapped 95% CIs, preferring macro-averaged F1 for multi-class balance. They skipped power analysis because the focus is estimation and validation. They predefined three macro checks: volume versus Google Trends; event-locked monthly volumes (plus a state marriage-equality location check); and a semantic cross-label plus Gallup-aligned sexuality sentiment composite.

---

## Results

### Filtering Pipeline Performance

Key questions:

1. Was the <10% residual-irrelevance target met, and did quality transfer to submissions?
2. How did required pipeline depth and interrater agreement vary by distinction?

How they answered these:

The authors documented per-distinction step counts with uneven depth (some one-pass; ability/race/skin tone needed reinforced classification and secondary pattern passes). They reported final double-rated comment audits under lenient versus stringent relevance rules and single-rater submission transfer audits in Table 3. They pointed to Appendix C for classifier metrics and step-by-step error reduction.

### Key Descriptive Statistics

Key questions:

1. What is the composition of the released corpus by post type, group, and year?

How they answered these:

The authors reported submission versus comment shares, relative volumes across the six distinctions (Figure 3), and growth of entries over collection years (Figure 4). These are census-style descriptives rather than inferential tests.

### Location Model Evaluation

Key questions:

1. How accurate are auto-extracted training disclosures and held-out hierarchical predictions?
2. How much does performance depend on overt place names (masking ablation)?
3. How are confidence thresholds and calibration used in the released labels?

How they answered these:

The authors summarized Appendix D on accuracy of auto-extracted disclosures and held-out hierarchical predictions: manual audit of disclosure labels; held-out macro F1/accuracy at U.S./non-U.S., region, and state tiers; and top-k and centroid-distance error sweeps (Table 4). They re-evaluated after stripping place names in a masking ablation. Released labels use conservative tiered confidence assignment across authors, and calibration/recalibration mappings ship with the corpus.

### Semantic Label Validation and Performance

Key questions:

1. How are off-the-shelf vs. in-house labelers evaluated differently?

How they answered these:

The authors split Table 5 into published creator benchmarks (sentiment/emotion) versus new held-out evaluations (moralization, generalization), and they added ensemble agreement on the stratified subsample in Figure 5.

#### Moralization

Key questions:

1. How does the custom moralization classifier perform on held-out MFRC?

How they answered these:

The authors report precision/recall/F1 and macro metrics on a 10% MFRC holdout.

#### Sentiment

Key questions:

1. How consistent are the three sentiment tools, and is the ensemble usable?

How they answered these:

The authors compared pairwise agreement and baseline skew across VADER/TextBlob/Stanza. After testing baseline-adjusted agreement, they reported three-model ICC on the stratified subsample relative to known human-agreement ceilings for social-media sentiment.

#### Emotion

Key questions:

1. How much do models agree on categorical vs. continuous emotion scores, and how is consensus formed at corpus scale?

How they answered these:

The authors reported pairwise κ on top labels (before/after rate equalization) and ICCs on continuous intensities. Majority-vote and unanimous consensus rates show how consensus forms when the models are applied corpus-wide.

#### Generalization

Key questions:

1. How well do segmentation and feature classifiers perform on held-out gold clauses?

How they answered these:

The authors cited companion-paper metrics for clause-span coverage, 18-way situation-entity classification, and collapsed F1/accuracy for genericity, eventivity, and boundedness/habituality.

### Corpus-Level Validation

#### Volume-Based Validation

Key questions:

1. Does monthly discourse volume track independent search interest?
2. Do national group-linked events produce detectable volume spikes after growth adjustment?
3. Do location labels capture localized spikes around state marriage-equality votes?

How they answered these:

**Search Interest.** The authors correlated monthly ISAAC volumes with Google Trends (level and first-difference). For sexuality, they also compared platform-share-normalized series to separate platform-growth artifacts (Figure 6).  
**National Event Spikes.** They compared event-month volumes to trailing baselines with post-2013 percentiles and share-adjusted volumes for group-specific anchors (Figure 7), treating age as an informative null.  
**Localized Event Spikes.** They indexed sexuality volume for voting-state users against non-voting-state medians around nine ballot measures, and they tested consistent outperformance (sign test / bootstrap; Figure 8; Appendix C.4).

#### Semantic Validation

Key questions:

1. Do moralization, sentiment, and emotion profiles differentiate groups and poles in theoretically expected ways?
2. Does sexuality discourse tone align with national public opinion over time?

How they answered these:

**Inter-Variable Alignment.** The authors used volume-weighted samples and the stratified subsample to profile moralization and affect by distinction, moralized versus non-moralized emotion coupling, and marginalized versus dominant pole sentiment (Table 6).  
**Validation Against National Public Opinion.** They built an annual three-tool sexuality sentiment composite and correlated it with Gallup marriage-equality support, also checking first-difference co-movement (Figure 9; Appendix C.4).

---

## Discussion

Key questions:

1. How do the major design choices (filtering, location, multi-model semantics) follow from the goal of scalable yet high-quality discourse study?
2. What multi-level validity argument ties component audits to corpus-level external convergence?

How they answered these:

The authors restated one goal: study discourse at scale without sacrificing measurement quality or flexibility. Aggressive multi-stage filtering, conservative tiered location, and multi-model semantics follow from that goal. They argued validity through convergence across component human agreement, residual-irrelevance, and model metrics, plus corpus-level search, event, and survey alignments, rather than through any single comparison.

### ISAAC's Scope of Intended Use

Key questions:

1. Where does ISAAC sit relative to surveys and implicit-measure repositories?
2. How does a fixed public pipeline enable cumulative, cross-category, temporal, spatial, and theory-testing work?

How they answered these:

The authors positioned ISAAC as unobtrusive naturalistic text complementary to ANES/GSS and large implicit repositories for triangulation. Because the pipeline is fixed and public, shared infrastructure can end study-specific silos, and identical multi-group processing supports artifact-free comparisons. The 17-year window supports interrupted time-series / DiD and lead-lag designs. State-year spatial linkage connects regional attitudes and outcomes. Semantic labels support tests of moral outrage, generic/essentialist language, and ML training/evaluation without oversimplified composites.

### Limitations and Possibilities for Expansion

Key questions:

1. What structural limits bind all downstream use (platform, language, text≠attitude)?
2. Which design compromises are mitigated by releasing uncertainty and multi-model outputs?
3. Along what four axes can independent labs extend the open pipeline?

How they answered these:

The authors acknowledged Reddit demographics, English-only content, platform norms, and the gap from manifest discourse markers to latent attitudes (plus platform-dynamics confounders). They treated sparse high-precision state labels and cross-model disagreement as deliberate compromises, mitigated by confidence/recalibration artifacts and side-by-side model outputs. They listed modular expansions such as new keyword dictionaries, alternate platform loaders, multilingual filters, and additional semantic labels, operationalized in the open repo (Appendix E).

---

## Conclusion

Key questions:

1. What integrated infrastructure claim does the paper close on?

How they answered these:

The authors summarized ISAAC as cumulative quantitative infrastructure: multi-decade multi-group text with temporal, geographic, and semantic indicators from a standardized pipeline; multi-pathway distribution; and a modular open architecture for expansion beyond current limits.

---

## Acknowledgments

Key questions:

1. Who contributed human validation and website development support?

How they answered these:

The authors credit named assistants for human validation and website development (with the full list continuing on the following page beyond the 1 to 53 scope).
