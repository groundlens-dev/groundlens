# GroundLens Verification Suite

GroundLens is not scored. It is checked.

Trust infrastructure is demonstrated by what it does, not by a single number. This
suite is that demonstration, and anyone can run it. It has four parts, each measured
on its own terms.

## Conformance — does it do what it says?

Canonical executions run through the engine, asserting the contracts GroundLens
promises: evidence generation, policy semantics, decision determinism, record
integrity, tamper detection, offline verification, and scope boundaries. The result
is PASS or FAIL per contract, never a score. Includes adversarial checks: an altered
decision, signature or piece of evidence is rejected, and verification runs with the
network disabled.

    python suite/conformance.py            # exit 1 if any contract fails
    python suite/conformance.py --json

## Performance — the operational numbers

Per-property percentiles, the way OpenTelemetry and Open Policy Agent report theirs:
latency to verify an answer, latency to verify a sealed record offline, record size,
and throughput. Numbers are environment-specific, so the report prints the machine it
ran on.

    python suite/performance.py
    python suite/performance.py --json

## Interoperability — verifiable by someone else

One sealed record, verified by three separate verifiers: the Python API, the
`groundlens record verify` command line, and an independent from-scratch verifier
that shares no code with the engine (it recomputes the hashes with `hashlib` and
checks the Ed25519 signature with `cryptography`, from the record format alone). Then
a tampered record, rejected by all three.

    pip install cryptography
    python suite/interoperability.py
    python suite/interoperability.py --json

## Verifier evaluation — the detectors, measured

Detection metrics for the individual verifiers (false-positive rate at 95% recall,
AUROC, balanced accuracy) on public datasets. This measures the verifiers, which are
swappable, not the infrastructure. See `verifier_evaluation/`.

## Not invented here

Every check traces to a public standard, RFC or regulation, and the suite/score split
follows the shape used by conformity assessment and by infrastructure projects like
Open Policy Agent, OpenTelemetry and W3C. See [STANDARDS.md](STANDARDS.md).
