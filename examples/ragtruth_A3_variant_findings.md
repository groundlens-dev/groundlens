# A3 — SGI precision ceiling investigation

## TL;DR

El techo de precisión 0.40 sobre RAGTruth **no es del approach geométrico**. Es de la fórmula Euclidean ratio específica de SGI. Dos variantes nuevas lo rompen.

## Variantes testeadas

Todas computables sobre los mismos embeddings cached (sin GPU, sin re-entrenar).

| Variante | Fórmula | Test max_P | Test AUROC |
|---|---|---|---|
| **SGI Euclidean (actual)** | `\|\|r - q\|\| / \|\|r - c\|\|` | 0.392 | 0.501 |
| **1 − cos(r, c)** | Similitud directa al contexto, negativa = ungrounded | **0.545** | **0.679** |
| **Perpendicular distance** | Distancia de r a la línea que conecta q y c en el espacio embedding | **0.639** | **0.718** |
| SGI cosine ratio | `cos(r,q) − cos(r,c)` | 0.383 | 0.468 |
| SGI normalizada por ‖c‖ | Mismo SGI escalado por context norm | 0.392 | 0.501 |
| SGI + cos_diff z-sum | Combinación lineal z-normalizada | 0.387 | 0.479 |

## Validación train vs test (no leakage)

Las variantes que rompen el ceiling lo hacen **consistentemente** entre train y test:

| Variante | Train max_P (n=15090) | Test max_P (n=2700) |
|---|---|---|
| SGI | 0.484 | 0.392 |
| 1 − cos(r,c) | 0.574 | 0.545 |
| Perpendicular | 0.630 | 0.639 |

No es overfitting al test. El patrón es estructural.

## Interpretación geométrica de la "perpendicular distance"

Para cada (q, c, r):
1. Construye la línea L que conecta `φ(q)` y `φ(c)` en el embedding space
2. Proyecta `φ(r)` ortogonalmente sobre L
3. Mide la distancia perpendicular de `φ(r)` a su proyección

Si `r` está grounded en `c` mediante `q`, geométricamente debería vivir cerca del segmento qc (el contexto responde a la pregunta, la respuesta se sitúa entre los dos). Si `r` se aleja perpendicularmente del segmento, está inventando algo que no está ni en `q` ni en `c` — espacio de fabricación.

Esto es una intuición geométrica **distinta** de la del paper SGI original (ratio de distancias). Más cercana al concepto de "el response embedding debería vivir en el subespacio span(q, c) si está grounded".

## Per-task

| Task | base_rate | perp max_P | perp AUROC | SGI max_P | SGI AUROC |
|---|---|---|---|---|---|
| qa | 0.178 | 0.227 | 0.561 | 0.273 | 0.542 |
| data2txt | 0.643 | **0.944** | 0.645 | 0.923 | 0.660 |
| summary | 0.227 | **0.538** | 0.608 | 0.457 | 0.606 |

`perpendicular` gana a SGI en data2txt y summary. En qa pierde — SGI 0.273 vs perp 0.227. **No es universal**: cada formulación cubre mejor cierta clase de hallucinations.

## Per-type recall — trade-off

En su punto de máxima precisión (P=0.639), `perpendicular` sacrifica recall fuertemente:

| Tipo | perp recall @ max P | (95% CI) | SGI @ max P | Llama-FT (paper) | n |
|---|---|---|---|---|---|
| Evident Conflict | 0.267 | [0.226, 0.304] | 0.728 | 0.383 | 459 |
| Subtle Conflict | 0.199 | [0.000, 0.444] | 0.479 | 0.025 | 15 |
| Evident Baseless | 0.254 | [0.220, 0.286] | 0.742 | 0.558 | 542 |
| Subtle Baseless | 0.296 | [0.222, 0.373] | 0.864 | 0.529 | 141 |

A su máxima precisión, `perpendicular` está por debajo de `SGI@maxP` en todos los tipos.

## Conclusión técnica

Esto no es "encontramos una variante que vence a SGI". Es **groundlens debería ofrecer DOS primitivas geométricas con perfiles operativos distintos**:

### Para screen de alta recall (catch broadly, low precision)
- Primitiva: **SGI Euclidean** (la actual)
- Operating: P ≈ 0.39, R ≈ 0.74, F1 ≈ 0.51
- Caso: pre-filtro antes de revisión humana o detector más caro

### Para triage de alta precisión (catch fewer but cleaner)
- Primitiva: **PGI** (Perpendicular Grounding Index) — nombre tentativo
- Operating: P ≈ 0.64, R ≈ 0.24, F1 ≈ 0.35
- Caso: flagging de auto-deferral en producción donde precision importa

## Implicaciones para publicación

**Cambia el framing del post LinkedIn**:

Antes (con solo SGI):
> "Training-free geometric grounding matches GPT-3.5 prompt at zero LLM cost — operates as a high-recall screen"

Después (con PGI añadida):
> "Two geometric grounding primitives cover complementary operating regimes on RAGTruth — SGI for high-recall screening (R=0.74 at P=0.39), PGI for high-precision triage (P=0.64 at R=0.24), both training-free and encoder-only"

Es una historia más rica, defendible, y abre un research line concreto para groundlens.

## Próximos pasos sugeridos

1. **Implementar PGI en groundlens** como nueva primitiva. ~30 líneas de código. Verificar en tests.
2. **Antes de Notebook 2 (RAGBench)**: validar PGI sobre RAGBench. Si reproduce el patrón, **es publicable como contribución técnica nueva** (no solo benchmark).
3. **Investigar combinación SGI × PGI** vía calibración Platt — podría dar mejor F1 que cualquiera de los dos por separado.
4. **Bookkeeping**: añadir issue en groundlens repo documentando la limitación de SGI Euclidean y la propuesta de PGI.

## Archivos generados

- `ragtruth_A3_variant_findings.md` — este documento
- Sweep de variantes corrido sobre embeddings preservados (sin GPU)

## Próximo paso operativo

Aplicar 5-check sobre Notebook 2 (RAGBench) con la pregunta nueva incorporada: ¿reproduce RAGBench el split entre SGI (high-recall) y PGI (high-precision)?
