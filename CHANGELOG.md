# Changelog

All notable changes to CryptoVision are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [PEP 440](https://peps.python.org/pep-0440/).

## [1.0.0rc1] - 2026-10-13

Release candidate. It is not a final release: the open items are listed in the [release notes](docs/release-notes-1.0.0rc1.md). Nothing has been published or deployed.

### Added

- Design system v1.0: color tokens with tested WCAG AA contrast, colorblind-safe chart palettes, a shared Plotly template, one CSS block, page-level components and a Streamlit theme (`.streamlit/config.toml`). See [docs/design-system.md](docs/design-system.md).
- Original CryptoVision logo and mark (`assets/`).
- Offline demo mode: `cryptovision-demo` builds synthetic data and a demo research bundle and starts the app without an API key. All demo values are labelled as synthetic.
- Accessible charts: each chart has a text summary and a data table.
- Release documentation: getting started, documentation index, security, deployment, release notes and checklist, `CITATION.cff`.
- `pip-audit` in the development dependencies and a `dependency-audit` CI job.
- Size limits on Binance Vision downloads (20 MB per archive, 50 MB uncompressed, 4 KB per checksum file).

### Changed

- Redesigned the Market Explorer, Historical Analytics and Research Lab pages: page headers with provenance, controls in the page body, tabs for charts, direction symbols next to colors.
- The Research Lab now states the failed validation gate at the top of the page, shows point estimates without intervals, and hides the bootstrap intervals behind a toggle labelled as unvalidated diagnostics.
- Generated research reports carry the Binance Vision attribution and CC BY-NC-SA 4.0 notice for real data, and label intervals as unvalidated when the gate failed. Existing result bundles were not changed.
- GitHub Actions pinned to full commit SHAs.
- Asset count in the Market Explorer is chosen from 10, 25 or 50.

### Security

- The Research Lab refuses result bundles that reference files outside the results directory.
- Documented the old CoinMarketCap API key in the public Git history (commit `ca9f2df`): revoked by the owner and invalid, but still visible in history, which is not rewritten. See [docs/security.md](docs/security.md).

## [0.5.0] - 2026-10-13

### Added

- Research Lab: a locally pre-specified study of return correlations in high- and low-volatility regimes, with a frozen, hash-locked protocol, strictly past regime classification, a stationary block bootstrap, a simulation-based validation gate, a robustness grid, immutable hash-verified result bundles, a generated report, the `cryptovision-research` CLI and a read-only dashboard page.
- The v1 validation gate failed, so the v1 results are descriptive only.

## [0.4.0] - 2026-10-13

### Added

- Quantitative analytics engine: simple and log returns, daily and annualized volatility, rolling windows, maximum drawdown with recovery dates, Pearson and Spearman correlation with sample counts, rolling correlation. Calendar-aware gap handling without filling.
- Historical Analytics page working offline on validated datasets.

## [0.3.0] - 2026-10-13

### Added

- Historical data pipeline (`cryptovision-data`): Binance Vision daily datasets verified by SHA-256 checksum, validation reports, Parquet storage with provenance manifests, offline rebuilds and integrity verification, deterministic synthetic data.

## [0.2.0] - 2026-10-13

Version 0.2.0 covers two commits: the CoinGecko migration and the engineering foundation.

### Added

- Continuous integration (Ubuntu and Windows, Python 3.12 and 3.13), coverage of at least 90%, pinned lock files, modular UI, pre-commit hooks with Gitleaks, Ruff and actionlint.

### Changed

- Migrated the Market Explorer from CoinMarketCap to the CoinGecko Demo API, with the key sent only in a request header, validated settings, caching and bounded retries.

Earlier history (before 2026-10-13) has no version entries.
