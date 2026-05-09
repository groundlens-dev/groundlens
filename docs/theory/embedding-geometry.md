# Embedding Geometry

This page provides the mathematical foundations underlying groundlens. We cover the geometry of embedding spaces, the distributional hypothesis that makes them work, and the hyperspherical structure that DGI exploits for directional statistics.

## Embedding Spaces and $\mathbb{R}^n$

A sentence-transformer model $\phi$ maps variable-length text strings to fixed-dimensional vectors in $\mathbb{R}^n$. For the default model `all-MiniLM-L6-v2`, $n = 384$. For `all-mpnet-base-v2`, $n = 768$.

$$
\phi: \mathcal{T} \to \mathbb{R}^n
$$

where $\mathcal{T}$ is the space of all possible text strings. The resulting $n$-dimensional real vector space has the standard Euclidean inner product:

$$
\langle \mathbf{u}, \mathbf{v} \rangle = \sum_{i=1}^{n} u_i v_i
$$

and the induced Euclidean norm:

$$
\|\mathbf{v}\| = \sqrt{\langle \mathbf{v}, \mathbf{v} \rangle} = \sqrt{\sum_{i=1}^{n} v_i^2}
$$

## Distance Metrics

groundlens uses **Euclidean distance** for SGI and **cosine similarity** (via dot product on unit vectors) for DGI.

### Euclidean Distance

The Euclidean distance between two embeddings is:

$$
d(\mathbf{u}, \mathbf{v}) = \|\mathbf{u} - \mathbf{v}\| = \sqrt{\sum_{i=1}^{n} (u_i - v_i)^2}
$$

This metric captures the overall magnitude of difference between two embedding vectors. It is sensitive to both the direction and the magnitude of the vectors.

### Cosine Similarity

Cosine similarity measures the angle between two vectors, ignoring magnitude:

$$
\cos\theta = \frac{\langle \mathbf{u}, \mathbf{v} \rangle}{\|\mathbf{u}\| \cdot \|\mathbf{v}\|}
$$

For unit-normalized vectors ($\|\mathbf{u}\| = \|\mathbf{v}\| = 1$), cosine similarity reduces to the dot product:

$$
\cos\theta = \langle \mathbf{u}, \mathbf{v} \rangle = \mathbf{u} \cdot \mathbf{v}
$$

### Relationship Between the Two

For unit vectors on the hypersphere, Euclidean distance and cosine similarity are monotonically related:

$$
d(\mathbf{u}, \mathbf{v})^2 = \|\mathbf{u}\|^2 + \|\mathbf{v}\|^2 - 2\langle \mathbf{u}, \mathbf{v}\rangle = 2 - 2\cos\theta = 2(1 - \cos\theta)
$$

Therefore:

$$
d(\mathbf{u}, \mathbf{v}) = \sqrt{2(1 - \cos\theta)}
$$

This means on the unit hypersphere, maximizing cosine similarity is equivalent to minimizing Euclidean distance. groundlens uses Euclidean distance for SGI (where magnitude matters) and cosine similarity for DGI (where only direction matters).

## The Distributional Hypothesis

The theoretical foundation for why embedding geometry encodes semantic meaning is the **distributional hypothesis**, articulated by Harris (1954)[^1] and formalized by Firth (1957)[^2]:

> *"You shall know a word by the company it keeps."*

[^1]: Harris, Z. S. (1954). Distributional structure. *Word*, 10(2-3), 146--162.
[^2]: Firth, J. R. (1957). A synopsis of linguistic theory, 1930--1955. *Studies in Linguistic Analysis*, 1--32.

Modern sentence transformers extend this principle from words to sentences. Texts that appear in similar contexts --- that are used in similar ways, answer similar questions, or describe similar concepts --- receive similar embedding vectors. This is not a coincidence but a direct consequence of the contrastive training objective: the model is trained to minimize the distance between semantically similar text pairs and maximize the distance between dissimilar pairs.

!!! abstract "Why this matters for groundlens"
    The distributional hypothesis is both the **strength** and the **limitation** of geometric hallucination detection. It is the reason embeddings encode semantic similarity (enabling SGI and DGI), and it is also the reason DGI cannot detect human-crafted confabulations that mimic the distributional properties of grounded text (see [Confabulation Boundary](confabulation-boundary.md)).

## Sentence Transformer Training

Sentence transformers are typically trained with a contrastive objective. Given a set of positive pairs $(s_i, s_i^+)$ (semantically similar sentences) and negative pairs $(s_i, s_i^-)$ (dissimilar sentences), the training minimizes:

$$
\mathcal{L} = -\log \frac{e^{\text{sim}(\phi(s_i), \phi(s_i^+)) / \tau}}{\sum_j e^{\text{sim}(\phi(s_i), \phi(s_j)) / \tau}}
$$

where $\text{sim}$ is cosine similarity and $\tau$ is a temperature parameter. This objective creates an embedding space where:

- Paraphrases cluster together
- Entailing sentences are nearby
- Contradictions are distant
- Unrelated texts are scattered

The resulting geometry is not arbitrary --- it reflects genuine semantic structure that groundlens leverages for hallucination detection.

## The Unit Hypersphere $S^{n-1}$

Many sentence transformers produce embeddings that are approximately (though not exactly) unit-normalized. When we explicitly normalize embeddings to unit length, they lie on the **unit hypersphere**:

