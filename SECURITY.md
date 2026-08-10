# Security policy

## Supported versions

| Version | Supported |
|---|---|
| 3.x | yes |
| 2.x and earlier | no — see [RETRACTIONS.md](RETRACTIONS.md) |

## Reporting a vulnerability

Report privately through GitHub Security Advisories:

**https://github.com/groundlens-dev/groundlens/security/advisories/new**

Please do not open a public issue for anything exploitable.

**What to expect.** Acknowledgement within 7 days. An assessment with a fix or a
rejection within 30 days. If a fix ships, you are credited in the advisory unless
you ask otherwise. If we disagree that a report is a vulnerability, you get the
reasoning in writing and you are free to disclose.

**Disclosure.** Coordinated. We ask for 90 days from acknowledgement, or until a
fix is released, whichever comes first.

## What this library touches

`groundlens` reads untrusted text by definition — model output and retrieved
documents both. Two consequences shape the code.

**No network access, ever.** The core has zero runtime dependencies and makes no
outbound calls. The optional `[encoder]` extra downloads a model from Hugging
Face on first use, and nothing else. A CI job asserts the deterministic path
imports nothing outside the standard library.

**Regular-expression denial of service is a real risk here.** `NUMBER_PATTERN`
bounds digit-group repetition at 8 rather than using an unbounded `+`, which
would backtrack quadratically on adversarial input. A unit test asserts a hostile
1,600-character numeral parses in under a second, and ClusterFuzzLite fuzzes the
numeral and segmentation path on every pull request that touches it. Any change
to that pattern must keep the bound, the test and the fuzz target.

`max_anchors` caps the work a single call can do; it raises rather than quietly
taking a very long time on a pathological answer.

## Out of scope

- Findings that require the caller to pass a deliberately hostile `Encoder`.
  The protocol is an extension point; implementing it is trusting it.
- Vulnerabilities in optional dependencies. Report those upstream; we will pick
  up the fix. Dependabot and OSV-Scanner run weekly here.
- Anything in versions before 3.0.0. That tree is retracted, not maintained.
