# Security

This document describes CryptoVision's security measures and a historical credential exposure that has been mitigated. It is not the result of an external security audit.

## Reporting a vulnerability

Please report suspected vulnerabilities privately to the author (contact details in the [README](../README.md#author)), not in a public issue. Do not include working credentials in the report.

## Historical credential exposure (mitigated)

**Status: mitigated by revocation (confirmed by the repository owner on 2026-10-13).**

Commit `ca9f2df` in the public Git history contains a CoinMarketCap API key in `api.py` (line 10). The current code does not use CoinMarketCap.

- The repository owner has revoked the key and confirmed that it is invalid. The revocation was reported by the owner; it was not tested independently, because using the key to check it would itself be inappropriate.
- The revoked key **remains visible in the public Git history**. History is intentionally **not** rewritten: a rewrite would not remove copies that were already cloned or indexed, and revocation is what makes the exposed value harmless.
- Gitleaks still reports this finding when scanning the full history (see the README, "Pre-commit hooks and secret scanning"). It is expected and refers to the revoked key.

## Secrets

- The CoinGecko key is read from the environment or a local `.env` file. `.env` is git-ignored; `.env.example` contains no value.
- The key is held as a Pydantic `SecretStr`. It is sent only in the `x-cg-demo-api-key` request header and never appears in URLs, cache keys, `repr()` output, logs, error messages, manifests or result bundles.
- Configuration errors name the variable, never its value.
- The test suite forces `COINGECKO_API_KEY=""` so a developer's real key is never loaded, and all HTTP calls are mocked.
- The demo mode makes no CoinGecko requests and needs no key.
- Gitleaks runs as a pre-commit hook on staged changes. If it blocks a commit, remove the secret and rotate it if it was real; do not bypass the hook.

## Network and downloads

- The CoinGecko base URL must use HTTPS.
- Every request has a timeout (default 10 s, at most 60 s) and a bounded number of retries with exponential backoff. A `Retry-After` above 60 s fails immediately instead of blocking.
- Binance Vision archives are verified against the published SHA-256 checksum before use.
- Download size limits:
  - archives: 20 MB;
  - uncompressed archive content: 50 MB, checked from the ZIP directory before extraction (zip-bomb protection);
  - checksum files: 4 KB.
- Only `cryptovision-data collect --yes` and the live Market Explorer access the network.

## Local files

- Datasets are verified by hash before the analytics or research code loads them. Tampered datasets and bundles are refused with an error message.
- The Research Lab loads only hash-verified result bundles and rejects a bundle that references files outside the results directory (path traversal).
- Files are written atomically (temporary file, then rename).
- Dynamic text in custom HTML components is escaped.

## Supply chain

- Dependencies are pinned in `requirements.txt` and `requirements-dev.txt` (pip-tools). CI checks that the locks match `pyproject.toml`.
- `pip-audit` checks the pinned development dependencies, locally and in a CI job. On 2026-10-13 it reported no known vulnerabilities. This only covers vulnerabilities that are already published.
- GitHub Actions are pinned to full commit SHAs. The workflow token is read-only and checkout does not persist credentials. No secrets are configured in CI.
- Streamlit usage statistics are disabled in `.streamlit/config.toml`.

## Not covered

- No authentication or authorization: the app is meant to run locally for one user. Do not expose it on a public network without adding them (see [deployment.md](deployment.md)).
- No rate limiting per user beyond the shared cache and refresh cooldown.
- No penetration test, threat model review or external audit has been done.
