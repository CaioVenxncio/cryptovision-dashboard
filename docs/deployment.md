# Deployment

**CryptoVision is not deployed anywhere.** There is no hosted instance, no Streamlit Community Cloud app and no container image. The supported way to run it is locally, as described in [getting-started.md](getting-started.md).

This page lists what would have to be decided before a public deployment. None of it has been done.

## Before deploying

1. **Historical CoinMarketCap key.** Already revoked by the owner (see [security.md](security.md)). It remains visible in Git history; no further action is needed for deployment.
2. **Data licensing.**
   - Binance Vision terms (§4.3) do not allow hosting the datasets. A deployment must not ship or serve `data/` or files derived from it beyond what the licence permits. Any derived output must carry Binance Vision attribution and the CC BY-NC-SA 4.0 notice, and must not be used commercially.
   - CoinGecko requires visible attribution and limits storage of its data. The persistent CoinGecko cache stays disabled.
   - Neither point has been reviewed by a lawyer; CryptoVision makes no compliance claim.
3. **API budget.** The CoinGecko Demo plan allows about 10,000 calls per month. The in-memory cache is per server process; several replicas or frequent restarts use more calls.
4. **Secrets.** Provide `COINGECKO_API_KEY` through the platform's secret store, never in the repository or the image. `.streamlit/secrets.toml` is git-ignored.
5. **Access control.** The app has no authentication. Add it in front of the app (reverse proxy or platform setting) if access should be limited.
6. **Demo-only option.** A public demo can run with `CRYPTOVISION_DEMO=1` and the synthetic `.demo/` data only. It then needs no API key and serves no provider data. The demo data must be regenerated on the server with `cryptovision-demo --prepare-only`.
7. **Platform testing.** CI runs on Ubuntu and Windows with Python 3.12 and 3.13, but at the time of the 1.0.0rc1 release candidate the workflow had not yet run on GitHub. Run it before any deployment.

## Configuration reference

See the configuration table in the [README](../README.md#configuration) and [architecture.md](architecture.md#5-authentication-and-configuration).
