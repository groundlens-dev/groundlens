# Confabulation Boundary

This page analyzes the fundamental limitation of geometric hallucination detection: the boundary at which the distributional hypothesis fails to distinguish between grounded text and deliberately constructed confabulations.

**Paper**: Marin (2026). *Rotational Dynamics of Factual Constraint Processing in LLMs*. [arXiv:2603.13259](https://arxiv.org/abs/2603.13259).

## The Core Problem

DGI detects hallucinations by measuring whether the question-to-response displacement aligns with the direction characteristic of grounded responses. This works because LLM-generated hallucinations produce displacements that deviate from the grounded direction --- the LLM moves through embedding space differently when fabricating versus when faithfully reporting.

However, this detection mechanism has a fundamental boundary: it relies on the **distributional hypothesis** (Harris, 1954), which states that meaning is encoded by distributional context. Any text that matches the distributional properties of grounded text will receive a high DGI score, **regardless of whether it is factually true**.

!!! danger "The confabulation boundary in one sentence"
    If a false statement is phrased in a way that is distributionally indistinguishable from a true statement, no embedding-based method can detect it as false.

## Types of Hallucinations

The geometric taxonomy (arXiv:2602.13224) classifies hallucinations by their geometric signature:

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

This is why DGI achieves AUROC 0.958 on the confabulation benchmark for **LLM-generated** hallucinations (arXiv:2603.13259). The LLM's generative process leaves a detectable geometric trace.

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

**Result**: DGI AUROC = **0.958** with domain calibration.

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

    Consequently, any hallucination detection method based solely on $\phi$ cannot distinguish $r_{\text{true}}$ from $r_{\text{false}}$.

This is not a limitation of groundlens specifically --- it is a fundamental constraint on **all** embedding-based methods, including:

- LLM-as-judge (when the judge uses embeddings internally)
- Retrieval-based fact checking
- Semantic similarity methods
- Any method operating in distributional embedding space

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

Many hallucination detection products claim to "detect all hallucinations" or provide "factual accuracy scores." These claims are not possible under the distributional hypothesis. By explicitly documenting the confabulation boundary, groundlens gives users an honest understanding of what geometric detection can and cannot do.

groundlens is positioned as **verification triage**: prioritize what to review, not "detect so you don't need to review." If a tool cannot explain what it misses and why, it is selling confidence it has not earned.

## Toward Breaking the Boundary

The confabulation boundary is a limitation of distributional embeddings. Methods that could potentially go beyond it include:

- **Knowledge graph grounding**: Verifying individual claims against structured knowledge bases.
- **Provenance tracking**: Tracing which training data or retrieval sources contributed to each output token.
- **Causal reasoning**: Detecting logical inconsistencies that distributional methods miss.
- **Multi-modal verification**: Cross-referencing text claims against non-text sources.

These approaches complement groundlens rather than replace it --- they address the cases that fall beyond the confabulation boundary while groundlens handles the efficiently-detectable cases.

## References

- Marin, J. (2026). *Rotational Dynamics of Factual Constraint Processing in LLMs*. arXiv:2603.13259.
- Marin, J. (2026). *A Geometric Taxonomy of Hallucinations in LLMs*. arXiv:2602.13224.
- Harris, Z. S. (1954). Distributional structure. *Word*, 10(2-3), 146--162.
- Ji, Z. et al. (2023). Survey of hallucination in natural language generation. *ACM Computing Surveys*.
