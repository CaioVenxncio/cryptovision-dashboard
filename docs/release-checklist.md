# Release checklist

Use this list for every release. Nothing on it publishes anything by itself; pushing, tagging, creating a GitHub release and deploying each need the owner's explicit decision.

## 1. Security

- [ ] `pre-commit run --all-files` passes (Gitleaks, Ruff, actionlint, standard hooks).
- [ ] `git status` shows no `.env`, `data/` files, `research/results/` or `.demo/` content staged.
- [ ] `pip-audit -r requirements-dev.txt --no-deps --disable-pip` reports no known vulnerabilities, or each finding is documented.
- [ ] Open items in [security.md](security.md) are reviewed. For 1.0.0rc1: the historical CoinMarketCap key is revoked (owner-confirmed) and remains visible in Git history.

## 2. Quality

- [ ] `pytest --cov` passes with at least 90% coverage.
- [ ] `ruff check .` and `ruff format --check .` pass.
- [ ] Lock files match `pyproject.toml` (`pip-compile` produces no diff).
- [ ] CI is green on Ubuntu and Windows, Python 3.12 and 3.13, including the dependency-audit and lock-file jobs.

## 3. Data and research integrity

- [ ] `cryptovision-data verify <dataset> --sources` passes for the archival dataset.
- [ ] `cryptovision-research validate configs/experiments/volatility-correlation-v1.toml` reports the protocol intact.
- [ ] `cryptovision-research verify <bundle>` passes for the published-in-docs bundles.
- [ ] Frozen protocols, locks and existing result bundles are unchanged (`git diff` on `research/protocols/` is empty).

## 4. Clean install

In a new, short directory (for example `C:\dev\cvtest`) with only the files tracked by Git:

- [ ] `pip install -r requirements-dev.txt` and `pip install -e . --no-deps` succeed; `pip check` passes.
- [ ] `pytest` passes.
- [ ] `cryptovision-demo --help`, `cryptovision-data --help` and `cryptovision-research --help` work.
- [ ] `cryptovision-demo` starts and all three pages render with the synthetic-data notice.

## 5. User interface

- [ ] All three pages render in demo mode without errors in the browser console.
- [ ] Layout works at desktop width and at about 390px.
- [ ] Keyboard focus is visible on controls.
- [ ] Synthetic-data and failed-gate notices are visible where they apply.
- [ ] README screenshots match the current UI and show synthetic data only.

## 6. Documentation and metadata

- [ ] Version is the same in `pyproject.toml`, `src/cryptovision/__init__.py`, `CITATION.cff` and `CHANGELOG.md`.
- [ ] `CHANGELOG.md` and release notes describe the release, including open items.
- [ ] README makes no claim that was not verified (no CI badge before CI has run, no compliance claim).

## 7. Publication (owner decision only)

- [ ] Push to GitHub.
- [ ] Tag and GitHub release.
- [ ] Any deployment, after the review in [deployment.md](deployment.md).

## Record for 1.0.0rc1 (2026-10-13)

| Section | Status |
|---|---|
| 1. Security | Done locally. Historical CoinMarketCap key revoked (confirmed by the owner); still visible in Git history |
| 2. Quality | Done locally (Windows, Python 3.13). **Outstanding: the first GitHub Actions run** (Ubuntu and Windows, Python 3.12 and 3.13, dependency audit, lock files) |
| 3. Data and research integrity | Done |
| 4. Clean install | Done on Windows, Python 3.13 |
| 5. User interface | Done in Chrome; console errors seen came from a browser extension, not the app |
| 6. Documentation | Done |
| 7. Publication | **Not done**, by decision: nothing pushed, tagged, released or deployed |
