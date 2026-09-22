# IDC paper replication workflow

This directory is an independent, provenance-preserving replication workflow for Figure 6 and Supplementary Table S6 of the IDC publication. It does not modify or reuse the project's baseline or TabPFN result directories.

## What the workflow separates

- `published`: the eight values transcribed and mechanically checked against the user's preprint and the final Frontiers supplementary PDF.
- `proxy`: a runnable diagnostic reconstructed from public IDC workbooks. It uses deterministic text mappings and sequence length in place of the unavailable author-derived T-cell epitope count.
- `exact`: a strict path that only runs when author-derived row-level variables are supplied. It refuses to label proxy values as an exact replication.

The inferred sequential Type-I logistic-regression order and all category contracts are frozen in `config/replication_contract.json`. The published final residual degrees of freedom imply 1,216 complete cases and 17 fitted parameters.

## Directory map

- `config/`: immutable model contract and published Table S6 values.
- `data/raw/`: frozen user-provided original workbook, Frontiers supplements, and the author GitHub repository checkout.
- `data/processed/`: JSON extracted from source workbooks for portable Python execution.
- `data/manual/`: location for author-derived row-level variables; intentionally absent until supplied.
- `run_replication.py`: proxy and strict-exact analysis entry point.
- `build_workbook.mjs`: audited Excel result builder using the Codex spreadsheet runtime.
- `../outputs/paper_replication/`: report, work log, figure, workbook, previews, and machine-readable artifacts.

## Project-local Python environment only

Never install these packages into system Python. On Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r paper_replication\requirements.lock.txt
.\.venv\Scripts\python.exe paper_replication\run_replication.py --mode proxy
```

On Linux:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r paper_replication/requirements.lock.txt
./.venv/bin/python paper_replication/run_replication.py --mode proxy
```

The current run reused the existing project `.venv`; it did not install or change global packages. Once the processed JSON files are copied, the Python analysis has no dependency on Excel or the Codex spreadsheet runtime.

## Strict replication input

Use `outputs/paper_replication/artifacts/manual_review_template.csv` as the starting point. Replace proxy-only values with the author's derived values, retain `replication_row_key`, set `review_status`, `mapping_source`, and `reviewer`, then save the completed file as:

`paper_replication/data/manual/paper_derived_variables.csv`

Run:

```powershell
.\.venv\Scripts\python.exe paper_replication\run_replication.py --mode exact
```

The command validates the unique key, required fields, allowed levels, numeric fields, and the paper-inferred complete-case count of 1,216 before fitting the model. `--allow-sample-mismatch` is diagnostic only and must not be used to claim exact replication.

## Key audit outputs

- `source_manifest.csv`: paths, SHA-256 hashes, and source roles.
- `source_workbook_value_comparison.csv`: every-sheet value comparison of the user original, author GitHub, and Frontiers copies.
- `sample_funnel.csv`: public-row selection and complete-case counts.
- `duplicate_idc_row_identifiers.csv`: repeated public source IDs retained for explicit review.
- `table_s6_comparison.csv`: published versus proxy values with guardrail labels.
- `order_sensitivity_summary.csv` and `order_sensitivity_runs.csv`: deterministic first/last term-entry diagnostics for Type-I deviance.
- `drop_one_lrt.csv`: order-independent conditional likelihood-ratio contribution on the fixed proxy cohort.
- `proxy_missingness.csv` and `outcome_balance.csv`: complete-case selection diagnostics.
- `robustness_comparison.csv`: compact published/sequential-proxy/conditional-proxy comparison.
- `replication_metadata.json`: environment, frozen commit, run mode, and status.
- `IDC_paper_replication_results.xlsx`: human-readable audit workbook.

The proxy result is a reproducibility diagnostic, not evidence that the publication is wrong. Exact numerical agreement requires the unreleased epitope-prediction outputs, author category mappings, and exact row-selection/design matrix.

## Independent deduplication scenarios

`run_dedup_scenarios.py` creates two additional sensitivity-analysis datasets without changing `outputs/paper_replication/`:

- `one_row_per_molecule.csv`: one deterministic representative source row for each normalized molecule INN.
- `one_row_per_molecule_disease_category.csv`: one deterministic representative source row for each normalized molecule INN and raw `Disease Indication Category` combination.

Representative rows are ranked by audited/model-complete status, distance from the within-group ADA-frequency median, ADA patient count, and source Excel row. Run only through the project virtual environment:

```powershell
.\.venv\Scripts\python.exe paper_replication\run_dedup_scenarios.py
```

All new data, model comparisons, robustness results, selection audits, figures, logs, and the audited workbook are written to `outputs/paper_replication_dedup_scenarios/`.

## Leakage-controlled grouped prediction evaluation

`run_grouped_nested_cv.py` compares the public-row reference and both deduplicated datasets using repeated nested cross-validation. Both outer validation and inner L2 tuning are grouped by normalized molecule INN, so a molecule never appears in training and validation simultaneously. Numeric scaling and categorical encoding are fitted inside each training fold.

```powershell
.\.venv\Scripts\python.exe paper_replication\run_grouped_nested_cv.py
```

The workflow reports row-weighted and molecule-balanced ROC-AUC, average precision, balanced accuracy, Brier score, log loss, calibration bins, molecule-cluster bootstrap intervals, and outer-test permutation importance. Outputs are isolated under `outputs/paper_replication_grouped_cv/`; existing replication and deduplication results are not modified.
