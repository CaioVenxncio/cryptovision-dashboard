# CryptoVision

**A reproducible cryptocurrency market analytics and research platform.**

CryptoVision is a Python and Streamlit application for exploring cryptocurrency market data. It is being developed in phases into a reproducible research platform for studying volatility and correlation among major cryptocurrencies.

> CryptoVision is an educational and academic research project. It is not a trading platform and does not provide investment advice.

## Status

| Module | Status |
|---|---|
| Market Explorer | Available |
| Historical data pipeline | Available (command line) |
| Quantitative Analytics | Planned (Phase 4) |
| Research Lab | Planned (Phase 5) |

Quantitative analytics and statistical research are **not available yet**. The dashboard shows current market data. The historical data pipeline builds validated research datasets, but no analysis is performed on them yet.

## Features

- **Market Explorer**: the top 5–50 assets by market capitalization, with price, 24h change, 24h volume and market cap.
- **Correctly scoped metrics**: totals are labelled as aggregates over the *selected assets only*, not the whole crypto market.
- **Numeric tables**: values stay numeric and sort by value. Formatting is applied only for display, and very small prices keep their significant digits.
- **Data freshness**: the provider's last-update time and the fetch time are shown in UTC, together with whether the data came from the cache.
- **CSV export**: an in-memory download of raw values at full precision, with currency, source and fetch-time columns.
- **Interactive charts**: market cap (linear or log scale) and 24h price change, built with Plotly.
- **Historical data pipeline** (`cryptovision-data` CLI):
  - Builds reproducible daily datasets from Binance Vision archives, each verified against its SHA-256 checksum.
  - Validates every dataset with explicit fatal/error/warning issues.
  - Stores Parquet files with a provenance manifest (sources, hashes, configuration, validation report).
  - Supports offline rebuilds and integrity verification.
- **API budget protection**:
  - Data is cached for 15 minutes by default.
  - Manual refresh is limited to once per 60 seconds.
  - After a failure, the app waits before contacting the provider again.
  - Changing the asset count never makes a request.

## Requirements

