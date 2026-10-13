# data/

Local market data, caches and generated datasets. Everything in this directory
except this file is git-ignored.

- `raw/binance_vision/`: verified Binance Vision archives (CC BY-NC-SA 4.0).
- `datasets/<id>/<version>/`: archival research datasets.
- `cache/coingecko/<id>/`: CoinGecko caches. They expire 24 hours after retrieval
  (CoinGecko API terms §6.1.1) and are removed by `cryptovision-data purge-expired`.
- `synthetic/<id>/<version>/`: synthetic data. Not market observations.

Provider terms restrict redistribution. Do not commit, upload or share real market
data from this directory. See `docs/data-sources.md`.
