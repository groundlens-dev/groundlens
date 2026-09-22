# GroundLens Verification Suite

GroundLens is not scored. It is checked.

This suite demonstrates GroundLens the way trust infrastructure is demonstrated:
by what it does, not by a single number. It has separate parts, each measured on
its own terms.

## Conformance — does it do what it says?

`conformance.py` runs canonical executions through the engine and asserts the
behaviours GroundLens promises, grouped by contract. The result is PASS or FAIL
per contract, never a score.

    pip install groundlens
    python suite/conformance.py          # human report; exit 1 if any contract fails
    python suite/conformance.py --json   # machine-readable

Contracts checked: evidence generation (a verifier produces structured evidence
with a source span), policy semantics (the policy decides, not the verifier; the
EU AI Act policy maps to articles), decision determinism (same input, same content
hash and decision; a fixed key gives a fixed signer identity), record integrity (a
fresh record verifies; a chain links and verifies), tamper detection (an altered
decision, signature or piece of evidence is rejected), offline verification (records
verify with the network disabled), and scope boundaries (only the given evidence is
a source, never the question).

It uses only the deterministic verifiers, so it needs no model bundle and no network.

## Coming next

Performance (latency, throughput, record overhead on a fixed, disclosed machine),
interoperability (a record verified across CLI, Python and an independent verifier),
and verifier evaluation (per-verifier detection metrics such as FPR at 95% recall —
a measurement of the verifiers, not of the infrastructure).