- Python **3.12** (primary) or **3.13**
- Windows, Linux or macOS
- A free [CoinGecko Demo API key](https://www.coingecko.com/en/api) for live data. Tests do not need one.

## Installation (Windows PowerShell)

```powershell
git clone https://github.com/CaioVenxncio/cryptovision-dashboard.git
cd cryptovision-dashboard

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -e . --no-deps
```

Troubleshooting:

- **Script blocked:** if PowerShell blocks the activation script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.
- **`WinError 206`** ("file name or extension is too long"): Streamlit contains deeply nested files. Clone into a short path such as `C:\dev\cryptovision`, or enable Windows long-path support.
- **Linux or macOS:** activate the environment with `source .venv/bin/activate`.

## Configuration

1. Copy the example file:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Edit `.env` and set `COINGECKO_API_KEY`.

`.env` is excluded by `.gitignore` and must never be committed.

| Variable | Default | Description |
|---|---|---|
| `COINGECKO_API_KEY` | none | CoinGecko Demo API key. Required for live data. |
| `CACHE_TTL_SECONDS` | `900` | How long fetched data is reused (60–86400). |
| `HTTP_TIMEOUT_SECONDS` | `10` | Per-request timeout (up to 60). |
| `HTTP_MAX_RETRIES` | `3` | Retries after timeouts, HTTP 429 or HTTP 5xx (0–5). |

The key is sent only in the `x-cg-demo-api-key` request header, never in URLs, logs or error messages.

## Running the application

```powershell
streamlit run app.py
```

Then open http://localhost:8501.

## Historical datasets

Datasets are defined by TOML files in `configs/datasets/` and stored under the git-ignored `data/` directory.

| Config | Provider | Retention |
|---|---|---|
| `binance-spot-1d-top10-20210103.toml` | Binance Vision, 9 USDT spot pairs, 2021–2025 | Archival research dataset |
| `coingecko-daily-365d.toml` | CoinGecko, last 365 days | Expires after 24 hours (CoinGecko terms) |

```powershell
$cfg = "configs\datasets\binance-spot-1d-top10-20210103.toml"
$ds  = "data\datasets\binance-spot-1d-top10-20210103\1.0.0"

cryptovision-data plan $cfg                      # offline: assets, period, request count
cryptovision-data collect $cfg                   # dry run, no requests
cryptovision-data collect $cfg --yes             # download, verify and build
cryptovision-data list
cryptovision-data show $ds --issues
cryptovision-data verify $ds --sources           # recompute every hash
cryptovision-data validate $ds
cryptovision-data collect $cfg --offline --force # rebuild from local archives only
cryptovision-data synthetic --days 90 --seed 42 --anomalies
cryptovision-data purge-expired                  # delete expired CoinGecko caches
```

- **Network access:** only `collect --yes` uses the network. Every other command, `collect --offline` and the test suite work offline.
- **Without the installed script:** run `python -m cryptovision.data` instead of `cryptovision-data`.
- **Data rights:** never commit or share files from `data/`; provider terms restrict redistribution.

Further reading:

- [Data sources and licensing](docs/data-sources.md)
- [Data methodology](docs/data-methodology.md)
- [Reproducibility](docs/reproducibility.md)
- [Limitations](docs/limitations.md)

## Development

### Tests and coverage

The tests need no API key and make no network requests; all HTTP calls are mocked.

```powershell
pytest                                     # run the test suite
pytest --cov                               # terminal coverage summary (minimum 90%)
pytest --cov --cov-report=html             # HTML report in htmlcov\index.html
pytest --cov --cov-report=xml              # coverage.xml, as produced in CI
```

### Linting and formatting

```powershell
ruff check .            # lint
ruff format .           # format
ruff format --check .   # verify formatting without changing files
```

### Pre-commit hooks and secret scanning

[pre-commit](https://pre-commit.com) runs these checks before every commit:

- [Gitleaks](https://github.com/gitleaks/gitleaks) scans staged changes for credentials.
- Ruff lints and checks formatting.
- [actionlint](https://github.com/rhysd/actionlint) validates the workflow files.
- Standard hooks detect private keys and large files.

```powershell
pre-commit install            # one-time: enable the hooks for this clone
pre-commit run --all-files    # run every hook manually
```

The first run downloads and builds the hook tools, which takes a few minutes.

If Gitleaks blocks a commit, do not bypass it. Remove the secret from the staged files and rotate the credential if it was real.

To scan the full Git history with the Gitleaks binary that pre-commit installed:

```powershell
$gitleaks = Get-ChildItem "$HOME\.cache\pre-commit" -Recurse -Filter gitleaks.exe | Select-Object -First 1
& $gitleaks.FullName git --redact .
```

This history scan reports one known finding: an old CoinMarketCap API key in commit `ca9f2df` (`api.py`). The code no longer uses it, but it remains in the public history. Rewriting history is intentionally avoided, so **only the repository owner can neutralize it, by revoking the key** in the CoinMarketCap dashboard.

### Dependencies

Dependency ranges live in `pyproject.toml`. Exact pins are generated with [pip-tools](https://pip-tools.readthedocs.io); shared options are set in the `[tool.pip-tools]` section.

```powershell
pip-compile -o requirements.txt pyproject.toml
pip-compile --extra dev -o requirements-dev.txt pyproject.toml
pip-sync requirements-dev.txt
pip install -e . --no-deps
```

Lock files are generated on Windows with Python 3.13. CI checks that they match `pyproject.toml`.

### Continuous integration

`.github/workflows/ci.yml` runs on pushes to `main`, on pull requests and on manual dispatch.

- **Matrix**: Ubuntu and Windows × Python 3.12 and 3.13.
- **Each job**:
  - installs the pinned dependencies
  - runs `pip check`, Ruff lint and Ruff format checks
  - runs pytest with coverage
  - uploads `coverage.xml`
- **Lock-file job**: confirms the lock files are up to date.

The workflow uses a read-only token and needs no secrets.

## Architecture

```
cryptovision-dashboard/
├── app.py                        # Thin Streamlit entry point
├── src/cryptovision/
│   ├── config.py                 # Validated settings from the environment
│   ├── models.py                 # Pydantic models with provenance
│   ├── market.py                 # Numeric DataFrames, aggregates, CSV export
│   ├── formatting.py             # Display-only formatting
│   ├── providers/                # HTTP client, CoinGecko client, errors
│   ├── data/                     # Historical datasets: config, sources, validation, storage, CLI
│   └── ui/                       # Data loading/cache, components, charts, theme
├── configs/datasets/             # Dataset definitions (TOML)
├── data/                         # Local datasets (git-ignored)
├── tests/                        # Offline test suite
├── docs/                         # Architecture, data sources, methodology, reproducibility, limitations
└── .github/workflows/ci.yml      # Continuous integration
```

See [docs/architecture.md](docs/architecture.md) for the data flow, caching, error handling, testing and security design.

## Data provider and limitations

Live market data is powered by [CoinGecko](https://www.coingecko.com/en/api) through the Demo API. Historical research datasets come from [Binance Vision](https://data.binance.vision) under CC BY-NC-SA 4.0 (see [data sources](docs/data-sources.md)).

- **Not real-time.** CoinGecko refreshes Demo data about every 60 seconds, and CryptoVision reuses fetched data for up to `CACHE_TTL_SECONDS`.
- **Request budget.** The Demo plan has a monthly call limit (10,000 calls at the time of writing). Each cache refresh uses one call.
- **Historical depth.** The Demo plan provides roughly one year of history, and CoinGecko's terms allow caching it for at most 24 hours. Multi-year research therefore uses Binance Vision, whose prices are exchange-specific and quoted in USDT, not USD.
- **Scope.** Only USD and the top 100 assets by market cap are fetched. Totals cover the selected assets only.
- **Cache scope.** The cache is held in memory per server process and is lost on restart.
- **Attribution.** CoinGecko requires attribution, which the app displays.

Check [CoinGecko's pricing page](https://www.coingecko.com/en/api/pricing) for current plan terms.

## Roadmap

1. Secure CoinGecko migration (complete)
2. Engineering foundation: CI, coverage, UI modularization, secret scanning (complete)
3. Historical data pipeline with provenance records (complete)
4. Quantitative analytics: returns, volatility, drawdown, correlation
5. Research Lab: reproducible volatility and correlation experiments
6. Multipage UI, offline demo mode and release

## License

Released under the [MIT License](LICENSE).

## Author

**Caio Venancio**

- LinkedIn: [Caio Venancio](https://www.linkedin.com/in/caio-venancio/)
- GitHub: [@CaioVenxncio](https://github.com/CaioVenxncio)
- Email: caiovenanciocommercial@gmail.com
