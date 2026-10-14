# CryptoVision 1.0.0rc1 — release notes

**Status: release candidate, local only.** No tag, GitHub release, package or deployment has been created. A final 1.0.0 needs the open items below to be closed.

## Highlights

- **Design system v1.0.** A consistent dark interface across the three pages, with tested WCAG AA text contrast, colorblind-safe chart palettes, text summaries and data tables for every chart, and a visible keyboard focus ring. See [design-system.md](design-system.md).
- **Offline demo.** `cryptovision-demo` runs the whole app on clearly labelled synthetic data, with no API key and no network access.
- **Honest research presentation.** The Research Lab states first that the v1 validation gate failed and the results are descriptive only. Bootstrap intervals are hidden by default and labelled as unvalidated diagnostics.
- **Historical credential mitigated.** The old CoinMarketCap key in commit `ca9f2df` has been revoked by the owner and is invalid. It remains visible in the public Git history, which is not rewritten. See [security.md](security.md).
- **Hardening.** Download size limits, bundle path confinement, `pip-audit`, and GitHub Actions pinned to commit SHAs.
- **Documentation.** Getting started, documentation index, security, deployment, changelog and citation metadata.

See the [changelog](../CHANGELOG.md) for the full list.

## Research status

The v1 protocol (`research/protocols/volatility-correlation-v1.md`, frozen 2026-10-13T22:24:26Z) and its results were not changed in this release. Its pre-specified simulation gate failed for both estimands, so the study makes no inferential claim. The descriptive point estimates are in the locally generated report. Results are not distributed with the repository because they derive from CC BY-NC-SA 4.0 data.

## Verification performed for this candidate

All checks ran on Windows 10 with Python 3.13.14 on 2026-10-13.

| Check | Result |
|---|---|
| Test suite (`pytest --cov`) | 437 passed; branch coverage 97.3% (minimum 90%) |
| Ruff lint and format check | Passed |
| Dataset verification (`cryptovision-data verify --sources`) | 544 of 544 hashes match |
| Protocol lock (`cryptovision-research validate`) | Protocol intact |
| Result bundle verification | Experiment bundle 8 of 8 files; simulation bundle passed |
| `pip-audit` on `requirements-dev.txt` | No known vulnerabilities |
| actionlint | Passed |
| Clean install (new virtual environment, only the files staged for commit, no `.env`, no data) | `pip check` passed; 431 passed, 6 skipped (tests that need the real dataset); all three entry points work; version 1.0.0rc1; about 6 minutes |
| Browser check (Chrome, demo mode) | Three pages at 1552px and 390px width; keyboard focus ring visible |

### Measured timings (same machine, demo data, indicative only)

| Measurement | Time |
|---|---|
| Streamlit server start to health check | 1.9 s |
| `prepare_demo` on an empty directory | 18.9 s |
| `prepare_demo` when the data already exists | < 0.01 s |
| Market Explorer script run (median of 3, `AppTest`) | 0.36 s |
| Historical Analytics, including the initial app run (median of 3) | 1.02 s |
| Research Lab, including the initial app run (median of 3) | 0.51 s |

Script-run times exclude browser rendering and network time.

## Open items before a final 1.0.0

| Severity | Item | Owner |
|---|---|---|
| High | Outstanding validation step: the CI workflow (including the new dependency-audit job and pinned actions) has never run on GitHub. | Repository owner, after approving a push |
| Medium | Python 3.12 and Linux/macOS were not tested locally; only Python 3.13 on Windows. CI covers them once it runs. | CI |
| Medium | No screen-reader, high-contrast or cross-browser testing; no formal accessibility audit. | Maintainer |
| Low | Licensing notes summarize provider terms but were not reviewed by a lawyer. | Maintainer |

## Upgrade notes

- No configuration changes are required. New optional variables: `CRYPTOVISION_DEMO`, `CRYPTOVISION_DATA_DIR`, `CRYPTOVISION_RESULTS_DIR`.
- Existing datasets and result bundles remain valid.
- New result bundles record software version `1.0.0rc1`.
