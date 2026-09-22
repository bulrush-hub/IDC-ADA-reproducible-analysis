"""Prepare JSON payload for the artifact-tool results workbook."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "work" / "modeling_artifacts"


def records(path: Path, limit: int | None = None) -> list[dict]:
    frame = pd.read_csv(path)
    if limit is not None:
        frame = frame.head(limit)
    frame = frame.replace({np.nan: None})
    return frame.to_dict(orient="records")


results = json.loads((ARTIFACTS / "modeling_results.json").read_text(encoding="utf-8"))

ridge = pd.read_csv(ARTIFACTS / "ridge_coefficients.csv").head(75)
ridge.insert(0, "model", "Ridge")
logistic = pd.read_csv(ARTIFACTS / "logistic_coefficients.csv").head(75)
logistic.insert(0, "model", "Logistic regression")
count = pd.read_csv(ARTIFACTS / "count_coefficients.csv").head(75)
count.insert(0, "model", "Binomial GLM")
coefficients = pd.concat([ridge, logistic, count], ignore_index=True).replace(
    {np.nan: None}
)

payload = {
    "results": results,
    "tables": {
        "Model_Performance": records(ARTIFACTS / "performance.csv"),
        "Feature_Importance": records(ARTIFACTS / "feature_importance.csv"),
        "Coefficients": coefficients.to_dict(orient="records"),
        "Sensitivity": records(ARTIFACTS / "sensitivity.csv"),
        "Data_Profile": records(ARTIFACTS / "profile.csv"),
        "Target_Summary": records(ARTIFACTS / "target_summary.csv"),
        "MOA_Summary": records(ARTIFACTS / "moa_summary.csv"),
        "Split_Audit": records(ARTIFACTS / "split_audit.csv"),
        "Test_Predictions": records(ARTIFACTS / "predictions.csv"),
    },
}

(ARTIFACTS / "workbook_payload.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(ARTIFACTS / "workbook_payload.json")
