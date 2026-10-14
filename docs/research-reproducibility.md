# Research Reproducibility

How to reproduce the Research Lab study from scratch on Windows PowerShell. Every command works offline except the dataset download in step 1.

## What is in the repository and what is not

| In Git | Not in Git (generated locally) |
|---|---|
| Protocol: `research/protocols/volatility-correlation-v1.md` | Binance archives and the Parquet dataset (`data/`), because provider terms restrict redistribution |
| Frozen hashes: `research/protocols/volatility-correlation-v1.lock.json` | Result bundles (`research/results/`), which contain statistics derived from the data |
| Configuration: `configs/experiments/volatility-correlation-v1.toml` | |
| Code and tests | |

No real market data is distributed with the repository.

## Steps

```powershell
# 0. Environment (see README: Installation)
.\.venv\Scripts\Activate.ps1

# 1. Obtain the permitted source data and rebuild the dataset (1,080 requests to
#    data.binance.vision; Binance Vision terms permit academic research, CC BY-NC-SA 4.0).
cryptovision-data collect configs\datasets\binance-spot-1d-top10-20210103.toml --yes

# 2. Verify the dataset. Its content hash must equal the one pinned in the experiment config:
#    d2da4d6e7087d49b72f9b3e18a67aa72870714f3ef8a7723d4fcab62ab9d8d4e
cryptovision-data verify data\datasets\binance-spot-1d-top10-20210103\1.0.0 --sources
cryptovision-data show data\datasets\binance-spot-1d-top10-20210103\1.0.0

# 3. Review the frozen protocol and confirm it is unchanged.
cryptovision-research validate configs\experiments\volatility-correlation-v1.toml
cryptovision-research plan configs\experiments\volatility-correlation-v1.toml

# 4. Synthetic method validation (simulation gate). About 30 minutes on a laptop.
cryptovision-research simulate configs\experiments\volatility-correlation-v1.toml --verbose

# 5. Run the frozen experiment (primary analysis, robustness grid, illustration).
cryptovision-research run configs\experiments\volatility-correlation-v1.toml

# 6. Verify and inspect the result bundle.
cryptovision-research list
cryptovision-research verify research\results\volatility-correlation\<bundle>
cryptovision-research report research\results\volatility-correlation\<bundle> --output report.md
```

The Research Lab page in the dashboard (`streamlit run app.py`) shows the same bundle offline.

### Default bundle in the Research Lab

Several verified bundles of the same study can exist locally (for example, runs made before the final simulation bundle). They share the protocol and dataset metadata, so the page does not choose by directory order or timestamps. Instead, the final Phase 5 result is pinned in `FINAL_BUNDLE` in `src/cryptovision/ui/research_view.py`:

- **Identifier:** `volatility-correlation/v1.0-81fd40d77fd5ad96` (relative to the results directory).
- **Checked before it is selected:** experiment id, protocol version and fingerprint, dataset hash, simulation bundle, the `results.json` hash recorded in the manifest, and a full integrity verification of every file.
- **When it passes:** it is selected by default and labelled "final result". Other valid bundles remain selectable.
- **When it is missing or fails a check** while other bundles of the same study exist: another bundle is selected, and a warning states that it is **not** the final result.
- **Other studies** (such as the offline demo) keep the first-listed bundle as the default, without a warning.

Changing the final result requires editing `FINAL_BUNDLE` in a reviewed commit.

## Guarantees

- **Frozen inputs.** `simulate` and `run` refuse to start if the protocol or configuration differs from the hashes in the lock file. Hashes are SHA-256 of the file bytes with CRLF normalized to LF, so Git line-ending conversion does not matter.
- **Pinned data.** `run` loads the dataset through the Phase 3 loader, which verifies file and content hashes. It also requires the dataset id, version and content hash pinned in the configuration.
- **Gate before inference.** `run` requires a full (non-quick) simulation bundle for the same frozen protocol and uses its pre-specified gate decision.
- **Determinism.** All randomness comes from `numpy.random.SeedSequence` streams derived from the configured seeds, in a fixed order, one stream per analysis and per simulated dataset.
- **Immutable bundles.**
  - Bundle identifiers are derived from their inputs: the protocol fingerprint, the dataset hash, the simulation bundle and the software version.
  - Re-running with the same inputs never overwrites anything. The new results are compared byte-for-byte with the existing bundle, and `run` reports `identical results` or lists the differences.
  - `verify` recomputes every file hash and checks the protocol files against the lock.

## What is byte-identical and what is not

| Expectation | Files |
|---|---|
| Byte-identical for identical inputs, platform and library versions | `results.json`, `regimes.csv`, `robustness.csv`, `report.md`, `config.toml` and `protocol.lock.json` in a bundle, plus `validation.json` in a simulation bundle. These files contain no timestamps; this was tested by re-running on the same machine. |
| Different on every run | `manifest.json` (creation time and environment) |
| Not tested | Bitwise identity across operating systems, CPU architectures or NumPy/pandas versions. Floating-point summation order can differ, so results should agree numerically (to about 1e-12) but not necessarily bit for bit. |

The bundle and the report record the environment (Python, NumPy, pandas, platform) and the Git commit with a dirty-tree flag.

## Changing the study

Frozen protocols are immutable. To change anything:

1. Write `research/protocols/<id>-v2.md` and `configs/experiments/<id>-v2.toml`, stating the reason and whether empirical results had been seen.
2. Freeze them in a new lock file with `cryptovision.research.protocol.freeze`.

Version 1 stays in the repository unchanged.
