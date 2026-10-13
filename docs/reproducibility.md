# Reproducibility

"Reproducible" can mean three different things. CryptoVision supports them to different degrees.

| Guarantee | Meaning | Supported? |
|---|---|---|
| **1. Archived-dataset reproducibility** | Re-running an analysis on the same stored dataset gives the same inputs. | Yes. `verify` recomputes every hash, and `load_dataset` refuses tampered files. |
| **2. Transformation reproducibility** | Rebuilding the dataset from the same raw provider files gives identical values. | Yes. `collect --offline` rebuilds from verified local archives, and identical values give an identical `content_sha256`. |
| **3. Re-acquisition reproducibility** | Someone else downloading the data later gets the same data. | Partly. Binance archives carry published checksums, so a matching SHA-256 proves byte-identical source files. Providers can still revise or remove files. CoinGecko history cannot be re-acquired identically and is never archived. |

Two independently downloaded datasets covering the same period are **not** assumed to be identical. Compare their `content_sha256` values and source-file hashes instead.

## Manifests

Each dataset directory contains a `manifest.json` that records:

- **Identity:** dataset id and version, kind, provider, `synthetic` flag, retention and expiry.
- **Source:** source description and endpoint or path template, attribution and license notes.
- **Universe:** assets, the selection rule and every exclusion.
- **Periods:** quote currency, frequency, requested period and actual period.
- **Timing:** creation time and retrieval start and finish times, all in UTC.
- **Source files:** for each downloaded file, its URL, local path, SHA-256, size, whether it was checksum-verified, retrieval time, and whether a local copy was reused.
- **Configuration:** its SHA-256 and the fully resolved configuration.
- **Stored files:** for each file, its SHA-256 and row count, plus `content_sha256`.
- **Validation:** the complete validation report (issues, coverage per asset, thresholds).
- **Software:** versions of CryptoVision, the schema, the transformation, Python, pandas and pyarrow.
- **Hash definitions:** a description of what each hash covers.

Manifests never contain API keys, request headers or signed URLs.

### What each hash covers

| Hash | Input | Use |
|---|---|---|
| `source_files[].sha256` | Bytes of each downloaded provider file | Proves which provider files were used. For Binance it also matches the provider's checksum. |
| `files.data.sha256`, `files.rejected.sha256` | Bytes of the stored Parquet files | Detects corruption or tampering of the local copy. Changes with the Parquet writer version. |
| `content_sha256` | Canonical CSV of the valid rows (sorted, fixed column order, floats as shortest round-trip `repr`, ISO 8601 UTC timestamps, nulls empty, LF) | Compares dataset *values* across machines and library versions. |
| `config.sha256` | Configuration file bytes with LF line endings | Identifies the exact configuration used. |

## Reproducing the research dataset

From the project root in PowerShell:

```powershell
# 1. Inspect the plan (offline).
cryptovision-data plan configs\datasets\binance-spot-1d-top10-20210103.toml

# 2. Download, verify and build. 1,080 requests to data.binance.vision, no API key.
cryptovision-data collect configs\datasets\binance-spot-1d-top10-20210103.toml --yes

# 3. Check every hash, including the raw archives.
cryptovision-data verify data\datasets\binance-spot-1d-top10-20210103\1.0.0 --sources

# 4. Rebuild from the local archives only and compare content_sha256.
cryptovision-data collect configs\datasets\binance-spot-1d-top10-20210103.toml --offline --force
cryptovision-data show data\datasets\binance-spot-1d-top10-20210103\1.0.0
```

To check that you obtained the same data as another researcher, compare `content_sha256` and the `source_files` hashes in your manifest with theirs.

## Offline use

- `plan`, `show`, `verify`, `validate`, `list`, `synthetic`, `purge-expired` and `collect --offline` never access the network.
- `collect` without `--yes` is a dry run.
- Importing modules, running tests or starting the dashboard never triggers data collection.
- Later analysis code should load data through `cryptovision.data.pipeline.load_dataset`. It works offline, verifies hashes, and refuses datasets that are expired or not research-ready.

## Versioning

| Version | Bump when |
|---|---|
| Dataset `version` (in the config) | The content or definition of a dataset changes. |
| `SCHEMA_VERSION` | Columns or their types change. |
| `TRANSFORMATION_VERSION` | Normalization or validation logic changes the stored output. |
| `MANIFEST_VERSION` | The manifest format changes. |
