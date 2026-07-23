# DGI Mathematics

This page presents the complete mathematical framework for the Directional Grounding Index, including displacement vector analysis, the von Mises-Fisher distribution on the unit hypersphere, mean direction estimation, the concentration parameter $\kappa$, and the linear normalization scheme.

## Displacement Vectors

Given a question $q$ and response $r$, the **displacement vector** is:

$$
\boldsymbol{\delta} = \phi(r) - \phi(q) \in \mathbb{R}^n
$$

This vector encodes the semantic transformation from question to response. Its two components carry distinct information:

- **Direction** $\hat{\boldsymbol{\delta}} = \boldsymbol{\delta} / \|\boldsymbol{\delta}\|$: *How* the semantics changed (toward factual elaboration, toward tangential topics, toward contradictions, etc.)
- **Magnitude** $\|\boldsymbol{\delta}\|$: *How much* the semantics changed (small for paraphrases, large for substantial elaboration)

The DGI **score** uses only the **direction** component. This is a deliberate design choice: the magnitude of semantic displacement varies widely across different question types and response lengths, but the *direction* of grounded displacement is consistent. The magnitude is not discarded — it is returned on `DGIResult.magnitude` as a second, complementary signal (how far the response moved from the question) — it simply does not enter the score.

## The Unit Displacement

The unit-normalized displacement vector is:

$$
\hat{\boldsymbol{\delta}} = \frac{\boldsymbol{\delta}}{\|\boldsymbol{\delta}\|} = \frac{\phi(r) - \phi(q)}{\|\phi(r) - \phi(q)\|}
$$

This maps the displacement to the **unit hypersphere** $S^{n-1} = \{\mathbf{v} \in \mathbb{R}^n : \|\mathbf{v}\| = 1\}$. All directional analysis --- the reference direction, the DGI score, the von Mises-Fisher model --- operates on $S^{n-1}$.

!!! note "Degenerate case"
    When $\phi(r) = \phi(q)$ (the response is identical to the question in embedding space), $\|\boldsymbol{\delta}\| = 0$ and the unit displacement is undefined. The implementation detects this case ($\|\boldsymbol{\delta}\| < 10^{-8}$) and returns DGI = 0, flagged = True.

## The Reference Direction $\hat{\boldsymbol{\mu}}$

The reference direction is the **mean direction** of displacement vectors computed from a set of $N$ verified grounded (question, response) pairs $\{(q_i, r_i)\}_{i=1}^N$.

### Computation

1. Compute each displacement: $\boldsymbol{\delta}_i = \phi(r_i) - \phi(q_i)$
2. Normalize to unit length: $\hat{\boldsymbol{\delta}}_i = \boldsymbol{\delta}_i / \|\boldsymbol{\delta}_i\|$
3. Compute the resultant vector: $\mathbf{R} = \sum_{i=1}^N \hat{\boldsymbol{\delta}}_i$
4. Normalize: $\hat{\boldsymbol{\mu}} = \mathbf{R} / \|\mathbf{R}\|$

This is equivalently expressed as:

$$
\hat{\boldsymbol{\mu}} = \text{normalize}\left(\frac{1}{N}\sum_{i=1}^{N} \hat{\boldsymbol{\delta}}_i\right)
$$

### Statistical Interpretation

The reference direction $\hat{\boldsymbol{\mu}}$ is the **maximum-likelihood estimate (MLE)** of the mean direction parameter $\boldsymbol{\mu}$ of a von Mises-Fisher distribution (see below). This makes it the optimal estimate under the assumption that grounded displacement directions are drawn from a unimodal directional distribution.

## The Von Mises-Fisher Distribution

The von Mises-Fisher (vMF) distribution is the natural probability distribution for directional data on $S^{n-1}$. It is the hyperspherical analog of the Gaussian distribution, and DGI uses it as the probabilistic model for grounded displacement directions.

### Probability Density Function

The vMF distribution on $S^{n-1}$ with mean direction $\boldsymbol{\mu} \in S^{n-1}$ and concentration parameter $\kappa \geq 0$ has density:

$$
f(\mathbf{x}; \boldsymbol{\mu}, \kappa) = C_n(\kappa) \exp\bigl(\kappa \, \boldsymbol{\mu}^\top \mathbf{x}\bigr)
$$

where the normalizing constant is:

$$
C_n(\kappa) = \frac{\kappa^{n/2 - 1}}{(2\pi)^{n/2} I_{n/2 - 1}(\kappa)}
$$

and $I_\nu(\cdot)$ is the modified Bessel function of the first kind of order $\nu$.

### Interpretation of Parameters

**Mean direction $\boldsymbol{\mu}$**: The mode of the distribution. This is the "most likely" direction. For DGI, $\hat{\boldsymbol{\mu}}$ represents the characteristic displacement direction of grounded responses.

**Concentration $\kappa$**: Controls how tightly the distribution is concentrated around $\boldsymbol{\mu}$:

- $\kappa = 0$: Uniform distribution on $S^{n-1}$. No preferred direction.
- $\kappa$ small: Spread out, weak directional preference.
- $\kappa$ large: Tightly concentrated around $\boldsymbol{\mu}$.
- $\kappa \to \infty$: Point mass at $\boldsymbol{\mu}$.

