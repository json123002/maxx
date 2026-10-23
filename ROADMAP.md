# Maintenance roadmap

These are proposed priorities, not completed features or delivery commitments.

## Reliability

- Expand regression coverage for exchange holidays, missing snapshots, and data-source fallback.
- Check candlestick confirmation timing and avoid using future observations as historical signals.
- Document repeatable local setup and validate it against a clean environment.

## Security

- Review session revocation, administrator permissions, and per-user data-source isolation.
- Review external endpoint configuration and credential handling.
- Validate remediation with focused regression tests and maintainer review.

## Community and releases

- Publish a tested, tagged release with installation instructions and release notes.
- Add screenshots from synthetic or sanitized demonstration data.
- Document reproducible bug reports and contribution entry points.
- Report adoption only from verifiable sources; do not infer users from stars.

## Proposed Codex/API workflow

Start with maintainer-triggered, read-only change summaries and test suggestions. Keep public issue and PR text untrusted, protect credentials, and require human review before code changes are merged. Measure usefulness through confirmed fixes, regression coverage, and maintenance time rather than unsupported adoption claims.
