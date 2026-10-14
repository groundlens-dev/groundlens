<!-- mcp-name: io.github.groundlens-dev/groundlens -->

<div align="center">

![GroundLens](https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/groundlens_header.png)

# GroundLens: verification for LLM answers. 

#### Every answer gets a decision you can act on and a signed record you can audit.**

[![PyPI](https://img.shields.io/pypi/v/groundlens?color=1a4fd6)](https://pypi.org/project/groundlens/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![Docs](https://readthedocs.org/projects/groundlens/badge/?version=latest)](https://groundlens.readthedocs.io/en/latest/)
[![Python](https://github.com/groundlens-dev/groundlens/actions/workflows/python.yml/badge.svg)](https://github.com/groundlens-dev/groundlens/actions/workflows/python.yml)
[![Rust](https://github.com/groundlens-dev/groundlens/actions/workflows/rust.yml/badge.svg)](https://github.com/groundlens-dev/groundlens/actions/workflows/rust.yml)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/groundlens-dev/groundlens/badge)](https://scorecard.dev/viewer/?uri=github.com/groundlens-dev/groundlens)
[![SLSA](https://slsa.dev/images/gh-badge-level2.svg)](https://slsa.dev)

<br>

<a href="#langfuse"><img src="https://cdn.brandfetch.io/langfuse.com/w/240/h/64/theme/light/logo?c=BRANDFETCH_CLIENT_ID" height="26" alt="Langfuse"></a>&nbsp;&nbsp;&nbsp;&nbsp;
<a href="#grafana-and-opentelemetry"><img src="https://cdn.brandfetch.io/grafana.com/w/240/h/64/theme/light/logo?c=BRANDFETCH_CLIENT_ID" height="26" alt="Grafana"></a>&nbsp;&nbsp;&nbsp;&nbsp;
<a href="#grafana-and-opentelemetry"><img src="https://cdn.brandfetch.io/opentelemetry.io/w/240/h/64/theme/light/logo?c=BRANDFETCH_CLIENT_ID" height="26" alt="OpenTelemetry"></a>&nbsp;&nbsp;&nbsp;&nbsp;
<a href="#mcp"><img src="https://cdn.brandfetch.io/modelcontextprotocol.io/w/240/h/64/theme/light/logo?c=BRANDFETCH_CLIENT_ID" height="26" alt="Model Context Protocol"></a>

</div>

<br>

## Quickstart

```python
# pip install groundlens
import groundlens as gl

verifier = gl.Verifier(sink=gl.sinks.jsonl("records/"))
record = verifier.check(answer="Revenue was €42.1 million.", passages=["Revenue reached €41.2 million."])
print(record.decision, record.reasons)
```

```text
FAIL ['c2: groundlens.numeric contradicted: €42.1 million not in sources; nearest 41200000 EUR in ctx-0 (relative distance 0.021)']
```

Runs locally: no account, no API key, no model, no network. The signed record is in `records/` before `check` returns.

The same check, wired into your stack:

<a name="langfuse"></a>
<details open>
<summary><b>Langfuse</b> · <code>pip install "groundlens[langfuse]"</code></summary>

```python
from langfuse import get_client
verifier = gl.Verifier(sink=gl.sinks.jsonl("records/"), observers=[gl.integrations.langfuse(get_client())])
```

- **Score:** `groundlens.decision`, categorical, values `PASS`, `REVIEW`, `FAIL`. Filter traces by it, chart it, export it.
- **Observation:** `groundlens.check`, type `guardrail`, inside the trace that produced the answer. Level `WARNING` on REVIEW, `ERROR` on FAIL; the reasons are its status message, one per line.
- **Judge:** a `generation` observation with the model name, next to your own model calls.
- **Spans:** one per verifier, plus the store, each with its duration.
- **SDK:** Python v3 and v4, Langfuse Cloud and self-hosted. Tested on Langfuse 4.58.

</details>

<a name="grafana-and-opentelemetry"></a>
<details open>
<summary><b>Grafana and OpenTelemetry</b> · <code>pip install "groundlens[otel]"</code></summary>

```python
verifier = gl.Verifier(sink=gl.sinks.jsonl("records/"), observers=[gl.integrations.otel()])
```

Spans and metrics go through the providers your application already configured: Tempo, Prometheus, or any OpenTelemetry backend.

- **Metrics:** `groundlens_decisions_total{decision, policy}`, `groundlens_reasons_total{reason, decision}`, `groundlens_check_duration_seconds{stage}` with stage `total`, `engine`, `judge`, `sign`, `store`.
- **Spans:** `groundlens.check` with `groundlens.decision`, `groundlens.reasons`, record id and hash; children per verifier, the judge (`gen_ai.*`) and the store.
- **Dashboard:** the one in the image. `gl.integrations.grafana_dashboard()` returns the path of its JSON; import it in **Dashboards → New → Import**.
- **PromQL, share of answers that failed:**

  ```promql
  sum(rate(groundlens_decisions_total{decision="FAIL"}[15m])) / sum(rate(groundlens_decisions_total[15m]))
  ```

- **Alert when more than 5 % fail:**

  ```yaml
  - alert: GroundLensFailRateHigh
    expr: sum(rate(groundlens_decisions_total{decision="FAIL"}[15m])) / sum(rate(groundlens_decisions_total[15m])) > 0.05
    for: 10m
  ```

- **Try it:** `docker run -p 3000:3000 -p 4318:4318 grafana/otel-lgtm`, then `python examples/observability/credit_copilot.py grafana --minutes 5`. Tested on Grafana 12 with Tempo and Prometheus.

</details>

<a name="mcp"></a>
<details open>
<summary><b>MCP</b> · <code>pip install "groundlens[mcp]"</code></summary>

```json
{ "mcpServers": { "groundlens": { "command": "groundlens-mcp" } } }
```

Tools: `verify_answer`, `verify_run`, `verify_records`, over stdio. An agent checks its own draft before it answers.

</details>

**Both connectors:** no text of questions, answers or passages is sent unless you pass `capture_text=True`. Exact checks add about 3 ms at p95 per answer (measured on 2 CPU cores); a judge adds one call to your model. GroundLens has no telemetry and never contacts us.

<br>

## Architecture

GroundLens splits verification into five parts that never mix: **claims**, **verifiers**, **evidence**, **policy** and **record**.

1. The answer is cut into **claims**: each figure and each sentence, with its character offsets.
2. **Verifiers** examine each claim against the passages and return evidence (`supported`, `contradicted`, `unsupported`), never a verdict. The shipped ones are exact: numeric (exact fractions, locales, units, recomputed sums and ratios), scope, intent, and your rules. The judge, if you connect one, is the model you already use, asked through a fixed template.
3. The **evidence graph** keeps what each verifier said about each claim, and where they disagree.
4. The **policy**, a YAML file you own, turns evidence into a decision: `PASS`, `REVIEW` or `FAIL`, with reasons.
5. The **record** holds the input hash, the evidence, the policy hash and the decision, chained to the previous record and signed. It is stored before `check` returns; observers are told after.

The engine is Rust (`crates/gl-core`, `gl-numeric`, `gl-verifiers`, `gl-policy`, `gl-record`, `gl-engine`), shipped as a Python wheel (abi3, Python 3.10+) and as the `glv` binary. It runs in your process: no server, no network, no runtime dependencies.

<br>

## Parameters and capabilities

| Parameter of `Verifier` | Options |
|---|---|
| `policy` | `groundlens_default_v1` (default), `eu_ai_act_high_risk_v1`, or your YAML, which can `extends` either |
| `signer` | `local_key` (development), `aws_kms`, `azure_key_vault`, `pkcs11` |
| `sink` | `jsonl`, `s3_object_lock`, `azure_blob`, `postgres` |
| `judge` | `openai_compatible` (OpenAI, vLLM, Ollama…), `azure_openai`, `bedrock`; optional |
| `observers` | `integrations.langfuse`, `integrations.otel`, or your own |
| `locale`, `rounding` | how numbers are read and compared |

| Parameter of `check` | |
|---|---|
| `answer`, `passages` | required; passages as strings or `(id, text, provenance)` |
| `question` | enables the intent check: the answer gives the kind and unit asked for |
| `scope` | what the request is about (`{"entity": "ACME"}`): a figure from another entity fails |
| `risk_class` | a class your policy can send to human review whatever the checks say |

A policy, in full:

```yaml
id: credit_desk
version: 1.0.0
extends: eu_ai_act_high_risk_v1
scope:
  required: [entity]
risk_classes:
  default: credit_information
  mandatory_review: [credit_limit_change]
```

Also: `groundlens measure` estimates the share of wrong answers among those that passed, from a small labelled sample, with a confidence interval; `groundlens replay` shows which past decisions a policy change would flip. Full documentation: [groundlens.readthedocs.io](https://groundlens.readthedocs.io).

<br>

## Security

GroundLens sits on the path between a model and a decision, and its records are meant to be evidence. Both make it a target: an attacker may try to get a wrong answer through, or to alter the trail afterwards.

| Threat | Control |
|---|---|
| A wrong answer passes | Exact checks with no model in the default path; errors and timeouts are `REVIEW`, never `PASS`; no stored record, no decision |
| Instructions hidden in passages steer the judge | Passages are delimited data in a fixed, versioned template; the judge can only escalate; adversarial tests |
| A record is edited, deleted or reordered | SHA-256 content hash, hash chain, signature; `groundlens record verify` checks offline with the public key alone |
| The signing key leaks | Keys stay in AWS KMS, Azure Key Vault or a PKCS#11 HSM (ECDSA P-256); GroundLens never holds them |
| Two writers fork a chain | Conditional writes in every sink; a lost race is retried, never overwritten |
| Data leaves through the verifier | No network code in the engine (`cargo-deny` bans HTTP and TLS crates); other systems are reached only through clients you pass in |
| Hostile input exhausts the parser | Bounded numeral grammar against regular-expression DoS; fuzzing of every parser |
| A tampered release | Pinned and hashed CI dependencies, SLSA level 2 provenance, signed release binaries, OpenSSF Scorecard |

Report vulnerabilities privately through [GitHub security advisories](https://github.com/groundlens-dev/groundlens/security/advisories/new). See [SECURITY.md](SECURITY.md).

<br>

## Contributing

If GroundLens got one of your answers wrong, that case is the most valuable contribution there is. Checks, connectors and documentation are welcome too; [CONTRIBUTING.md](CONTRIBUTING.md) explains how to start.

<br>

## Open source

Apache-2.0, all of it: engine, checks, policies, connectors, command line and MCP server. Verification evidence has to be checkable by anyone, without our software or our permission, and that only holds if the verifier is open. 

> Not included: a hosted service, and a the judge model.

<br>

## Contact

You can contact the developer at javier@groundlens.dev

<br>

<div align="center">

<sub>Copyright Groundlens 2026</sub>

</div>