!!! abstract "Why vMF for DGI?"
    The vMF distribution is the maximum-entropy distribution on $S^{n-1}$ given a constraint on the mean direction. This makes it the least-informative assumption consistent with the observation that grounded displacements have a preferred direction. Using any other distributional family would impose additional structural assumptions not supported by the data.

### Relationship to the Gaussian

In low dimensions, the vMF distribution is well-known:

- On $S^1$ (the circle): vMF reduces to the **von Mises distribution**, the circular analog of the Gaussian.
- On $S^2$ (the 2-sphere): vMF is the **Fisher distribution**, used extensively in paleomagnetic studies and geological directional data.

In high dimensions ($n = 384$), the vMF distribution concentrates rapidly for even moderate $\kappa$ values, due to the vast surface area of $S^{n-1}$.

## Mean Direction Estimation (MLE)

Given $N$ independent samples $\hat{\boldsymbol{\delta}}_1, \ldots, \hat{\boldsymbol{\delta}}_N$ from $\text{vMF}(\boldsymbol{\mu}, \kappa)$, the maximum-likelihood estimate of $\boldsymbol{\mu}$ is:

$$
\hat{\boldsymbol{\mu}}_{\text{MLE}} = \frac{\mathbf{R}}{\|\mathbf{R}\|} = \frac{\sum_{i=1}^N \hat{\boldsymbol{\delta}}_i}{\left\|\sum_{i=1}^N \hat{\boldsymbol{\delta}}_i\right\|}
$$

This is exactly what groundlens computes. The MLE for the mean direction does not depend on $\kappa$ --- it is the same regardless of how concentrated the distribution is.

### The Resultant Length $\bar{R}$

The **mean resultant length** is:

$$
\bar{R} = \frac{1}{N}\left\|\sum_{i=1}^N \hat{\boldsymbol{\delta}}_i\right\| = \frac{\|\mathbf{R}\|}{N}
$$

This scalar in $[0, 1]$ measures the consistency of the directional data:

- $\bar{R} \approx 0$: The unit vectors point in many different directions (no consistent pattern). The calibration data is noisy or from mixed domains.
- $\bar{R} \approx 1$: All unit vectors point in nearly the same direction (strong consensus). The domain has a clear grounded displacement direction.

## Concentration Parameter Estimation

The MLE for $\kappa$ involves solving the equation:

$$
A_n(\kappa) = \bar{R}
$$

where $A_n(\kappa) = I_{n/2}(\kappa) / I_{n/2-1}(\kappa)$ is the ratio of Bessel functions. This equation has no closed-form solution.

### Sra (2012) Approximation

groundlens uses the approximation from Sra (2012)[^1] for the MLE of $\kappa$:

$$
\hat{\kappa} \approx \frac{\bar{R}(n - \bar{R}^2)}{1 - \bar{R}^2}
$$

[^1]: Sra, S. (2012). A short note on parameter approximation for von Mises-Fisher distributions: and a fast implementation of $I_s(x)$. *Computational Statistics*, 27(1), 177--190.

This approximation is accurate for moderate to large $n$ and avoids the computational cost of evaluating Bessel functions. For $n = 384$ (our default embedding dimension), the approximation error is negligible.

### Interpretation of $\hat{\kappa}$

| $\hat{\kappa}$ | Interpretation | DGI quality |
|---|---|---|
| > 10 | High concentration --- strong directional consensus | Excellent discrimination |
| 5--10 | Moderate concentration | Good discrimination |
| 1--5 | Low concentration --- weak consensus | Poor discrimination |
| < 1 | Near-uniform --- no meaningful direction | Calibration failure |

!!! tip "Practical guidance"
    If $\hat{\kappa} < 5$ after calibration, the reference direction is unreliable. Consider: (1) adding more calibration pairs, (2) filtering noisy pairs, (3) splitting into sub-domains if the data spans multiple topics.

## The DGI Score

Given the reference direction $\hat{\boldsymbol{\mu}}$ and a new (question, response) pair, the DGI score is:

$$
\text{DGI} = \hat{\boldsymbol{\delta}}^\top \hat{\boldsymbol{\mu}} = \cos\theta
$$

where $\theta$ is the angle between the displacement direction and the reference direction. This is the cosine similarity between the unit displacement and the unit reference direction.

### Statistical Interpretation Under vMF

Under the null hypothesis that the displacement direction is drawn uniformly from $S^{n-1}$ (i.e., the response is unrelated to the grounded pattern), the expected DGI score is:

$$
\mathbb{E}_{\text{uniform}}[\text{DGI}] = \mathbb{E}[\hat{\boldsymbol{\delta}}^\top \hat{\boldsymbol{\mu}}] = 0
$$

with variance $\approx 1/n$. For $n = 384$, the standard deviation is $\approx 0.051$.

Under the alternative hypothesis that the displacement is drawn from $\text{vMF}(\hat{\boldsymbol{\mu}}, \kappa)$:

