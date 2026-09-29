r"""Generate development-only OOF predictions for IDC model validation.

Run with the project-local TabPFN environment:

    .\.venv-tabpfn\Scripts\python.exe outputs\IDC_oof_validation.py

Two validation schemes are evaluated separately:

1. ``study``: GroupKFold by model_split_group; estimates performance for new
   studies while molecules may have appeared in other studies.
2. ``molecule``: GroupKFold by molecule_inn_name; estimates transfer to unseen
   molecules while another molecule from the same multi-arm study may appear in
   training. The fold audit quantifies this remaining study overlap.

Only train+validation rows are used. The sealed test outcomes are not selected,
scored, calibrated, thresholded, or otherwise accessed after filtering.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "4")

import numpy as np
import pandas as pd
import sklearn
import tabpfn
import torch
from dotenv import load_dotenv
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from tabpfn import TabPFNClassifier, TabPFNRegressor

from feature_layers import (
    PRIMARY_BINARY_FEATURES as BINARY_FEATURES,
    PRIMARY_CATEGORICAL_FEATURES as CATEGORICAL_FEATURES,
    PRIMARY_NUMERIC_FEATURES as NUMERIC_FEATURES,
)


SEED = 20260802
N_SPLITS = 5
N_ESTIMATORS = 8
EXPECTED_TABPFN_VERSION = "8.2.0"

# The release stores scripts in code/modeling; repository data and outputs are
# located two directory levels above this file.
ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "outputs" / "IDC_modeling_table_final_model_ready.xlsx"
SPLIT = ROOT / "work" / "modeling_artifacts" / "split_audit.csv"
ARTIFACTS = ROOT / "work" / "validation_stage2"
MODEL_CACHE = ROOT / "work" / "tabpfn_model_cache"
ARTIFACTS.mkdir(parents=True, exist_ok=True)
MODEL_CACHE.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / ".env", override=False)
os.environ["TABPFN_MODEL_CACHE_DIR"] = str(MODEL_CACHE)
os.environ.setdefault("TABPFN_NO_BROWSER", "1")


FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES + BINARY_FEATURES
CATEGORICAL_INDICES = tuple(range(len(CATEGORICAL_FEATURES)))


def prepare_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in (
        "n_ada_assessed",
        "assessment_days",
        "dose_mg_extracted",
        "total_sequence_length",
    ):
        values = pd.to_numeric(result[column], errors="coerce").clip(lower=0)
        result[f"log_{column}"] = np.log1p(values)
    return result


def load_development_data() -> pd.DataFrame:
    frame = prepare_dataframe(pd.read_excel(INPUT, sheet_name="Modeling_Data"))
    split = pd.read_csv(SPLIT, dtype={"idc_row_id": "string"})
    merged = frame.merge(
        split[["idc_row_id", "partition"]],
        on="idc_row_id",
        how="left",
        validate="one_to_one",
    )
    if len(merged) != len(split) or merged["partition"].isna().any():
        raise ValueError("Modeling table does not align with split audit")
    development = merged.loc[
        merged["partition"].isin(["train", "validation"])
    ].copy()
    development.reset_index(drop=True, inplace=True)
    if len(development) != 2237:
        raise ValueError(f"Expected 2,237 development rows, found {len(development)}")
    if not development["ada_frequency_percent"].between(0, 100).all():
        raise ValueError("Development ADA frequency outside 0–100")
    derived = (development["ada_frequency_percent"] >= 10).astype(int)
    if not derived.equals(development["ada_high_10"].astype(int)):
        raise ValueError("Development binary outcome is inconsistent")
    return development


def tabpfn_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame[FEATURES].copy()
    for column in CATEGORICAL_FEATURES:
        result[column] = result[column].fillna("Missing").astype(str)
    for column in NUMERIC_FEATURES + BINARY_FEATURES:
        result[column] = pd.to_numeric(result[column], errors="coerce").astype(float)
    return result


def random_forest_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame[FEATURES].copy()
    for column in CATEGORICAL_FEATURES:
        result[column] = result[column].astype("object")
    for column in NUMERIC_FEATURES + BINARY_FEATURES:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def rf_preprocessor() -> ColumnTransformer:
    numeric = Pipeline(
        [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
    )
    categorical = Pipeline(
        [
            ("impute", SimpleImputer(strategy="constant", fill_value="Missing")),
            (
                "onehot",
                OneHotEncoder(
                    handle_unknown="infrequent_if_exist",
                    min_frequency=10,
                    sparse_output=False,
                ),
            ),
        ]
    )
    return ColumnTransformer(
        [("num", numeric, NUMERIC_FEATURES + BINARY_FEATURES), ("cat", categorical, CATEGORICAL_FEATURES)],
        remainder="drop",
        verbose_feature_names_out=True,
    )


def make_rf_regressor() -> Pipeline:
    return Pipeline(
        [
            ("preprocess", rf_preprocessor()),
            (
                "model",
                RandomForestRegressor(
                    n_estimators=300,
                    max_depth=14,
                    min_samples_leaf=5,
                    max_features=0.65,
                    n_jobs=-1,
                    random_state=SEED,
                ),
            ),
        ]
    )


def make_rf_classifier() -> Pipeline:
    return Pipeline(
        [
            ("preprocess", rf_preprocessor()),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=300,
                    max_depth=14,
                    min_samples_leaf=5,
                    max_features="sqrt",
                    class_weight="balanced_subsample",
                    n_jobs=-1,
                    random_state=SEED,
                ),
            ),
        ]
    )


def make_tabpfn_regressor() -> TabPFNRegressor:
    return TabPFNRegressor(
        n_estimators=N_ESTIMATORS,
        auto_scale_n_estimators=True,
        categorical_features_indices=CATEGORICAL_INDICES,
        device="auto",
        random_state=SEED,
        fit_mode="fit_preprocessors",
        show_progress_bar=False,
    )


def make_tabpfn_classifier() -> TabPFNClassifier:
    return TabPFNClassifier(
        n_estimators=N_ESTIMATORS,
        auto_scale_n_estimators=True,
        categorical_features_indices=CATEGORICAL_INDICES,
        device="auto",
        random_state=SEED,
        fit_mode="fit_preprocessors",
        show_progress_bar=False,
    )


def regression_metrics(actual: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    return {
        "MAE": float(mean_absolute_error(actual, prediction)),
        "RMSE": float(mean_squared_error(actual, prediction) ** 0.5),
        "R2": float(r2_score(actual, prediction)),
    }


def binary_metrics(actual: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    label = (probability >= 0.5).astype(int)
    clipped = np.clip(probability, 1e-15, 1 - 1e-15)
    return {
        "ROC_AUC": float(roc_auc_score(actual, probability)),
        "PR_AUC": float(average_precision_score(actual, probability)),
        "F1_0_5": float(f1_score(actual, label, zero_division=0)),
        "Balanced_Accuracy_0_5": float(balanced_accuracy_score(actual, label)),
        "Brier": float(brier_score_loss(actual, probability)),
        "Log_Loss": float(log_loss(actual, clipped, labels=[0, 1])),
    }


def run_scheme(development: pd.DataFrame, scheme: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if scheme == "study":
        groups = development["model_split_group"].astype(str)
        excluded_dimension = "model_split_group"
        secondary_dimension = "molecule_inn_name"
    elif scheme == "molecule":
        groups = development["molecule_inn_name"].astype(str)
        excluded_dimension = "molecule_inn_name"
        secondary_dimension = "model_split_group"
    else:
        raise ValueError(f"Unknown scheme: {scheme}")

    X_tab = tabpfn_frame(development)
    X_rf = random_forest_frame(development)
    y_reg = development["ada_frequency_percent"].to_numpy(float)
    y_cls = development["ada_high_10"].to_numpy(int)
    splitter = GroupKFold(n_splits=N_SPLITS)

    output = development[
        [
            "idc_row_id",
            "model_split_group",
            "molecule_inn_name",
            "ada_frequency_percent",
            "ada_high_10",
            "n_ada_assessed",
            "assessment_days",
            "ada_assay_platform",
            "ada_assay_sensitivity_missing",
            "disease_category_clean",
            "route_clean",
            "labelled_as_biosimilar",
        ]
    ].copy()
    output.insert(0, "validation_scheme", scheme)
    output["fold"] = pd.Series(pd.NA, index=output.index, dtype="Int64")
    for column in ["rf_regression", "tabpfn_regression", "rf_probability", "tabpfn_probability"]:
        output[column] = np.nan

    fold_rows: list[dict[str, Any]] = []
    runtime_rows: list[dict[str, Any]] = []
    for fold, (train_index, valid_index) in enumerate(
        splitter.split(development, y_reg, groups), start=1
    ):
        train_primary = set(development.iloc[train_index][excluded_dimension].astype(str))
        valid_primary = set(development.iloc[valid_index][excluded_dimension].astype(str))
        train_secondary = set(development.iloc[train_index][secondary_dimension].astype(str))
        valid_secondary = set(development.iloc[valid_index][secondary_dimension].astype(str))
        primary_overlap = train_primary & valid_primary
        secondary_overlap = train_secondary & valid_secondary
        if primary_overlap:
            raise RuntimeError(f"{scheme} fold {fold} has primary group leakage")

        fold_audit = {
            "validation_scheme": scheme,
            "fold": fold,
            "train_rows": len(train_index),
            "validation_rows": len(valid_index),
            "primary_dimension": excluded_dimension,
            "train_primary_groups": len(train_primary),
            "validation_primary_groups": len(valid_primary),
            "primary_overlap": len(primary_overlap),
            "secondary_dimension": secondary_dimension,
            "secondary_overlap": len(secondary_overlap),
            "validation_prevalence": float(y_cls[valid_index].mean()),
        }
        output.loc[valid_index, "fold"] = fold

        models = [
            ("Random forest", "continuous", make_rf_regressor(), X_rf),
            ("TabPFN-3", "continuous", make_tabpfn_regressor(), X_tab),
            ("Random forest", "binary", make_rf_classifier(), X_rf),
            ("TabPFN-3", "binary", make_tabpfn_classifier(), X_tab),
        ]
        for model_name, outcome, estimator, feature_frame in models:
            started = time.perf_counter()
            target = y_reg if outcome == "continuous" else y_cls
            estimator.fit(feature_frame.iloc[train_index], target[train_index])
            fit_seconds = time.perf_counter() - started
            started = time.perf_counter()
            if outcome == "continuous":
                prediction = np.asarray(estimator.predict(feature_frame.iloc[valid_index]), dtype=float)
                metrics = regression_metrics(y_reg[valid_index], prediction)
                column = "rf_regression" if model_name == "Random forest" else "tabpfn_regression"
            else:
                prediction = np.asarray(
                    estimator.predict_proba(feature_frame.iloc[valid_index])[:, 1], dtype=float
                )
                metrics = binary_metrics(y_cls[valid_index], prediction)
                column = "rf_probability" if model_name == "Random forest" else "tabpfn_probability"
            predict_seconds = time.perf_counter() - started
            output.loc[valid_index, column] = prediction
            fold_rows.append(
                {
                    **fold_audit,
                    "model": model_name,
                    "outcome": outcome,
                    **metrics,
                }
            )
            runtime_rows.append(
                {
                    "validation_scheme": scheme,
                    "fold": fold,
                    "model": model_name,
                    "outcome": outcome,
                    "fit_seconds": fit_seconds,
                    "predict_seconds": predict_seconds,
                }
            )
            del estimator
            gc.collect()
        output.to_csv(ARTIFACTS / f"oof_{scheme}_predictions.partial.csv", index=False)
        print(
            json.dumps(
                {
                    "scheme": scheme,
                    "fold": fold,
                    "validation_rows": len(valid_index),
                    "secondary_overlap": len(secondary_overlap),
                }
            ),
            flush=True,
        )

    prediction_columns = ["rf_regression", "tabpfn_regression", "rf_probability", "tabpfn_probability"]
    if output["fold"].isna().any() or output[prediction_columns].isna().any().any():
        raise RuntimeError(f"{scheme} OOF predictions are incomplete")
    if not output["rf_probability"].between(0, 1).all() or not output["tabpfn_probability"].between(0, 1).all():
        raise RuntimeError(f"{scheme} probabilities outside 0–1")
    return output, pd.DataFrame(fold_rows), pd.DataFrame(runtime_rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--schemes",
        default="study,molecule",
        help="Comma-separated validation schemes: study,molecule",
    )
    arguments = parser.parse_args()
    schemes = [value.strip() for value in arguments.schemes.split(",") if value.strip()]
    invalid = sorted(set(schemes) - {"study", "molecule"})
    if invalid:
        raise ValueError(f"Invalid schemes: {invalid}")
    if tabpfn.__version__ != EXPECTED_TABPFN_VERSION:
        raise RuntimeError(
            f"Expected tabpfn {EXPECTED_TABPFN_VERSION}, found {tabpfn.__version__}"
        )

    development = load_development_data()
    all_predictions: list[pd.DataFrame] = []
    all_folds: list[pd.DataFrame] = []
    all_runtime: list[pd.DataFrame] = []
    started = time.perf_counter()
    for scheme in schemes:
        predictions, folds, runtime = run_scheme(development, scheme)
        predictions.to_csv(ARTIFACTS / f"oof_{scheme}_predictions.csv", index=False)
        folds.to_csv(ARTIFACTS / f"oof_{scheme}_fold_metrics.csv", index=False)
        runtime.to_csv(ARTIFACTS / f"oof_{scheme}_runtime.csv", index=False)
        all_predictions.append(predictions)
        all_folds.append(folds)
        all_runtime.append(runtime)
    combined_predictions = pd.concat(all_predictions, ignore_index=True)
    combined_folds = pd.concat(all_folds, ignore_index=True)
    combined_runtime = pd.concat(all_runtime, ignore_index=True)
    combined_predictions.to_csv(ARTIFACTS / "oof_predictions.csv", index=False)
    combined_folds.to_csv(ARTIFACTS / "oof_fold_metrics.csv", index=False)
    combined_runtime.to_csv(ARTIFACTS / "oof_runtime.csv", index=False)

    metadata = {
        "development_rows": int(len(development)),
        "schemes": schemes,
        "folds_per_scheme": N_SPLITS,
        "feature_count": len(FEATURES),
        "tabpfn_version": tabpfn.__version__,
        "tabpfn_estimators": N_ESTIMATORS,
        "torch_version": torch.__version__,
        "torch_cuda_available": bool(torch.cuda.is_available()),
        "sklearn_version": sklearn.__version__,
        "wall_seconds": time.perf_counter() - started,
        "sealed_test_outcome_used": False,
    }
    (ARTIFACTS / "oof_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2), flush=True)


if __name__ == "__main__":
    main()
