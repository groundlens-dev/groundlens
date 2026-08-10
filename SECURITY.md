# Security

## Reporting

Report vulnerabilities privately through GitHub's "Report a vulnerability"
button on the Security tab of this repository. Please do not open a public issue
for anything exploitable.

Expect an acknowledgement within a week.

## What this library touches

`groundlens` reads untrusted text by definition — model output and retrieved
documents both. Two consequences shape the code:

- **No network access, ever.** The core has zero runtime dependencies and makes
  no outbound calls. The optional `[encoder]` extra downloads a model from
  Hugging Face on first use and nothing else.
- **Regex denial of service is a real risk here.** `NUMBER_PATTERN` bounds digit
  group repetition at 8 rather than using an unbounded `+`, which would backtrack
  quadratically on adversarial input. A test asserts a hostile 1,600-character
  numeral parses in under a second. Any change to that pattern must keep the
  bound and the test.

`max_anchors` caps how much work one call can do; it raises rather than quietly
taking a very long time on a pathological answer.
