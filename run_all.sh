#!/usr/bin/env bash
# Reproducible IDC workflow for Linux. Run from the repository root.
set -euo pipefail

# 1. Recreate local environments instead of copying Windows virtualenvs.
if [[ ! -d .venv ]]; then
  python3.12 -m venv .venv
fi
./.venv/bin/python -m pip install -r requirements-modeling.lock.txt

if [[ ! -d .venv-tabpfn ]]; then
  python3.12 -m venv .venv-tabpfn
fi
./.venv-tabpfn/bin/python -m pip install -r requirements-tabpfn.lock.txt

# 2. Restore the input path expected by the original baseline script.
mkdir -p outputs
cp data/cleaned/IDC_modeling_table_final_model_ready.xlsx \
  outputs/IDC_modeling_table_final_model_ready.xlsx

# 3. Baseline and public-data sensitivity workflows.
./.venv/bin/python code/modeling/IDC_modeling_pipeline.py
./.venv/bin/python code/paper_replication/run_replication.py --mode proxy
./.venv/bin/python code/paper_replication/run_dedup_scenarios.py
./.venv/bin/python code/paper_replication/run_grouped_nested_cv.py

# 4. License-gated TabPFN and OOF validation.
if [[ -f .env ]]; then
  ./.venv-tabpfn/bin/python code/modeling/IDC_TabPFN_pipeline.py
  ./.venv-tabpfn/bin/python code/modeling/IDC_TabPFN_postprocess.py
  ./.venv-tabpfn/bin/python code/modeling/IDC_validation_readiness.py
  ./.venv-tabpfn/bin/python code/modeling/IDC_oof_validation.py --schemes study,molecule
  ./.venv-tabpfn/bin/python code/modeling/IDC_oof_postprocess.py
else
  printf '%s\n' 'Skipping TabPFN/OOF: create a local .env after accepting the TabPFN-3 license.' >&2
fi

