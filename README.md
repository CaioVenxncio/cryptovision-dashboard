# CryptoVision

**A reproducible cryptocurrency market analytics and research platform.**

CryptoVision is a Python and Streamlit application for exploring cryptocurrency market data. It is being developed incrementally into a reproducible research platform for studying volatility and correlation among major cryptocurrencies.

> CryptoVision is an educational and academic research project. It is not a trading platform and does not provide investment advice.

## Status

| Module | Status |
|---|---|
| Market Explorer | Available |
| Quantitative Analytics | Planned |
| Research Lab | Planned |

## Features

- **Market Explorer**: the top 5–50 assets by market capitalization, with price, 24h change, 24h volume and market cap.
- **Correctly scoped metrics**: market cap and volume cards are labelled as aggregates over the *selected assets only*, not the whole crypto market.
- **Numeric tables**: values stay numeric, so columns sort by value. Formatting is applied only when displayed, and very small prices keep their significant digits.
- **Data freshness**: the app shows the provider's last-update time and the fetch time, both in UTC, and whether the data came from the cache.
- **CSV export**: an in-memory download of raw values at full precision, with source and fetch-time columns.
- **Interactive charts**: market cap (linear or log scale) and 24h price change, built with Plotly.
- **API budget protection**: responses are cached (15 minutes by default) and manual refresh is rate-limited. Changing the asset count never triggers a new request.

## Technology

- Python 3.12 (primary), 3.13 compatible
- Streamlit, Plotly, pandas
- Pydantic v2 for configuration and response validation
- requests with explicit timeouts and bounded retries
- pytest, responses, Ruff
- pip-tools for pinned dependencies

## Architecture

```
cryptovision-dashboard/
├── app.py                       # Streamlit entry point (Market Explorer)
├── src/cryptovision/
│   ├── config.py                # Environment settings, validated; API key masked
│   ├── models.py                # Typed models with provenance and UTC timestamps
│   ├── market.py                # Snapshot -> numeric DataFrame, summaries, CSV export
│   ├── formatting.py            # Display-only number and time formatting
│   └── providers/
│       ├── errors.py            # Provider exception hierarchy (safe messages)
│       ├── http_client.py       # Timeouts, bounded exponential backoff, Retry-After
│       └── coingecko.py         # CoinGecko /coins/markets and /simple/price client
├── tests/                       # Offline tests with mocked HTTP responses
├── pyproject.toml               # Project metadata, Ruff and pytest configuration
├── requirements.txt             # Pinned runtime dependencies (generated)
└── requirements-dev.txt         # Pinned development dependencies (generated)
```

## Installation (Windows PowerShell)

Prerequisite: Python 3.12 or 3.13.

```powershell
git clone https://github.com/CaioVenxncio/cryptovision-dashboard.git
cd cryptovision-dashboard

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -e . --no-deps
```

If PowerShell blocks the activation script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

On Linux or macOS, activate with `source .venv/bin/activate` instead.

## Configuration

1. Create a free CoinGecko Demo API key at [coingecko.com/en/api](https://www.coingecko.com/en/api).
2. Copy the example file:
   ```powershell
   Copy-Item .env.example .env
   ```
3. Edit `.env` and set `COINGECKO_API_KEY`. Never commit `.env`; it is excluded by `.gitignore`.

| Variable | Default | Description |
|---|---|---|
| `COINGECKO_API_KEY` | none | CoinGecko Demo API key. Required for live data. |
| `CACHE_TTL_SECONDS` | `900` | How long fetched data is reused (60–86400). |
| `HTTP_TIMEOUT_SECONDS` | `10` | Per-request timeout (up to 60). |
| `HTTP_MAX_RETRIES` | `3` | Retries after timeouts, HTTP 429 or HTTP 5xx (0–5). |

The key is sent only in the `x-cg-demo-api-key` request header, never in URLs or logs.

## Running

```powershell
streamlit run app.py
```

Then open http://localhost:8501.

## Testing and linting

The tests need no API key and make no network requests.

```powershell
pytest
ruff check .
ruff format --check .
```

## Data provider and limitations

Market data is provided by [CoinGecko](https://www.coingecko.com/en/api) through the Demo API (`https://api.coingecko.com/api/v3`).

- **Not real-time.** CoinGecko refreshes Demo endpoint data about every 60 seconds, and CryptoVision reuses fetched data for up to `CACHE_TTL_SECONDS`.
- **Request budget.** The Demo plan has a monthly call limit (10,000 calls at the time of writing). Each cache refresh uses one call.
- **Historical depth.** The Demo plan provides roughly one year of daily and hourly history, which constrains future research designs.
- **Scope of aggregates.** Totals are computed over the selected assets only and are not global market figures.
- **Attribution.** CoinGecko requires attribution, which the app displays.

Check [CoinGecko's pricing page](https://www.coingecko.com/en/api/pricing) for current plan terms.

## Updating dependencies

Edit the dependency ranges in `pyproject.toml`, then regenerate the pinned files:

```powershell
pip-compile --strip-extras --no-emit-index-url -o requirements.txt pyproject.toml
pip-compile --strip-extras --extra dev -o requirements-dev.txt pyproject.toml
pip-sync requirements-dev.txt
pip install -e . --no-deps
```

## Roadmap

1. Secure CoinGecko migration (complete)
2. Engineering foundation: CI, coverage, further refactoring
3. Historical data pipeline with provenance records
4. Quantitative analytics: returns, volatility, drawdown, correlation
5. Research Lab: reproducible volatility and correlation experiments
6. UI refinement, offline demo mode and release

## License

Released under the [MIT License](LICENSE).

## Author

**Caio Venancio**

- LinkedIn: [Caio Venancio](https://www.linkedin.com/in/caio-venancio/)
- GitHub: [@CaioVenxncio](https://github.com/CaioVenxncio)
- Email: caiovenanciocommercial@gmail.com
