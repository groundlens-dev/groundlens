# Cómo enseñarle a DGI tu dominio en una tarde

Esta guía explica `DGI.propose_labels()` en lenguaje sencillo. Si después de leerla algo te parece complicado, **abre un issue**: la opacidad es un bug, no una característica.

## El problema

DGI mide si una respuesta está bien anclada en una fuente. Para hacerlo necesita saber cómo se ven las respuestas correctas **en tu dominio**. Esa información vive en un vector llamado `mu_hat` que DGI compara con cada respuesta nueva.

Groundlens trae un `mu_hat` por defecto (212 pares en nueve dominios). Es un buen punto de partida, no una configuración de producción. La primera tarea en cualquier despliegue serio es construir tu propio `mu_hat`. Para eso necesitas 20–50 pares `(pregunta, respuesta correcta)` verificados de tu dominio.

El cuello de botella siempre es el mismo: nadie tiene esos 20–50 pares listos. `propose_labels` los genera con la ayuda de un LLM y un revisor humano.

## La idea, en tres frases

Le das a DGI unos pocos ejemplos correctos de tu FAQ. DGI le pide a un LLM que escriba versiones incorrectas de esas respuestas en cinco formas distintas, y te enseña las que más le confunden. Tú confirmas cuáles son realmente incorrectas, y DGI usa esa información para afinarse.

## Tres pasos

### Paso 1 — Reúne 10-20 ejemplos buenos

Un ejemplo es un `SeedExample`. Tres campos. Todos obligatorios.

```python
from groundlens import SeedExample

seed = SeedExample(
    context="Bizum permite enviar y recibir dinero entre cuentas de bancos "
            "espanoles usando el numero de telefono movil del destinatario. "
            "El limite por transaccion es de 1.000 EUR para particulares.",
    question="Cual es el limite por transaccion de Bizum para particulares?",
    grounded="El limite por transaccion de Bizum para particulares es de 1.000 EUR.",
)
```

- `context` — el párrafo de tu FAQ del que sale la respuesta. Tal cual aparece en tu corpus.
- `question` — una pregunta concreta cuya respuesta esté en ese párrafo.
- `grounded` — la respuesta correcta, redactada como te gustaría que tu LLM responda en producción.

Cada `SeedExample` se valida por sí mismo: si dejas cualquier campo vacío salta un `ValueError` antes de hacer ninguna llamada al LLM.

**Por qué se piden los tres juntos.** En versiones anteriores el `context` y la pregunta se combinaban al azar dentro del bucle, y el LLM acababa recibiendo "Contexto: hipoteca / Pregunta: Bizum", produciendo basura que el revisor humano marcaba como `out_of_scope`. Hoy cada `SeedExample` viaja entero al prompt, así que la generación queda coherente por construcción.

**Cuántos seeds.** 10 es el mínimo razonable para que la mediana del threshold sea estable. 20 es el sweet spot. Más allá de 50 no ayuda — lo que ayuda son más rondas, no más seeds.

### Paso 2 — Pide propuestas a DGI

```python
from groundlens import DGI

dgi = DGI()  # arranca desde el mu_hat genérico

def my_llm(prompt: str) -> str:
    # tu wrapper de OpenAI / Anthropic / local LLM
    ...

batch = dgi.propose_labels(
    seeds=my_seeds,                # tu lista de SeedExample
    llm_generate=my_llm,
    n_candidates=50,               # default; ≈5 min a 4 s/llamada
    n_to_label=10,                 # default; cuántos ve el revisor
    strategies="default",          # las 5 del paper grounding-benchmark
    seed=42,                       # determinismo para auditorías
)
```

Lo que pasa por dentro, en cuatro viñetas, sin matemáticas:

1. DGI calcula la **mediana** de sus propios scores sobre tus seeds. Esa mediana es el "punto medio" provisional entre correcto e incorrecto.
2. DGI sortea un seed, mete su `(context, question, grounded)` en una de las cinco plantillas de confabulación, y se lo manda al LLM. Repite `n_candidates` veces, distribuyendo entre las cinco estrategias.
3. Para cada respuesta confabulada, DGI calcula su propio score y mide cuánto se aleja de la mediana. Cuanto menos se aleja, más "duda" DGI sobre si es correcta o no.
4. Devuelve los `n_to_label` candidatos sobre los que más duda (70%) + algunos extra para que aparezcan las cinco estrategias (30%).

Devuelve un `PropositionBatch` con cuatro atributos. Sólo `items` y `review_template` te hacen falta hoy; los otros dos son para auditoría posterior:

