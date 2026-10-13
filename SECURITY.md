# Security policy

## Supported versions

| Version | Supported |
|---|---|
| latest release | yes |
| earlier 5.x and 4.x | no: upgrade to the latest release; records they wrote stay verifiable |
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
package have no runtime dependencies and make no outbound calls of their own;
a CI job fails the build if an HTTP or TLS crate ever reaches an engine crate.

Everything that talks to another system does it through a client you create
and pass in: the judge (your OpenAI, Azure or Bedrock client), the signers
(your KMS, Key Vault or PKCS#11 session), the sinks (your S3, Blob or
database connection) and the observability connectors (your OpenTelemetry
providers or Langfuse client). GroundLens holds no credentials and opens no
connection you did not configure. What the judge sees is exactly the prompt
`groundlens judge show-template` prints; text in a passage is data inside
that prompt, never an instruction, and adversarial tests check it.

The deprecated model channels add one command that downloads:
`groundlens bundle pull`, which the user runs explicitly. The download is
compared with a hash pinned in the engine before a single file is unpacked,
and archives with links or paths that escape the target directory are
refused.

**Regular-expression denial of service is a real risk here.** The numeral
grammar bounds digit-group repetition instead of using an unbounded `+`,
which would backtrack quadratically on adversarial input. Tests keep that
bound, and cargo-fuzz targets under `fuzz/` exercise the numeral, quantity,
normalisation and policy parsers.

**Records are only as good as their verification.** Every record carries
its content hash, the hash of the previous record and a signature: Ed25519
with a local key, or ECDSA P-256 from a KMS or HSM. `groundlens record verify`
recomputes all of them, offline, with the public key alone. A bundle is re-hashed
artefact by artefact when it is opened; a mismatch refuses to start.

## Out of scope

- Findings that require a deliberately hostile bundle installed by the
  operator. A bundle directory is trusted like any other installed software;
  `bundle pull` is the guarded path.
- Vulnerabilities in the clients you pass in (model, key, storage and
  observability SDKs). Report those to their vendors.
- Vulnerabilities in build-time dependencies. Report those upstream; we will
  pick up the fix. Dependabot, OSV-Scanner and Scorecard run weekly here.
- Anything in versions before 3.0.0. That tree is retracted, not maintained.
