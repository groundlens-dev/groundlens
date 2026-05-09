# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 2026.4.x (latest) | Yes |
| < 2026.4.0 | No |

Only the latest CalVer release receives security patches.

## Reporting a vulnerability

**Do not open a public issue for security vulnerabilities.**

Email **javier@jmarin.info** with:

- A description of the vulnerability
- Steps to reproduce
- Affected versions
- Any potential impact assessment

### What to expect

- **Acknowledgment:** within 48 hours of your report.
- **Initial assessment:** within 5 business days. We will confirm whether the report is accepted, request additional information, or explain why it does not qualify.
- **Fix timeline:** critical vulnerabilities within 7 days, high severity within 14 days, moderate within 30 days.
- **Disclosure:** we will coordinate disclosure timing with you. We follow responsible disclosure practices and will credit reporters unless they prefer anonymity.

## Scope

The following are in scope:

- **Code execution vulnerabilities** in groundlens core, CLI, providers, or integrations
- **Dependency vulnerabilities** in direct dependencies (numpy, sentence-transformers) that affect groundlens users
- **Data leakage** through calibration files, cached embeddings, or provider wrappers
- **Deserialization attacks** via crafted calibration JSON files or CSV inputs
- **Path traversal** through CLI file arguments or calibration file paths

The following are out of scope:

- Vulnerabilities in third-party LLM provider APIs (OpenAI, Anthropic, Google) -- report these to the respective providers
- Accuracy of hallucination detection scores (this is a research concern, not a security concern)
- Denial of service through large input texts (sentence-transformers has its own input limits)

## Security practices

- **No secrets in code.** groundlens does not store or transmit API keys. Provider wrappers read keys from environment variables or user-provided configuration.
- **Dependency auditing.** We run `pip-audit` in CI against known vulnerability databases.
- **Type safety.** mypy strict mode is enforced across the codebase.
- **Input validation.** All public functions validate inputs before processing.
- **Minimal permissions.** groundlens requires no network access for core functionality. Network access is only needed when loading sentence-transformer models (first use) or when using LLM provider wrappers.