$$
\mathbb{E}_{\text{grounded}}[\text{DGI}] = A_n(\kappa) = \frac{I_{n/2}(\kappa)}{I_{n/2-1}(\kappa)}
$$

For well-calibrated domains ($\kappa \geq 10$, $n = 384$), $A_n(\kappa) \approx 1 - (n-1)/(2\kappa)$, which is close to 1.

The DGI threshold of 0.30 is approximately $6\sigma$ above the null hypothesis mean, providing strong statistical confidence.

## Linear Normalization

The DGI score lies in $[-1, 1]$ (the range of cosine similarity). The linear normalization maps this to $[0, 1]$:

$$
\text{DGI}_{\text{norm}} = \frac{\text{DGI} + 1}{2}
$$

### Why Linear (Not Tanh)?

Unlike SGI (which has a semi-infinite range requiring compression), DGI already lies in a bounded interval. A linear map preserves the metric structure:

- Equal differences in raw DGI correspond to equal differences in normalized DGI.
- The midpoint (DGI = 0, orthogonal to reference direction) maps to 0.5.
- The extremes (DGI = -1 and DGI = +1) map to 0 and 1 respectively.

A non-linear normalization (such as tanh) would distort the well-calibrated cosine similarity values and reduce the interpretability of the vMF concentration parameter.

## DGI as a Sufficient Statistic

Under the vMF model, the DGI score $\gamma = \hat{\boldsymbol{\delta}}^\top \hat{\boldsymbol{\mu}}$ is a **sufficient statistic** for the concentration parameter $\kappa$. This means that the DGI score contains all the information that the full displacement direction $\hat{\boldsymbol{\delta}}$ has about whether the response follows the grounded pattern. No additional information about grounding can be extracted from $\hat{\boldsymbol{\delta}}$ beyond what is captured by DGI.

This is a consequence of the exponential family structure of the vMF distribution. The density can be written as:

$$
f(\mathbf{x}; \boldsymbol{\mu}, \kappa) = C_n(\kappa) \exp(\kappa \, \boldsymbol{\mu}^\top \mathbf{x})
$$

The sufficient statistic for $\kappa$ is $\boldsymbol{\mu}^\top \mathbf{x}$, which is exactly the DGI score (when $\boldsymbol{\mu}$ is known or estimated).

## Connection to Hypothesis Testing

DGI can be framed as a one-sided hypothesis test:

- $H_0$: The displacement direction is uniform on $S^{n-1}$ (no grounding signal).
- $H_1$: The displacement direction follows $\text{vMF}(\hat{\boldsymbol{\mu}}, \kappa)$ with $\kappa > 0$ (grounded).

The DGI score is the test statistic. The threshold DGI = 0.30 defines the rejection region. Under $H_0$, the probability of DGI > 0.30 is vanishingly small (since $0.30 / 0.051 \approx 5.9\sigma$), giving the test high specificity.

Under $H_1$ with domain-specific calibration ($\kappa \geq 10$), the expected DGI for grounded responses is well above 0.30. Note what the null is here: a **uniformly random direction**, not a competent confabulation. Against an in-register confabulation the separation is far smaller, and no threshold choice recovers it: with authorship held constant the empirical AUROC is ≈ 0.68. The vMF argument gives the *form* of the statistic. It does not license the uncontrolled numbers this section used to quote.

## Geometric Visualization

Consider the unit hypersphere $S^{n-1}$ with the reference direction $\hat{\boldsymbol{\mu}}$ at the "north pole." The DGI score is the cosine of the polar angle $\theta$ from the north pole:

$$
\text{DGI} = \cos\theta
$$

- Grounded responses cluster near the north pole (small $\theta$, high DGI).
- Hallucinated responses are scattered away from the north pole (large $\theta$, low DGI).
- The DGI = 0.30 threshold corresponds to $\theta \approx 72.5°$.
- The DGI = 0.00 threshold corresponds to $\theta = 90°$ (equator).

The vMF distribution gives the "density of grounded responses" as a function of polar angle: highest at the pole, decaying exponentially as $\theta$ increases, with the rate of decay controlled by $\kappa$.

## Caching Strategy

Computing the reference direction requires embedding all calibration pairs, which involves $2N$ forward passes through the sentence transformer. groundlens caches $\hat{\boldsymbol{\mu}}$ by `(model_name, reference_csv)` key to avoid recomputation:

- First call with a given key: compute and cache.
- Subsequent calls with the same key: return cached result.
- Different CSV paths produce independent cache entries, allowing multiple domain calibrations to coexist.

## References

- Marin, J. (2026). *A Geometric Taxonomy of Hallucinations in LLMs*. arXiv:2602.13224v3.
- Fisher, R. A. (1953). Dispersion on a sphere. *Proceedings of the Royal Society A*, 217, 295--305.
- Mardia, K. V., & Jupp, P. E. (2000). *Directional Statistics*. John Wiley & Sons.
- Sra, S. (2012). A short note on parameter approximation for von Mises-Fisher distributions. *Computational Statistics*, 27(1), 177--190.
- Banerjee, A. et al. (2005). Clustering on the unit hypersphere using von Mises-Fisher distributions. *JMLR*, 6, 1345--1382.
