# Confabulation Boundary

This page analyses the fundamental limit of geometric grounding checks: the boundary at which the distributional hypothesis stops distinguishing grounded text from a confabulation that stays in register.

**Paper**: Marin (2026). *Rotational Dynamics of Factual Constraint Processing in LLMs*. [arXiv:2603.13259](https://arxiv.org/abs/2603.13259).

## The Core Problem

DGI measures whether the question-to-response displacement aligns with the direction characteristic of answers written from a source. It separates a confabulation **that leaves the register** of a correct answer, because such a response lands elsewhere in the space. It does not separate one that stays in register, and most production errors do.

However, this detection mechanism has a fundamental boundary: it relies on the **distributional hypothesis** (Harris, 1954), which states that meaning is encoded by distributional context. Any text that matches the distributional properties of grounded text will receive a high DGI score, **regardless of whether it is factually true**.

!!! danger "The confabulation boundary in one sentence"
    If a false statement is phrased in a way that is distributionally indistinguishable from a true statement, no embedding-based method can detect it as false.

## Types of Hallucinations

The geometric taxonomy (arXiv:2602.13224v3) classifies hallucinations by their geometric signature:

### Type 1: Divergent Hallucinations

These are responses where the LLM's output moves in a direction that is clearly different from grounded responses. They are characterized by:

- Large angular deviation from $\hat{\boldsymbol{\mu}}$ (low DGI)
- Often involves topic drift, irrelevant elaboration, or incoherent generation
- **Detectable** by DGI with high confidence

$$
\hat{\boldsymbol{\delta}}_{\text{divergent}} \cdot \hat{\boldsymbol{\mu}} \ll 0.30
$$

### Type 2: Tangential Hallucinations

Responses that partially follow the grounded direction but with significant lateral deviation. They contain some relevant content mixed with fabricated details.

- Moderate DGI scores (around the threshold)
- Often semantically plausible but factually mixed
- **Partially detectable** by DGI

$$
0 < \hat{\boldsymbol{\delta}}_{\text{tangential}} \cdot \hat{\boldsymbol{\mu}} < 0.30
$$

### Type 3: Distributional Confabulations

Responses that perfectly mimic the distributional properties of grounded text while being factually wrong. These are the **undetectable** cases:

- High DGI scores (above threshold)
- Distributionally identical to grounded responses
- **Not detectable** by any embedding-based method

$$
\hat{\boldsymbol{\delta}}_{\text{confab}} \cdot \hat{\boldsymbol{\mu}} \geq 0.30
$$

## Why LLM-Generated Hallucinations Are Detectable

When an LLM generates a hallucinated response, the generation process itself introduces a geometric signature. The transformer's internal representations undergo different computational paths for grounded versus hallucinated outputs:

1. **Grounded generation**: The model retrieves and composes information from its parametric memory in a way that produces embeddings consistent with the training distribution of correct answers.

2. **Hallucinated generation**: The model fills gaps with plausible-sounding but incorrect completions. This process produces embeddings that deviate systematically from the grounded distribution --- the "fabrication direction" is geometrically distinct from the "retrieval direction."

An earlier version of this page explained a reported AUROC of 0.958 on the confabulation benchmark by a "detectable geometric trace" left by the LLM's generative process. **That number is withdrawn and the explanation was the artifact itself.** The trace being detected was *authorship*: in that benchmark the grounded answers were machine-written and the confabulations human-written. Hold authorship constant and the directional score falls to 0.606. See [Results](../benchmarks/results.md).

### Mechanistic evidence: active suppression

The arXiv preprint paper (Marin, 2026b) provides direct evidence for *why* this geometric trace exists by probing what happens inside the transformer during hallucination.

Using forced-completion probing across seven decoder-only models (Llama-2 7B through Llama-3.1 70B, Mistral 7B, Gemma-2 9B, Phi-3 3.8B, Qwen-2.5 7B), the study measures how residual-stream representations evolve layer by layer when a model produces a grounded versus a hallucinated completion. The key findings:

**Models retrieve correct answers, then override them.** In the middle layers, the correct factual answer is recoverable from the residual stream even when the model ultimately hallucinates. At late layers ($\ell > 0.7L$), the representation undergoes an **isometric rotational divergence**: the residual-stream vector rotates away from the correct-answer subspace while preserving its norm. This is not a decay of signal --- it is an active redirection.

**Factual selection is geometry-in-direction, not magnitude.** The divergence between grounded and hallucinated trajectories manifests as angular deviation (measured by cosine similarity $\kappa$ between the two trajectories), not as a change in vector norm. When $\kappa$ drops below 0.5 at late layers, the model is actively suppressing the correct answer. This rotational signature is exactly what DGI detects in the output embedding: the displacement direction from question to response carries a trace of whether the generation process stayed on the grounded trajectory or rotated away from it.

**The suppression pattern is consistent across model families.** All seven architectures tested show the same qualitative pattern --- mid-layer factual retrieval followed by late-layer rotational suppression --- despite different training data, tokenizers, and parameter counts. This universality explains why DGI generalizes across models: it measures a downstream consequence of a mechanism that is shared across transformer architectures.

**Domain-local transfer.** Calibrating DGI's reference direction $\hat{\mu}$ on one declarative-knowledge domain (e.g., biology) transfers to other declarative domains (e.g., history) with minimal AUROC loss ($\Delta < 0.05$), consistent with the finding that the suppression rotation is domain-general rather than topic-specific.

!!! info "Connecting mechanistic and geometric levels"
    groundlens operates at the sentence-embedding level (black-box, single-pass). The COLM findings explain *why* this works: the rotational divergence at late transformer layers propagates through the embedding model's own encoder, producing the directional deviation that DGI measures. The mechanistic and geometric accounts are complementary --- the rotational dynamics paper explains the cause; groundlens measures the consequence.

## Why Human-Crafted Confabulations Are Undetectable

A human expert can craft a false statement that is distributionally indistinguishable from a true statement. Consider:

- **True**: "The boiling point of water at sea level is 100 degrees Celsius."
- **False**: "The boiling point of water at sea level is 95 degrees Celsius."

Both sentences have:

- Identical syntactic structure
- Identical vocabulary (except for one numeral)
- Identical distributional context (science, boiling point, water, temperature)
- Nearly identical embedding vectors

The displacement vectors from a question like "What is the boiling point of water?" to each of these responses will be virtually identical in direction. DGI cannot distinguish them.

### Formal Analysis

Let $r_{\text{true}}$ and $r_{\text{false}}$ be two responses that differ only in a factual detail while maintaining identical distributional properties. Then:

$$
\phi(r_{\text{true}}) \approx \phi(r_{\text{false}}) + \boldsymbol{\epsilon}
$$

where $\|\boldsymbol{\epsilon}\|$ is small relative to the displacement magnitude. The DGI scores will be:

$$
\text{DGI}_{\text{true}} = \frac{(\phi(r_{\text{true}}) - \phi(q))}{\|\phi(r_{\text{true}}) - \phi(q)\|} \cdot \hat{\boldsymbol{\mu}}
$$

$$
\text{DGI}_{\text{false}} \approx \text{DGI}_{\text{true}} + O\left(\frac{\|\boldsymbol{\epsilon}\|}{\|\boldsymbol{\delta}\|}\right)
$$

For typical embedding models, a single-fact substitution produces $\|\boldsymbol{\epsilon}\| / \|\boldsymbol{\delta}\| \approx 0.01$--$0.05$, well within the noise floor. The two DGI scores are indistinguishable.

## The Confabulation Benchmark

The confabulation benchmark (arXiv:2603.13259) systematically tests this boundary using three categories:

### Category 1: LLM-Generated Hallucinations

Responses generated by LLMs that were instructed to answer questions without access to correct information. These hallucinations carry the geometric signature of the fabrication process.

**Result, corrected**: under an authorship-matched control the directional score reaches AUROC **0.606**, and the ceiling of the whole embedding-similarity class is about 0.68. The uncontrolled 0.958 measured who wrote the text.

### Category 2: Template-Based Confabulations

Factually incorrect responses constructed by substituting incorrect values into templates derived from correct answers. These maintain distributional properties while changing factual content.

**Result**: DGI AUROC drops significantly. The geometric signal is weak because the distributional properties are preserved.

### Category 3: Expert-Crafted Confabulations

Factually incorrect responses written by domain experts specifically to be distributionally indistinguishable from correct responses.

**Result**: DGI AUROC approaches **0.50** (random chance). No geometric discrimination is possible.

## The Boundary as a Theorem

The confabulation boundary can be stated formally:

!!! abstract "Confabulation Boundary Theorem (Informal)"
    Let $\phi$ be any embedding function derived from the distributional hypothesis (including all sentence transformers, word2vec, GloVe, etc.). Let $r_{\text{true}}$ and $r_{\text{false}}$ be texts with identical distributional properties but different truth values. Then:

    $$
    \|\phi(r_{\text{true}}) - \phi(r_{\text{false}})\| \to 0
    $$

    as the distributional similarity increases, regardless of the factual difference.

    Consequently, any method that scores a response solely by its position under $\phi$ cannot distinguish $r_{\text{true}}$ from $r_{\text{false}}$.

This is not a limitation of groundlens specifically. It is a constraint on **any method that scores a response by its position in a distributional embedding space**:

- Cosine similarity and every ratio or projection built on it
- SGI, DGI, and supervised probes over the same embeddings
- Semantic similarity methods generally

!!! success "What it is NOT a constraint on"
    Methods that **read the response against a source**, rather than measuring where it sits, are outside this bound and do not decline in register:

    - **Entailment (NLI).** Binned from out-of-register to in-register it holds AUROC 0.836, 0.786, 0.837, 0.719, **0.887**. It is strongest exactly where geometry is weakest.
    - **Reference-based verification** (lookup against the source, knowledge graphs).
    - **Model-graded judging** on a supplied source.

    These are the way past the wall, and they are the second stage. Groundlens escalates to them; it does not compete with them.

## Implications for Practice

### What groundlens Can Detect

| Hallucination type | Detection ability | AUROC |
|---|---|---|
| LLM-generated fabrications | Strong | 0.90--0.96 |
| Topic drift / irrelevant responses | Strong | 0.85--0.95 |
| Context-ignoring responses (SGI) | Strong | 0.88--0.95 |
| Partially grounded, partially fabricated | Moderate | 0.70--0.85 |
| Single-fact substitution confabulations | Weak | 0.50--0.60 |
| Expert-crafted confabulations | None | ~0.50 |

### What This Means for Deployment

1. **groundlens is a triage tool, not a truth oracle.** It efficiently identifies outputs that are geometrically anomalous --- the most common and most damaging hallucination types. It cannot verify factual correctness at the individual claim level.

2. **The value is in the 80% you do not need to review.** If groundlens passes 80% of outputs and flags 20%, and the flagged set contains 95% of the actual hallucinations, you have reduced your human review workload by 4x while catching nearly all problems.

3. **Complement with domain knowledge.** For high-stakes applications where single-fact confabulations matter (medical, legal, financial), combine groundlens triage with domain-specific fact-checking on the outputs that pass geometric verification.

## Why This Is Honest

Many products in this space claim to "detect all hallucinations" or to provide a "factual accuracy score". Under the distributional hypothesis those claims are not possible, and a high reported AUROC in this family is usually a shortcut: authorship, length, or generation condition. We published such a number ourselves and withdrew it.

So the boundary is documented as a number, not as a footnote, and the controls that expose it are published as a protocol. That is the point of this page.

groundlens is positioned as **verification triage**: prioritize what to review, not "detect so you don't need to review." If a tool cannot explain what it misses and why, it is selling confidence it has not earned.

## Complementary Tools for Type III Detection

The confabulation boundary is a limitation of distributional embeddings, not of verification in general. For high-stakes applications where within-frame factual errors matter, the recommended architecture is **groundlens for triage + a complementary method for the outputs that pass geometric verification**. This section describes concrete tools and techniques for the Type III cases that groundlens cannot catch.

### Claim decomposition + source retrieval

Break each LLM output into atomic claims, then verify each claim against an authoritative source. This is the most mature approach and the one with broadest applicability.

**Tools:**

- **[Vectara HHEM](https://huggingface.co/vectara/hallucination_evaluation_model)** --- A cross-encoder fine-tuned specifically for factual consistency checking. Operates on (source, claim) pairs and returns a consistency probability. Effective when the source document is available (RAG settings). Complementary to groundlens because it performs token-level entailment rather than sentence-level geometry.
- **[AlignScore](https://github.com/yuh-zha/AlignScore)** --- A unified alignment function trained on 4.7M examples across NLI, QA, and paraphrase tasks. Particularly strong on factual consistency in summarization. Handles the source-grounded verification that groundlens deliberately excludes from its scope.
- **[MiniCheck](https://github.com/Liyan06/MiniCheck)** --- Fact-checking grounded in document retrieval, designed for claim-level verification. Lightweight and suitable for pipeline integration.
- **[FActScore](https://github.com/shmsw25/FActScore)** --- Decomposes long-form generation into atomic facts and verifies each against Wikipedia. Originally designed for biography generation but the decompose-then-verify pattern applies broadly.

### LLM-as-judge (with caveats)

Using a second LLM to evaluate the first is conceptually simple but carries the risk that the judge hallucinates in the same way as the generator. The approach works best when:

1. The judge model is different from the generator (different architecture or training data)
2. The judge is given access to source documents for grounded evaluation
3. Multiple judges are used and their assessments are aggregated

**Tools:**

- **[RAGAS](https://github.com/explodinggradients/ragas)** --- Framework for RAG pipeline evaluation. Includes faithfulness, answer relevance, and context precision metrics. Uses LLM-as-judge internally but structures the evaluation to reduce judge hallucination.
- **[DeepEval](https://github.com/confident-ai/deepeval)** --- LLM evaluation framework with hallucination-specific metrics. Includes G-Eval implementation and faithfulness scoring.

!!! tip "Entailment is the recommended second stage"
    Across register bins an NLI cross-encoder holds AUROC 0.72 to 0.89 and does not decline as a confabulation stays in register. Route what groundlens escalates to entailment, a lookup against the source, or a model judge.

    One real caveat, and it is about the **task**, not the method: on open-domain misconception benchmarks such as TruthfulQA, where there is no source to check against, every method here is at or below chance. That is a property of asking "is this true in the world?" with no reference. Give the verifier a source and it works. Do not ask any of these methods to adjudicate open-domain truth from nothing.

### Knowledge graph verification

For domains with structured knowledge (medicine, law, finance), verify extracted entities and relationships against a knowledge graph.

**Tools:**

- **[Wikidata / SPARQL](https://www.wikidata.org/)** --- Free, broad-coverage knowledge graph. Suitable for verifying named entities, dates, relationships, and numerical facts.
- **Domain-specific ontologies** --- SNOMED CT (medical), FIBO (financial), or your organization's internal knowledge graph. These provide authoritative facts that no distributional method can access.
- **[LangChain fact-checking chains](https://python.langchain.com/)** --- Can be configured to decompose claims and verify against a retrieval backend (vector store, knowledge graph, or API).

### Consistency-based methods

Rather than verifying against an external source, these methods detect hallucinations by checking whether the LLM is self-consistent.

**Tools:**

- **[SelfCheckGPT](https://github.com/potsawee/selfcheckgpt)** --- Samples multiple responses to the same question and measures consistency. If the model says different things each time, at least some of the responses are hallucinated. Effective for Type III detection because within-frame factual errors tend to be inconsistent across samples while correct facts are stable.
- **Semantic entropy** (Kuhn et al., 2023) --- Clusters sampled responses by semantic equivalence and measures the entropy of the cluster distribution. High entropy indicates uncertainty, which correlates with hallucination.

!!! note "Cost tradeoff"
    Consistency-based methods require multiple LLM calls per output (typically 5-20 samples). They are best reserved for the subset of outputs that pass groundlens triage, reducing the total cost by 4-5x compared to applying them to all outputs.

### Recommended architecture

For production systems, the practical architecture is a two-stage pipeline:

1. **Stage 1 — groundlens triage** (fast, deterministic, single-pass): Score all outputs with SGI/DGI. Flag outputs below threshold for human review. Pass outputs above threshold to Stage 2.
2. **Stage 2 — claim-level verification** (slower, more expensive): Apply one or more of the tools above to the outputs that passed geometric triage. This catches the Type III errors that groundlens cannot detect.

The value of this architecture is cost efficiency: if groundlens passes 80% of outputs and the flagged 20% contains 95% of Type I and Type II hallucinations, you only need to run the expensive claim-level tools on the remaining 80% — and only on the high-stakes subset of those. In practice, this reduces claim-verification costs by an order of magnitude while maintaining high recall across all three hallucination types.

## References

- Marin, J. (2026a). *Rotational Dynamics of Factual Constraint Processing in LLMs*. arXiv:2603.13259.
- Marin, J. (2026b). *Hallucination Is Active Suppression*. arXiv preprint. [arXiv:2604.xxxxx](https://arxiv.org/abs/2604.xxxxx).
- Marin, J. (2026c). *A Geometric Taxonomy of Hallucinations in LLMs*. arXiv:2602.13224v3.
- Marin, J. (2025). *Semantic Grounding Index for LLM Hallucination Detection*. arXiv:2512.13771.
- Harris, Z. S. (1954). Distributional structure. *Word*, 10(2-3), 146--162.
- Ji, Z. et al. (2023). Survey of hallucination in natural language generation. *ACM Computing Surveys*.
- Kalai, A. T. & Vempala, S. S. (2025). *Why Language Models Hallucinate*. arXiv preprint.