$$
S^{n-1} = \{\mathbf{v} \in \mathbb{R}^n : \|\mathbf{v}\| = 1\}
$$

This is an $(n-1)$-dimensional manifold embedded in $\mathbb{R}^n$. For $n = 384$, the hypersphere $S^{383}$ is the space where DGI's directional statistics operate.

### Properties of $S^{n-1}$

The unit hypersphere has several properties relevant to groundlens:

**Surface area.** The surface area of $S^{n-1}$ is:

$$
A_{n-1} = \frac{2\pi^{n/2}}{\Gamma(n/2)}
$$

For $n = 384$, this is an astronomically large number, reflecting the vast amount of "room" on a high-dimensional sphere.

**Geodesic distance.** The shortest path between two points on $S^{n-1}$ is the great-circle arc. The geodesic (angular) distance is:

$$
d_{\text{geo}}(\mathbf{u}, \mathbf{v}) = \arccos(\langle \mathbf{u}, \mathbf{v} \rangle)
$$

**Uniform distribution.** A uniform distribution on $S^{n-1}$ places equal probability density at every point. Two random unit vectors drawn uniformly from $S^{383}$ will have expected cosine similarity close to 0, with variance $\approx 1/n$. This concentration phenomenon is key to understanding why DGI works.

## Curse of Dimensionality

In high-dimensional spaces, distance metrics behave counterintuitively. Several phenomena are relevant to groundlens:

### Distance Concentration

For random points in $\mathbb{R}^n$, the ratio of maximum to minimum pairwise distance converges to 1 as $n \to \infty$ (Beyer et al., 1999)[^3]. In other words, in very high dimensions, all points are approximately equidistant from each other.

[^3]: Beyer, K. et al. (1999). When is "nearest neighbor" meaningful? *ICDT*.

$$
\lim_{n \to \infty} \frac{d_{\max} - d_{\min}}{d_{\min}} \to 0
$$

This seems like it should doom any distance-based method. However, sentence transformer embeddings are **not** random points --- they occupy a structured, low-dimensional submanifold of $\mathbb{R}^n$. The contrastive training creates meaningful distance variation within this submanifold.

### Cosine Similarity Concentration

For random unit vectors on $S^{n-1}$, cosine similarity concentrates around 0 with standard deviation $\approx 1/\sqrt{n}$:

$$
\mathbb{E}[\cos\theta] = 0, \quad \text{Var}[\cos\theta] \approx \frac{1}{n}
$$

For $n = 384$, this gives $\sigma \approx 0.051$. This means that cosine similarities of $\pm 0.1$ are already $\approx 2\sigma$ deviations from the mean --- statistically significant. DGI exploits this: a cosine similarity of 0.30 between the displacement direction and the reference direction is a $\approx 6\sigma$ event under the null hypothesis of random direction, giving high confidence in the grounding signal.

### The "Hub" Phenomenon

In high-dimensional spaces, some points become "hubs" that are nearest neighbors of disproportionately many other points (Radovanovic et al., 2010)[^4]. Sentence transformer embeddings exhibit this phenomenon to some degree. groundlens is robust to hubness because:

[^4]: Radovanovic, M. et al. (2010). Hubs in space: Popular nearest neighbors in high-dimensional data. *JMLR*.

- SGI uses distance **ratios** rather than absolute distances, which partially cancels hubness effects.
- DGI uses displacement **directions** rather than point positions, sidestepping hubness entirely.

## Displacement Vectors and Semantic Transformations

A central concept in DGI is the **displacement vector** from question to response:

$$
\delta = \phi(r) - \phi(q)
$$

This vector encodes the *semantic transformation* the LLM performed when generating the response. Geometrically, it points from the question's location in embedding space to the response's location.

The key insight is that grounded responses produce displacement vectors with a **consistent direction**. When you average the unit displacement vectors across many verified grounded pairs, you get a strong, non-zero mean direction $\hat{\mu}$. Hallucinated responses produce displacements that deviate from this mean.

This consistency is a consequence of the distributional hypothesis: grounded responses systematically shift the semantics from "question framing" toward "factual elaboration," and this shift has a characteristic geometric signature.

## Summary of Geometric Primitives Used by groundlens

| Primitive | Used by | Purpose |
|---|---|---|
| Euclidean distance $d(\mathbf{u}, \mathbf{v})$ | SGI | Measure proximity of response to question vs. context |
| Displacement vector $\delta = \phi(r) - \phi(q)$ | DGI | Capture the semantic transformation from question to response |
| Unit normalization $\hat{\mathbf{v}} = \mathbf{v} / \|\mathbf{v}\|$ | DGI | Project onto $S^{n-1}$ for directional analysis |
| Dot product $\hat{\delta} \cdot \hat{\mu}$ | DGI | Measure alignment with grounded reference direction |
| Mean direction $\hat{\mu}$ | DGI | Estimate the central tendency of grounded displacements |

## Further Reading

- [SGI Mathematics](sgi-mathematics.md) --- formal derivation of the distance ratio geometry
- [DGI Mathematics](dgi-mathematics.md) --- von Mises-Fisher distribution and directional statistics
- [Confabulation Boundary](confabulation-boundary.md) --- where the distributional hypothesis fails
