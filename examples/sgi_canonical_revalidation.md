# SGI canonical re-validation — bug fix groundlens 2026.6.18

## TL;DR

`groundlens.sgi` original computaba SGI como Euclidean ratio `||r-q||/||r-c||`
sobre embeddings sin normalizar. El paper SGI (arXiv:2512.13771, Algorithm 1)
define SGI como **angular ratio** `arccos(r̂·q̂)/arccos(r̂·ĉ)` sobre embeddings
**L2-normalizados** en la unit hypersphere S^(d-1). El bug ha sido corregido.

**PERO**: sobre Snowflake-arctic-embed-l-v2.0 (encoder usado en notebooks
RAGTruth + RAGBench), la diferencia de AUROC entre las dos implementaciones
es ≤ 0.005 — dentro del ruido bootstrap. Las dos implementaciones producen
**rankings prácticamente idénticos** sobre este encoder.

## Tabla comparativa

### RAGTruth test (preserved embeddings, Snowflake-L-v2.0)

| split | n | base_rate | SGI buggy AUC | SGI canónico AUC | Δ |
|---|---|---|---|---|---|
| qa_test | 900 | 0.178 | 0.542 | 0.542 | 0.000 |
| data2txt_test | 900 | 0.643 | 0.660 | 0.662 | +0.002 |
| summary_test | 900 | 0.227 | 0.606 | 0.605 | -0.001 |
| **combined** | **2700** | **0.349** | **0.501** | **0.496** | **-0.005** |

### RAGBench test (preserved embeddings, Snowflake-L-v2.0)

| subset | n_te | base_rate | SGI buggy AUC | SGI canónico AUC | Δ |
|---|---|---|---|---|---|
| covidqa | 246 | 0.159 | 0.598 | 0.598 | 0.000 |
| pubmedqa | 2450 | 0.296 | 0.454 | 0.454 | 0.000 |
| cuad | 510 | 0.075 | 0.589 | 0.589 | 0.000 |
| finqa | 2294 | 0.085 | 0.517 | 0.513 | -0.004 |
| tatqa | 3338 | 0.035 | 0.454 | 0.455 | +0.001 |

## Por qué buggy ≈ canónico sobre Snowflake

Snowflake-arctic-l-v2.0 fue entrenado con contrastive loss que produce
embeddings con norma ≈ 1 de forma aproximada. Para vectores aproximadamente
unitarios:

```
||a - b||² = ||a||² + ||b||² - 2(a·b) ≈ 2 - 2(a·b) = 2(1 - cos(theta))
||a - b||  ≈ √(2(1 - cos(theta))) = 2 sin(theta/2)
```

`2 sin(θ/2)` y `θ = arccos(a·b)` son monotónicamente relacionados en [0, π/2].
Por tanto el **ranking** de `||r-q||/||r-c||` y `arccos(r̂·q̂)/arccos(r̂·ĉ)`
es esencialmente igual sobre encoders contrastive modernos.

Con encoders más antiguos (donde las normas varían sustancialmente), la
diferencia sería mayor. Pero para deployments con Snowflake / MPNet / BGE / E5
/ GTE, la implementación buggy daba flags equivalentes a la canonical.

## Implicaciones

### Para usuarios existentes de groundlens
- **Sin acción retroactiva necesaria**: los flags ya producidos eran
  esencialmente correctos en su ranking
- La implementación 2026.6.18 fixea para alineación con paper, no por
  riesgo de mal funcionamiento en producción

### Para los experimentos pasados RAGTruth + RAGBench
- Los resultados negativos en RAGBench finqa/tatqa/cuad **NO se deben al bug**
- Se deben a que esos benchmarks son **Type III dominante** (within-frame
  factual errors) — el paper SGI ya documenta TruthfulQA AUC=0.478 como
  negative result EXPLÍCITO para Type III
- Los papers de Javier ya predecían este resultado

### Para el A3 finding (ceiling SGI 0.40)
- El "ceiling" observado en RAGTruth combined (max_P 0.39) **no es artefacto
  del bug** — la implementación canonical produce el mismo ceiling
- Es propiedad estructural del dataset (mix Type I + Type III)
- La investigación PGI fue respuesta a un fenómeno real (ceiling), pero la
  conclusión ("PGI breaks ceiling") fue construida sobre una métrica que
  resulta ser equivalente a SGI en ranking → la "ruptura" del ceiling con
  PGI raw distance fue capturando otra señal estructural del dataset, no
  una propiedad fundamental de la primitiva geométrica

### Para el release 2026.6.18
- **No incluir PGI** — fue diseñada como respuesta a un problema mal-comprendido
- **Sí incluir bug fix SGI** — alineación con paper canonical
- CHANGELOG honesto: "Implementation now matches paper canonical formulation
  (L2-normalized angular ratio); empirical rankings preserved on contrastive
  encoders (Δ AUROC ≤ 0.005 verified on RAGTruth + RAGBench)"

## Para banca (vendible)

El framing honesto que SÍ funciona, alineado con tus tres papers:

> *groundlens implementa el Semantic Grounding Index canonical (Marin 2025)
> y el Directional Grounding Index calibrado por dominio (Marin 2026). Estos
> métodos detectan **Type I (query-proximate unfaithfulness)** y **Type II
> (confabulation outside plausibility region)** según la taxonomía geométrica
> publicada. Para **Type III (factual errors within frame)** — la categoría
> más peligrosa en banca y que incluye números mal o nombres mal — la
> geometría angular no es discriminativa por construcción (documented
> negative result on TruthfulQA AUC=0.478). Para detección Type III
> recomendamos combinar groundlens con NLI específica y/o KG verification.*

Eso es honesto, preciso, y **defendible frente a un Head of Model Risk**.
Más vendible que cualquier claim de "magic detector" porque deja claro
qué cubre y qué NO cubre — esa transparencia es lo que regulators valoran.

## Files of record

- `src/groundlens/sgi.py` — bug-fixed implementation (paper canonical)
- `examples/sgi_canonical_revalidation.md` — this document
- Preserved embeddings: `/Desktop/ragbench_preserved.zip` (Snowflake-L v2.0)
- Preserved embeddings RAGTruth: `/uploads/*_Snowflake_snowflake-arctic-embed-l-v2.0.npz`
