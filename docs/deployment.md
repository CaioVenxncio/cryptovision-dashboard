# Deployment

## Status

CryptoVision **is being deployed to Streamlit Community Cloud in offline demo mode**. The deployment has **not yet been verified** as working; this page will be updated once it has. There is no container image and no other hosted instance. Local use, as described in [getting-started.md](getting-started.md), remains the reference setup.

## Streamlit Community Cloud (demo mode)

| Setting | Value |
|---|---|
| Repository and branch | `CaioVenxncio/cryptovision-dashboard`, `main` |
| Entrypoint | `app.py` |
| Python | 3.13 |
| Dependencies | `requirements.txt` (installs the pinned dependencies and the `cryptovision` package itself, via `-e .` from `requirements.in`) |
| Secrets | `CRYPTOVISION_DEMO = "1"` only. No API key is needed or should be added for the demo. |

How it behaves:

- Streamlit exposes the root-level secret as the `CRYPTOVISION_DEMO` environment variable, which turns on demo mode.
- On its first start, the app builds the synthetic demo dataset and demo research bundle in `.demo/`. This happens once per server process and takes under a minute, behind a spinner. After a restart the files may be gone, and they are built again.
- All three pages show synthetic data with visible "Demo mode — synthetic data" notices. No CoinGecko requests are made, and no Binance data or empirical research results are deployed.
- If the demo data cannot be built (for example, a read-only file system), the app shows an error. The Market Explorer demo keeps working; Historical Analytics and the Research Lab report that no data is available.

Checks still to do on the hosted app: the dependency installation on Linux, write access to `.demo/`, the first-start time, and that all three pages render.

## Before any other deployment

These points apply to deployments other than the demo described above, such as one serving live or local data.

1. **Historical CoinMarketCap key.** Already revoked by the owner (see [security.md](security.md)). It remains visible in Git history; no further action is needed for deployment.
2. **Data licensing.**
   - Binance Vision terms (§4.3) do not allow hosting the datasets. A deployment must not ship or serve `data/` or files derived from it beyond what the licence permits. Any derived output must carry Binance Vision attribution and the CC BY-NC-SA 4.0 notice, and must not be used commercially.
   - CoinGecko requires visible attribution and limits storage of its data. The persistent CoinGecko cache stays disabled.
   - Neither point has been reviewed by a lawyer; CryptoVision makes no compliance claim.
3. **API budget.** The CoinGecko Demo plan allows about 10,000 calls per month. The in-memory cache is per server process; several replicas or frequent restarts use more calls.
4. **Secrets.** Provide `COINGECKO_API_KEY` through the platform's secret store, never in the repository or the image. `.streamlit/secrets.toml` is git-ignored.
5. **Access control.** The app has no authentication. Add it in front of the app (reverse proxy or platform setting) if access should be limited.
6. **Demo-only option.** A public demo can run with `CRYPTOVISION_DEMO=1` and the synthetic `.demo/` data only. It then needs no API key and serves no provider data. In demo mode without explicit data directories, the app builds the synthetic demo data in `.demo/` on its first start (once per server process, under a minute); no manual step is needed. The host must install `requirements.txt`, which also installs the `cryptovision` package itself.
7. **Platform testing.** CI runs on Ubuntu and Windows with Python 3.12 and 3.13. Check that the latest workflow run on GitHub passed before deploying.

## Configuration reference

See the configuration table in the [README](../README.md#configuration) and [architecture.md](architecture.md#5-authentication-and-configuration).