| Atributo | Para qué sirve |
|---|---|
| `batch.items` | Los `n_to_label` candidatos seleccionados, ordenados de más a menos dudoso |
| `batch.review_template` | Markdown listo para pegar a un revisor humano |
| `batch.all_candidates` | Los `n_candidates` completos, ordenados por incertidumbre (auditoría) |
| `batch.strategies_used` | Nombres de las estrategias que se usaron en esta ronda |

### Paso 3 — Etiqueta y calibra

Pasa `batch.review_template` a un revisor humano. Lo ideal: dos revisores en paralelo, reconcilias desacuerdos.

```markdown
### Item 1/10 — strategy: redefinition
> FAQ context excerpt: Bizum permite enviar...
**Question:** Cual es el limite por transaccion de Bizum?
**Candidate response:** Bizum permite enviar dinero ilimitadamente a particulares.
[ ] grounded   [x] fabricated   [ ] out_of_scope
```

Una vez tengas las etiquetas, te quedas con los `grounded` y los pasas a `DGI.calibrate()` junto con tus seeds originales:

```python
reviewer_grounded = [
    (item.question, item.candidate_response)
    for item, label in zip(batch.items, human_labels, strict=True)
    if label == "grounded"
]

calibration_pairs = [(s.question, s.grounded) for s in my_seeds] + reviewer_grounded
dgi.calibrate(pairs=calibration_pairs)
```

Tu DGI ya está más afinado. Si quieres una ronda más, repite el paso 2 con el nuevo `mu_hat` activo.

## Qué hacer cuando algo va mal

**El revisor dice `out_of_scope` en casi todo.**
Casi siempre significa que el encoder no entiende tu idioma. El default `all-MiniLM-L6-v2` es mayoritariamente inglés. Para español o multilingüe:

```python
from groundlens import DGI, MULTILINGUAL_MINI
dgi = DGI(model=MULTILINGUAL_MINI)
```

Si seguía después de eso, revisa que tu `grounded` sea realmente correcto frente al `context`. Si el seed está mal, todos los confabulados serán raros.

**AUROC no mejora tras calibrar.**
Necesitas más rondas, más seeds, o seeds más diversos. La regla simple: si dos rondas seguidas no mueven AUROC más de ±0.02 en tu held-out set, has plateado.

**AUROC baja tras calibrar.**
Síntoma clásico de seeds inconsistentes. Revisa que todos tus `SeedExample.grounded` digan lo mismo que el `context` afirma. Un seed contradictorio envenena `mu_hat`.

**Tarda demasiado.**
`n_candidates=50` con OpenAI cuesta unos 4-5 minutos a 4 segundos por llamada. Si necesitas iterar más rápido, baja `n_candidates` a 20 para una primera vuelta exploratoria, luego sube.

## Cuándo parar

Cuando dos rondas seguidas no mejoren AUROC en tu held-out set por encima de ±0.02. A partir de ahí estás pagando llamadas al LLM y tiempo de revisor para ganar ruido.

Una vez en producción, recalibra cuando la distribución de DGI scores sobre tu tráfico real se desvíe del rango de calibración. Eso quiere decir que tu dominio se está moviendo (nuevos temas, nuevos productos) y `mu_hat` tiene que moverse con él.

## Detalles para los curiosos

Si has llegado hasta aquí y quieres entender el resto del mecanismo:

- **Las cinco estrategias** vienen de [`groundlens-dev/grounding-benchmark`](https://github.com/groundlens-dev/grounding-benchmark) (CC BY 4.0). Cada una conserva una propiedad distinta del embedding mientras viola la verdad referencial: `redefinition`, `mechanism_inversion`, `entity_composition`, `polysemy`, `template_filling`.
- **Acquisition function.** Mix 70% incertidumbre (distancia a la mediana del threshold) + 30% diversidad de estrategia. Lo puedes ajustar con `diverse_fraction`.
- **Estrategias custom.** Pasa una tupla `((name, prompt_template), ...)` en `strategies`. Las plantillas aceptan los slots `{context}`, `{question}`, `{grounded}`.
- **No-circularidad.** DGI ordena los candidatos por incertidumbre; el humano asigna las etiquetas. Las etiquetas que vuelven a calibrar `mu_hat` nunca las puso DGI.

## Referencias

- Marin, J. (2026). *A Methodology for Building Human-Confabulated Hallucination Benchmarks*. [groundlens-dev/grounding-benchmark](https://github.com/groundlens-dev/grounding-benchmark). CC BY 4.0.
- Marin, J. (2026). *A Geometric Taxonomy of Hallucinations in LLMs*. arXiv:2602.13224v3.

## Ver también

- [Domain Calibration](domain-calibration.md) — qué hacer con los pares ya etiquetados.
- [Banking Deployment](banking-deployment.md) — patrón completo de despliegue con audit log + compliance.
