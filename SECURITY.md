# Security policy

## Supported versions

| Version | Supported |
|---|---|
| 4.x | yes |
| 3.x | no: it is the previous Python implementation, kept at tag `v3.1.0` for reproducibility |
| 2.x and earlier | no, and its published figures were withdrawn |

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

## What this software touches

GroundLens reads untrusted text by definition: model output and retrieved
documents both. Three consequences shape the code.

**No network access in the engine, ever.** The Rust engine and the Python
package have no runtime dependencies and make no outbound calls; a CI job
fails the build if an HTTP or TLS crate ever reaches an engine crate. The
one command that opens a connection is `groundlens bundle pull`, which the
user runs explicitly; the download is compared with a hash pinned in the
engine before a single file is unpacked, and archives with links or paths
that escape the target directory are refused.

**Regular-expression denial of service is a real risk here.** The numeral
grammar bounds digit-group repetition instead of using an unbounded `+`,
which would backtrack quadratically on adversarial input. Tests keep that
bound, and cargo-fuzz targets under `fuzz/` exercise the numeral, quantity,
normalisation and policy parsers.

**Records are only as good as their verification.** Every record carries
its content hash, the hash of the previous record and an Ed25519 signature;
`groundlens record verify` recomputes all of them. A bundle is re-hashed
artefact by artefact when it is opened; a mismatch refuses to start.

## Out of scope

- Findings that require a deliberately hostile bundle installed by the
  operator. A bundle directory is trusted like any other installed software;
  `bundle pull` is the guarded path.
- Vulnerabilities in build-time dependencies. Report those upstream; we will
  pick up the fix. Dependabot, OSV-Scanner and Scorecard run weekly here.
- Anything in versions before 3.0.0. That tree is retracted, not maintained.
