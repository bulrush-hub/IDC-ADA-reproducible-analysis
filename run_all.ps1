# Reproducible IDC workflow for Windows.
# Run from the repository root. Commands stop on the first failure so a partial
# result is never silently presented as a complete run.

$ErrorActionPreference = "Stop"

# 1. Create project-local environments. These commands never install packages
#    into the system/global Python environment.
if (-not (Test-Path -LiteralPath ".venv")) {
    py -3.12 -m venv .venv
}
.\.venv\Scripts\python.exe -m pip install -r requirements-modeling.lock.txt

if (-not (Test-Path -LiteralPath ".venv-tabpfn")) {
    py -3.12 -m venv .venv-tabpfn
}
.\.venv-tabpfn\Scripts\python.exe -m pip install -r requirements-tabpfn.lock.txt

# 2. The main modeling scripts retain the original project's outputs/... paths.
#    Prepare the expected input location without changing the frozen source.
New-Item -ItemType Directory -Force -Path "outputs" | Out-Null
Copy-Item -LiteralPath "data\cleaned\IDC_modeling_table_final_model_ready.xlsx" `
    -Destination "outputs\IDC_modeling_table_final_model_ready.xlsx" -Force

# 3. Baseline modeling. This freezes the research-group split and writes the
#    baseline artifacts used by later comparisons.
.\.venv\Scripts\python.exe code\modeling\IDC_modeling_pipeline.py

# 4. Public-data paper proxy, deduplication scenarios, and leakage-controlled
#    grouped nested CV. Exact replication needs author-derived row-level data.
.\.venv\Scripts\python.exe code\paper_replication\run_replication.py --mode proxy
.\.venv\Scripts\python.exe code\paper_replication\run_dedup_scenarios.py
.\.venv\Scripts\python.exe code\paper_replication\run_grouped_nested_cv.py

# 5. TabPFN steps require an accepted non-commercial license and a local .env.
if (Test-Path -LiteralPath ".env") {
    .\.venv-tabpfn\Scripts\python.exe code\modeling\IDC_TabPFN_pipeline.py
    .\.venv-tabpfn\Scripts\python.exe code\modeling\IDC_TabPFN_postprocess.py
    .\.venv-tabpfn\Scripts\python.exe code\modeling\IDC_validation_readiness.py
    .\.venv-tabpfn\Scripts\python.exe code\modeling\IDC_oof_validation.py --schemes study,molecule
    .\.venv-tabpfn\Scripts\python.exe code\modeling\IDC_oof_postprocess.py
} else {
    Write-Warning "Skipping TabPFN/OOF: create a local .env after accepting the TabPFN-3 license."
}

