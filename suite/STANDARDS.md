# Where these checks come from

Trust infrastructure does not invent its tests. It re-uses established primitives
and states which behaviour each test demonstrates. Every check in this suite traces
to a public standard, an RFC, or a regulation. Nothing here is graded on a scale of
our own making.

| Suite check | What it demonstrates | Grounded in |
|---|---|---|
| Evidence generation | Each claim carries structured evidence naming what was checked, by which verifier and version, and the source span it rests on | The attestation pattern of **in-toto** attestations and **SLSA** provenance (record what was produced and how); **C2PA** assertions that bind a claim to its source |
| Policy semantics | The policy decides, not the verifier; the same evidence under two policies gives two decisions; a high-risk policy maps to named regulation | **Open Policy Agent** policy-as-code (policy separated from mechanism); **EU AI Act** Art. 12 (record-keeping and logging) and Art. 15 (accuracy, robustness, cybersecurity) |
| Decision determinism | The same input yields the same content hash | **RFC 8785** JSON Canonicalization Scheme (one serialisation, one hash); the reproducible-builds principle |
| Record integrity | Content hash, record hash and signature recompute and agree; records chain | **FIPS 180-4** SHA-256; **RFC 8032** Ed25519 signatures; append-only hash chaining as in **RFC 9162** Certificate Transparency (Merkle logs) |
| Tamper detection | A record with an altered decision, signature or piece of evidence is rejected | Tamper-evidence as in **C2PA** manifests and **W3C Verifiable Credentials 2.0** (tamper-evident, verifiable proofs) |
| Offline / independent verification | A record verifies with no network, and by a party other than its maker | **SLSA** verifiable provenance; the verifier role of **W3C Verifiable Credentials**; demonstrated in code by the interoperability part's from-scratch verifier |
| Scope boundaries | Only the given evidence is a source; the question is never treated as one | Normative requirement keywords, **RFC 2119** / **RFC 8174** (MUST / MUST NOT) |

## Why a suite and not a score

Splitting conformance from performance, and reporting properties instead of one
number, is the established shape for trust and infrastructure projects, not a choice
of ours:

- **Conformity assessment** (**ISO/IEC 17000**) is defined as demonstrating that
  specified requirements are met, check by check, not as a single grade.
- **Open Policy Agent** and the **OpenTelemetry Collector** publish performance
  benchmarks across separate dimensions (latency, throughput, CPU, memory), never a
  combined "quality score".
- **W3C** ships conformance test suites to show a specification is met and that
  implementations interoperate, not to rank them.

GroundLens follows the same shape. The verifier-evaluation part reports detection
metrics such as false-positive rate at 95% recall, and those numbers describe the
individual verifiers, which are swappable, never the infrastructure as a whole.

## References

- RFC 8032 (Ed25519), RFC 8785 (JSON Canonicalization Scheme), RFC 9162
  (Certificate Transparency 2.0), RFC 2119 / RFC 8174 (requirement keywords)
- FIPS 180-4 (SHA-256)
- SLSA (slsa.dev), in-toto attestations (in-toto.io)
- C2PA / Content Credentials (c2pa.org)
- W3C Verifiable Credentials Data Model 2.0 (w3.org/TR/vc-data-model-2.0)
- Open Policy Agent (openpolicyagent.org), OpenTelemetry (opentelemetry.io)
- ISO/IEC 17000 (conformity assessment vocabulary)
- EU AI Act, Regulation (EU) 2024/1689, Articles 12 and 15
