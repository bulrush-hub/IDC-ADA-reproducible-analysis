"""Reproducible modeling workflow for the final IDC model-ready dataset.

Run with the project-local virtual environment only:

Windows:
    .\\.venv\\Scripts\\python.exe outputs\\IDC_modeling_pipeline.py

Linux:
    ./.venv/bin/python outputs/IDC_modeling_pipeline.py
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "4")

import joblib
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import shap
import sklearn
import statsmodels.api as sm
from scipy.stats import spearmanr
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    mean_absolute_error,
    r2_score,
    roc_auc_score,
    root_mean_squared_error,
)
from sklearn.model_selection import (
    GroupKFold,
    GroupShuffleSplit,
    StratifiedGroupKFold,
    cross_validate,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from feature_layers import (
    FEATURE_LAYER_BY_FEATURE,
    PRIMARY_BINARY_FEATURES,
    PRIMARY_CATEGORICAL_FEATURES,
    PRIMARY_NUMERIC_FEATURES,
    build_feature_layer_manifest,
)


SEED = 20260802
N_SPLITS = 5
INPUT_RELATIVE = Path("outputs/IDC_modeling_table_final_model_ready.xlsx")
MODEL_SHEET = "Modeling_Data"


# The missingness figure deliberately uses a curated source-field scope. It must
# not mix true model-input gaps with audit notes (blank when no issue exists),
# derived helper columns, or attributes that apply only to selected molecules.
MODEL_INPUT_MISSINGNESS_SPECS = [
    {
        "field": "ada_assay_sensitivity",
        "display_label": "ADA assay sensitivity",
        "indicator": "ada_assay_sensitivity_missing",
        "missing_when": 1,
        "linked_model_features": "ada_assay_sensitivity_missing",
        "missing_definition": "ada_assay_sensitivity_missing = 1",
    },
    {
        "field": "coadministered_drugs",
        "display_label": "Coadministration information",
        "indicator": "comedication_missing",
        "missing_when": 1,
        "linked_model_features": "has_coadministered_drugs; comedication_missing",
        "missing_definition": (
            "blank in source; cannot distinguish no co-medication from not reported"
        ),
        "include_in_figure": False,
        "field_role": "conditional/semantically ambiguous",
        "exclusion_reason": (
            "Blank may encode a no-co-medication comparison group rather than missing data"
        ),
    },
    {
        "field": "ada_assay_platform",
        "display_label": "ADA assay platform",
        "indicator": "ada_assay_missing",
        "missing_when": 1,
        "linked_model_features": "ada_assay_platform; ada_assay_missing",
        "missing_definition": "ada_assay_missing = 1 (Not reported)",
    },
    {
        "field": "sequence_derived_descriptors",
        "display_label": "Sequence-derived descriptors",
        "indicator": "sequence_available",
        "missing_when": 0,
        "linked_model_features": (
            "sequence_available; log_total_sequence_length; n_sequence_chains; "
            "n_unique_sequences; max_chain_length"
        ),
        "missing_definition": "sequence_available = 0",
    },
    {
        "field": "therapeutic_comparator",
        "display_label": "Therapeutic comparator",
        "linked_model_features": "therapeutic_comparator",
        "missing_definition": "null/blank; may be not applicable to single-arm studies",
        "include_in_figure": False,
        "field_role": "conditionally applicable study-design field",
        "exclusion_reason": "A comparator is not applicable to every study design",
    },
    {
        "field": "randomized_or_not",
        "display_label": "Randomization status",
        "linked_model_features": "randomized_or_not",
        "missing_definition": "null/blank",
    },
    {
        "field": "dose_mg_extracted",
        "display_label": "Extracted dose",
        "indicator": "dose_mg_missing",
        "missing_when": 1,
        "linked_model_features": "log_dose_mg_extracted; dose_mg_missing",
        "missing_definition": "dose_mg_missing = 1",
    },
    {
        "field": "sequence_verified",
        "display_label": "Sequence verification status",
        "linked_model_features": "sequence_verified",
        "missing_definition": "null/blank",
    },
    {
        "field": "trial_blinding",
        "display_label": "Trial blinding",
        "linked_model_features": "trial_blinding",
        "missing_definition": "null/blank",
    },
    {
        "field": "prospective_or_retrospective",
        "display_label": "Study direction",
        "linked_model_features": "prospective_or_retrospective",
        "missing_definition": "null/blank",
    },
    {
        "field": "disease_category_clean",
        "display_label": "Disease category",
        "missing_values": ["Unspecified"],
        "linked_model_features": "disease_category_clean",
        "missing_definition": "null/blank or Unspecified",
    },
    {
        "field": "n_ada_assessed",
        "display_label": "ADA-assessed sample size",
        "linked_model_features": "log_n_ada_assessed",
        "missing_definition": "null/blank",
    },
    {
        "field": "assessment_days",
        "display_label": "Assessment duration",
        "linked_model_features": "log_assessment_days",
        "missing_definition": "null/blank",
    },
    {
        "field": "route_clean",
        "display_label": "Administration route",
        "linked_model_features": "route_clean",
        "missing_definition": "null/blank",
    },
    {
        "field": "protein_modality",
        "display_label": "Protein modality",
        "linked_model_features": "protein_modality",
        "missing_definition": "null/blank",
    },
    {
        "field": "species",
        "display_label": "Species/origin",
        "linked_model_features": "species",
        "missing_definition": "null/blank",
    },
    {
        "field": "antibody_backbone_clean",
        "display_label": "Antibody backbone",
        "linked_model_features": "antibody_backbone_clean",
        "missing_definition": "null/blank",
    },
    {
        "field": "light_chain_clean",
        "display_label": "Light-chain type",
        "linked_model_features": "light_chain_clean",
        "missing_definition": "null/blank",
    },
    {
        "field": "conjugate_modification_clean",
        "display_label": "Conjugation/modification class",
        "linked_model_features": "conjugate_modification_clean",
        "missing_definition": "null/blank",
    },
    {
        "field": "target_group",
        "display_label": "Target group",
        "linked_model_features": "target_group",
        "missing_definition": "null/blank",
    },
    {
        "field": "moa_group",
        "display_label": "MOA group",
        "linked_model_features": "moa_group",
        "missing_definition": "null/blank",
    },
    {
        "field": "labelled_as_biosimilar",
        "display_label": "Biosimilar label",
        "linked_model_features": "labelled_as_biosimilar",
        "missing_definition": "null/blank",
    },
]


FEATURE_DISPLAY_LABELS = {
    "disease_category_clean": "Disease category",
    "route_clean": "Administration route",
    "protein_modality": "Protein modality",
    "species": "Species/origin",
    "antibody_backbone_clean": "Antibody backbone",
    "light_chain_clean": "Light-chain type",
    "conjugate_modification_clean": "Conjugation/modification class",
    "target_group": "Target group",
    "moa_group": "MOA group",
    "ada_assay_platform": "ADA assay platform",
    "prospective_or_retrospective": "Study direction",
    "randomized_or_not": "Randomization status",
    "trial_blinding": "Trial blinding",
    "therapeutic_comparator": "Therapeutic comparator",
    "labelled_as_biosimilar": "Biosimilar label",
    "sequence_verified": "Sequence verification status",
    "has_coadministered_drugs": "Coadministration recorded",
    "comedication_missing": "Coadministration missing indicator",
    "dose_mg_missing": "Dose missing indicator",
    "sequence_available": "Sequence available",
    "ada_assay_missing": "ADA assay missing indicator",
    "ada_assay_sensitivity_missing": "Assay sensitivity missing indicator",
    "log_n_ada_assessed": "ADA-assessed sample size (log1p)",
    "log_assessment_days": "Assessment duration (log1p)",
    "log_dose_mg_extracted": "Dose in mg (log1p)",
    "log_total_sequence_length": "Total sequence length (log1p)",
    "n_sequence_chains": "Number of sequence chains",
    "n_unique_sequences": "Number of unique sequences",
    "max_chain_length": "Maximum chain length",
}


@dataclass
class ProjectPaths:
    root: Path
    input_xlsx: Path
    outputs: Path
    figures: Path
    models: Path
    work_artifacts: Path


def locate_project_root() -> Path:
    # Prefer the current working directory, then the portable release root.
    candidates = [Path.cwd(), Path(__file__).resolve().parents[2]]
    for candidate in candidates:
        if (candidate / INPUT_RELATIVE).exists():
            return candidate.resolve()
    raise FileNotFoundError(
        "Could not locate outputs/IDC_modeling_table_final_model_ready.xlsx"
    )


def make_paths(root: Path) -> ProjectPaths:
    outputs = root / "outputs"
    figures = outputs / "modeling_figures"
    models = outputs / "models"
    work_artifacts = root / "work" / "modeling_artifacts"
    for directory in (outputs, figures, models, work_artifacts):
        directory.mkdir(parents=True, exist_ok=True)
    return ProjectPaths(
        root=root,
        input_xlsx=root / INPUT_RELATIVE,
        outputs=outputs,
        figures=figures,
        models=models,
        work_artifacts=work_artifacts,
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for column in [
        "n_ada_assessed",
        "assessment_days",
        "dose_mg_extracted",
        "total_sequence_length",
    ]:
        values = pd.to_numeric(df[column], errors="coerce").clip(lower=0)
        df[f"log_{column}"] = np.log1p(values)
    return df


def validate_input(df: pd.DataFrame) -> dict[str, Any]:
    required = {
        "idc_row_id",
        "model_split_group",
        "molecule_inn_name",
        "ada_frequency_percent",
        "ada_high_10",
        "binomial_count_model_eligible",
        "ada_count_rate_percent",
        "n_ada_assessed",
    }
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    if df["idc_row_id"].duplicated().any():
        raise ValueError("idc_row_id is not unique")
    if not df["ada_frequency_percent"].between(0, 100).all():
        raise ValueError("ada_frequency_percent has values outside 0-100")
    derived_binary = (df["ada_frequency_percent"] >= 10).astype(int)
    if not derived_binary.equals(df["ada_high_10"].astype(int)):
        raise ValueError("ada_high_10 does not agree with the 10% threshold")
    return {
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "unique_idc_row_id": int(df["idc_row_id"].nunique()),
        "unique_model_split_groups": int(df["model_split_group"].nunique()),
        "high_ada_rows": int(df["ada_high_10"].sum()),
        "high_ada_prevalence": float(df["ada_high_10"].mean()),
        "count_model_eligible_rows": int(df["binomial_count_model_eligible"].sum()),
        "count_mismatch_rows": int(
            df["ada_count_consistency_status"].eq("REVIEW_COUNT_MISMATCH").sum()
        ),
        "dependency_flag_rows": int(df["record_dependency_note"].notna().sum()),
    }


def create_group_partitions(df: pd.DataFrame) -> tuple[pd.Series, dict[str, Any]]:
    groups = df["model_split_group"].astype(str)
    strata = pd.cut(
        df["ada_frequency_percent"],
        bins=[-0.001, 0, 1, 5, 10, 25, 50, 100],
        labels=False,
        include_lowest=True,
    )
    splitter = StratifiedGroupKFold(
        n_splits=7,
        shuffle=True,
        random_state=SEED,
    )
    dev_idx, test_idx = next(splitter.split(df, strata, groups))

    dev = df.iloc[dev_idx]
    dev_groups = groups.iloc[dev_idx]
    dev_strata = strata.iloc[dev_idx]
    splitter_dev = StratifiedGroupKFold(
        n_splits=6,
        shuffle=True,
        random_state=SEED + 1,
    )
    train_rel, val_rel = next(
        splitter_dev.split(dev, dev_strata, dev_groups)
    )

    partition = pd.Series("", index=df.index, dtype="string")
    partition.iloc[test_idx] = "test"
    partition.iloc[dev_idx[train_rel]] = "train"
    partition.iloc[dev_idx[val_rel]] = "validation"

    if partition.eq("").any():
        raise RuntimeError("Not all rows received a partition")

    group_sets = {
        name: set(groups[partition.eq(name)])
        for name in ["train", "validation", "test"]
    }
    if group_sets["train"] & group_sets["validation"]:
        raise RuntimeError("Train/validation group leakage detected")
    if group_sets["train"] & group_sets["test"]:
        raise RuntimeError("Train/test group leakage detected")
    if group_sets["validation"] & group_sets["test"]:
        raise RuntimeError("Validation/test group leakage detected")

    summary = {
        name: {
            "rows": int(partition.eq(name).sum()),
            "groups": int(groups[partition.eq(name)].nunique()),
            "high_ada_prevalence": float(
                df.loc[partition.eq(name), "ada_high_10"].mean()
            ),
            "ada_mean": float(
                df.loc[partition.eq(name), "ada_frequency_percent"].mean()
            ),
            "ada_median": float(
                df.loc[partition.eq(name), "ada_frequency_percent"].median()
            ),
        }
        for name in ["train", "validation", "test"]
    }
    return partition, summary


def build_feature_frame(
    df: pd.DataFrame, include_molecule: bool = False
) -> tuple[pd.DataFrame, list[str], list[str]]:
    categorical = list(PRIMARY_CATEGORICAL_FEATURES)
    if include_molecule:
        categorical.append("molecule_inn_name")
    numeric = list(PRIMARY_NUMERIC_FEATURES) + list(PRIMARY_BINARY_FEATURES)
    feature_columns = categorical + numeric
    X = df[feature_columns].copy()
    for column in categorical:
        X[column] = X[column].astype("object")
    for column in numeric:
        X[column] = pd.to_numeric(X[column], errors="coerce")
    return X, categorical, numeric


def build_preprocessor(
    categorical: list[str],
    numeric: list[str],
    *,
    min_frequency: int = 10,
    drop_first: bool = False,
) -> ColumnTransformer:
    numeric_pipe = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]
    )
    categorical_pipe = Pipeline(
        [
            (
                "impute",
                SimpleImputer(strategy="constant", fill_value="Missing"),
            ),
            (
                "onehot",
                OneHotEncoder(
                    handle_unknown="infrequent_if_exist",
                    min_frequency=min_frequency,
                    sparse_output=False,
                    drop="first" if drop_first else None,
                ),
            ),
        ]
    )
    return ColumnTransformer(
        [
            ("num", numeric_pipe, numeric),
            ("cat", categorical_pipe, categorical),
        ],
        remainder="drop",
        verbose_feature_names_out=True,
    )


def regression_candidates(categorical: list[str], numeric: list[str]) -> dict[str, Pipeline]:
    models = {
        "Dummy median": DummyRegressor(strategy="median"),
        "Ridge": Ridge(alpha=10.0),
        "Random forest": RandomForestRegressor(
            n_estimators=300,
            max_depth=14,
            min_samples_leaf=5,
            max_features=0.65,
            n_jobs=-1,
            random_state=SEED,
        ),
        "Histogram gradient boosting": HistGradientBoostingRegressor(
            max_iter=250,
            learning_rate=0.05,
            max_leaf_nodes=15,
            min_samples_leaf=20,
            l2_regularization=2.0,
            random_state=SEED,
        ),
    }
    return {
        name: Pipeline(
            [
                ("preprocess", build_preprocessor(categorical, numeric)),
                ("model", model),
            ]
        )
        for name, model in models.items()
    }


def classification_candidates(
    categorical: list[str], numeric: list[str]
) -> dict[str, Pipeline]:
    models = {
        "Dummy prior": DummyClassifier(strategy="prior"),
        "Logistic regression": LogisticRegression(
            C=0.2,
            class_weight="balanced",
            max_iter=3000,
            solver="lbfgs",
        ),
        "Random forest": RandomForestClassifier(
            n_estimators=300,
            max_depth=14,
            min_samples_leaf=5,
            max_features="sqrt",
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=SEED,
        ),
        "Histogram gradient boosting": HistGradientBoostingClassifier(
            max_iter=250,
            learning_rate=0.05,
            max_leaf_nodes=15,
            min_samples_leaf=20,
            l2_regularization=2.0,
            class_weight="balanced",
            random_state=SEED,
        ),
    }
    return {
        name: Pipeline(
            [
                ("preprocess", build_preprocessor(categorical, numeric)),
                ("model", model),
            ]
        )
        for name, model in models.items()
    }


def evaluate_regression(y_true: pd.Series, prediction: np.ndarray) -> dict[str, float]:
    return {
        "MAE": float(mean_absolute_error(y_true, prediction)),
        "RMSE": float(root_mean_squared_error(y_true, prediction)),
        "R2": float(r2_score(y_true, prediction)),
    }


def evaluate_classification(
    y_true: pd.Series, probability: np.ndarray, threshold: float = 0.5
) -> dict[str, float]:
    label = (probability >= threshold).astype(int)
    return {
        "ROC_AUC": float(roc_auc_score(y_true, probability)),
        "PR_AUC": float(average_precision_score(y_true, probability)),
        "F1": float(f1_score(y_true, label, zero_division=0)),
        "Balanced_Accuracy": float(balanced_accuracy_score(y_true, label)),
        "Brier": float(brier_score_loss(y_true, probability)),
        "Log_Loss": float(log_loss(y_true, probability, labels=[0, 1])),
    }


def cross_validate_models(
    candidates: dict[str, Pipeline],
    X: pd.DataFrame,
    y: pd.Series,
    groups: pd.Series,
    outcome: str,
) -> pd.DataFrame:
    cv = GroupKFold(n_splits=N_SPLITS)
    rows: list[dict[str, Any]] = []
    if outcome == "continuous":
        scoring = {
            "MAE": "neg_mean_absolute_error",
            "RMSE": "neg_root_mean_squared_error",
            "R2": "r2",
        }
    else:
        scoring = {
            "ROC_AUC": "roc_auc",
            "PR_AUC": "average_precision",
            "Brier": "neg_brier_score",
            "F1": "f1",
            "Balanced_Accuracy": "balanced_accuracy",
        }

    for name, estimator in candidates.items():
        result = cross_validate(
            estimator,
            X,
            y,
            groups=groups,
            cv=cv,
            scoring=scoring,
            n_jobs=1,
            error_score="raise",
        )
        row: dict[str, Any] = {"outcome": outcome, "model": name}
        for metric in scoring:
            values = np.asarray(result[f"test_{metric}"])
            if metric in {"MAE", "RMSE", "Brier"}:
                values = -values
            row[f"cv_{metric}_mean"] = float(values.mean())
            row[f"cv_{metric}_sd"] = float(values.std(ddof=1))
        row["cv_fit_time_mean_seconds"] = float(np.mean(result["fit_time"]))
        rows.append(row)
    return pd.DataFrame(rows)


def select_model(cv_table: pd.DataFrame, outcome: str) -> str:
    subset = cv_table[cv_table["outcome"].eq(outcome)].copy()
    if outcome == "continuous":
        return str(subset.sort_values("cv_MAE_mean").iloc[0]["model"])
    return str(subset.sort_values("cv_PR_AUC_mean", ascending=False).iloc[0]["model"])


def fit_and_test_candidates(
    candidates: dict[str, Pipeline],
    X_dev: pd.DataFrame,
    y_dev: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    outcome: str,
    selected_name: str,
) -> tuple[pd.DataFrame, dict[str, Pipeline], dict[str, np.ndarray]]:
    rows: list[dict[str, Any]] = []
    fitted: dict[str, Pipeline] = {}
    predictions: dict[str, np.ndarray] = {}
    for name, estimator in candidates.items():
        model = clone(estimator).fit(X_dev, y_dev)
        fitted[name] = model
        if outcome == "continuous":
            prediction = np.asarray(model.predict(X_test), dtype=float)
            metrics = evaluate_regression(y_test, prediction)
        else:
            prediction = np.asarray(model.predict_proba(X_test)[:, 1], dtype=float)
            metrics = evaluate_classification(y_test, prediction)
        predictions[name] = prediction
        rows.append(
            {
                "outcome": outcome,
                "model": name,
                "selected": name == selected_name,
                **{f"test_{key}": value for key, value in metrics.items()},
            }
        )
    return pd.DataFrame(rows), fitted, predictions


def permutation_table(
    fitted_model: Pipeline,
    X: pd.DataFrame,
    y: pd.Series,
    *,
    scoring: str,
    outcome: str,
    n_repeats: int = 12,
    random_state: int = SEED,
) -> pd.DataFrame:
    result = permutation_importance(
        fitted_model,
        X,
        y,
        scoring=scoring,
        n_repeats=n_repeats,
        random_state=random_state,
        n_jobs=-1,
    )
    table = pd.DataFrame(
        {
            "outcome": outcome,
            "method": "held-out permutation importance",
            "feature": X.columns,
            "importance_mean": result.importances_mean,
            "importance_sd": result.importances_std,
        }
    ).sort_values("importance_mean", ascending=False)
    table["rank"] = np.arange(1, len(table) + 1)
    return table.reset_index(drop=True)


def cv_permutation_stability(
    estimator: Pipeline,
    X: pd.DataFrame,
    y: pd.Series,
    groups: pd.Series,
    *,
    scoring: str,
    outcome: str,
) -> pd.DataFrame:
    fold_tables: list[pd.DataFrame] = []
    for fold, (train_idx, test_idx) in enumerate(
        GroupKFold(n_splits=N_SPLITS).split(X, y, groups), start=1
    ):
        fitted = clone(estimator).fit(X.iloc[train_idx], y.iloc[train_idx])
        table = permutation_table(
            fitted,
            X.iloc[test_idx],
            y.iloc[test_idx],
            scoring=scoring,
            outcome=outcome,
            n_repeats=5,
            random_state=SEED + fold,
        )
        table["fold"] = fold
        fold_tables.append(table)
    combined = pd.concat(fold_tables, ignore_index=True)
    stable = (
        combined.groupby(["outcome", "feature"], as_index=False)
        .agg(
            importance_mean=("importance_mean", "mean"),
            importance_sd_across_folds=("importance_mean", "std"),
            positive_fold_fraction=("importance_mean", lambda s: float((s > 0).mean())),
        )
        .sort_values("importance_mean", ascending=False)
    )
    stable["method"] = "5-fold grouped CV permutation importance"
    stable["rank"] = np.arange(1, len(stable) + 1)
    return stable.reset_index(drop=True)


def transformed_feature_to_raw(name: str, categorical: list[str]) -> str:
    if name.startswith("num__"):
        return name.removeprefix("num__")
    value = name.removeprefix("cat__")
    for feature in sorted(categorical, key=len, reverse=True):
        if value == feature or value.startswith(f"{feature}_"):
            return feature
    return value


def shap_importance(
    fitted_tree_pipeline: Pipeline,
    X: pd.DataFrame,
    categorical: list[str],
    *,
    outcome: str,
    max_rows: int = 300,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    sample = X.sample(min(max_rows, len(X)), random_state=SEED)
    preprocess = fitted_tree_pipeline.named_steps["preprocess"]
    tree = fitted_tree_pipeline.named_steps["model"]
    transformed = np.asarray(preprocess.transform(sample), dtype=float)
    transformed_names = np.asarray(preprocess.get_feature_names_out(), dtype=object)
    explainer = shap.TreeExplainer(tree)
    values = explainer.shap_values(transformed, check_additivity=False)
    if isinstance(values, list):
        values_array = np.asarray(values[1] if len(values) > 1 else values[0])
    else:
        values_array = np.asarray(values)
        if values_array.ndim == 3:
            values_array = values_array[:, :, 1]

    transformed_table = pd.DataFrame(
        {
            "outcome": outcome,
            "transformed_feature": transformed_names,
            "mean_abs_shap": np.abs(values_array).mean(axis=0),
        }
    ).sort_values("mean_abs_shap", ascending=False)
    transformed_table["raw_feature"] = transformed_table[
        "transformed_feature"
    ].map(lambda name: transformed_feature_to_raw(str(name), categorical))

    raw_table = (
        transformed_table.groupby(["outcome", "raw_feature"], as_index=False)[
            "mean_abs_shap"
        ]
        .sum()
        .sort_values("mean_abs_shap", ascending=False)
        .rename(columns={"raw_feature": "feature"})
    )
    raw_table["method"] = "Random-forest SHAP (aggregated to raw feature)"
    raw_table["rank"] = np.arange(1, len(raw_table) + 1)
    return raw_table.reset_index(drop=True), transformed_table.reset_index(drop=True)


def coefficient_table(
    fitted_pipeline: Pipeline,
    categorical: list[str],
    *,
    outcome: str,
) -> pd.DataFrame:
    names = fitted_pipeline.named_steps["preprocess"].get_feature_names_out()
    coef = np.asarray(fitted_pipeline.named_steps["model"].coef_)
    if coef.ndim == 2:
        coef = coef[0]
    table = pd.DataFrame(
        {
            "outcome": outcome,
            "transformed_feature": names,
            "coefficient": coef,
        }
    )
    table["absolute_coefficient"] = table["coefficient"].abs()
    table["raw_feature"] = table["transformed_feature"].map(
        lambda name: transformed_feature_to_raw(str(name), categorical)
    )
    table["interpretation_unit"] = (
        "percentage points per standardized/encoded feature"
        if outcome == "continuous"
        else "log-odds per standardized/encoded feature"
    )
    return table.sort_values("absolute_coefficient", ascending=False).reset_index(drop=True)


def fit_count_glm(
    df: pd.DataFrame,
    partition: pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    eligible = df["binomial_count_model_eligible"].astype(bool)
    dev_mask = partition.isin(["train", "validation"]) & eligible
    test_mask = partition.eq("test") & eligible
    X, categorical, numeric = build_feature_frame(df)
    preprocess = build_preprocessor(
        categorical,
        numeric,
        min_frequency=20,
        drop_first=True,
    )
    X_dev = np.asarray(preprocess.fit_transform(X.loc[dev_mask]), dtype=float)
    X_test = np.asarray(preprocess.transform(X.loc[test_mask]), dtype=float)
    X_dev = sm.add_constant(X_dev, prepend=True, has_constant="add")
    X_test = sm.add_constant(X_test, prepend=True, has_constant="add")
    y_dev = (
        pd.to_numeric(df.loc[dev_mask, "ada_count_rate_percent"], errors="raise")
        / 100.0
    ).to_numpy()
    y_test = (
        pd.to_numeric(df.loc[test_mask, "ada_count_rate_percent"], errors="raise")
        / 100.0
    ).to_numpy()
    weights_dev = pd.to_numeric(
        df.loc[dev_mask, "n_ada_assessed"], errors="raise"
    ).to_numpy()
    weights_test = pd.to_numeric(
        df.loc[test_mask, "n_ada_assessed"], errors="raise"
    ).to_numpy()

    model = sm.GLM(
        y_dev,
        X_dev,
        family=sm.families.Binomial(),
        freq_weights=weights_dev,
    )
    fit_method = "standard GLM fit"
    try:
        result = model.fit(maxiter=200, disp=0)
        if not bool(getattr(result, "converged", True)):
            raise RuntimeError("standard GLM did not converge")
        prediction = np.clip(result.predict(X_test), 1e-8, 1 - 1e-8)
        params = np.asarray(result.params)
        if not np.isfinite(params).all():
            raise RuntimeError("standard GLM returned non-finite coefficients")
        pvalues = np.asarray(result.pvalues)
    except Exception as exc:  # pragma: no cover - fallback is data dependent
        warnings.warn(f"Standard binomial GLM failed ({exc}); using L2 regularization")
        result = model.fit_regularized(alpha=1e-4, L1_wt=0.0, maxiter=500)
        prediction = np.clip(result.predict(X_test), 1e-8, 1 - 1e-8)
        params = np.asarray(result.params)
        pvalues = np.full_like(params, np.nan, dtype=float)
        fit_method = "L2-regularized GLM fallback"

    null_probability = float(np.average(y_dev, weights=weights_dev))
    null_prediction = np.full_like(y_test, null_probability, dtype=float)

    def weighted_metrics(pred: np.ndarray) -> dict[str, float]:
        return {
            "weighted_MAE_pp": float(
                np.average(np.abs(y_test - pred) * 100, weights=weights_test)
            ),
            "weighted_Brier": float(
                np.average((y_test - pred) ** 2, weights=weights_test)
            ),
            "weighted_Log_Loss": float(
                np.average(
                    -(y_test * np.log(pred) + (1 - y_test) * np.log(1 - pred)),
                    weights=weights_test,
                )
            ),
        }

    performance = pd.DataFrame(
        [
            {
                "outcome": "binomial_count",
                "model": "Weighted null proportion",
                "selected": False,
                **{f"test_{k}": v for k, v in weighted_metrics(null_prediction).items()},
            },
            {
                "outcome": "binomial_count",
                "model": "Binomial GLM",
                "selected": True,
                **{f"test_{k}": v for k, v in weighted_metrics(prediction).items()},
            },
        ]
    )

    feature_names = np.concatenate(
        [["intercept"], preprocess.get_feature_names_out().astype(object)]
    )
    coefficients = pd.DataFrame(
        {
            "outcome": "binomial_count",
            "transformed_feature": feature_names,
            "coefficient": params,
            "p_value": pvalues,
        }
    )
    coefficients["absolute_coefficient"] = coefficients["coefficient"].abs()
    coefficients = coefficients.sort_values(
        "absolute_coefficient", ascending=False
    ).reset_index(drop=True)
    metadata = {
        "fit_method": fit_method,
        "development_rows": int(dev_mask.sum()),
        "test_rows": int(test_mask.sum()),
        "development_total_assessed": int(weights_dev.sum()),
        "test_total_assessed": int(weights_test.sum()),
        "transformed_feature_count": int(X_dev.shape[1] - 1),
    }
    return performance, coefficients, metadata


def sensitivity_analysis(
    df: pd.DataFrame,
    partition: pd.Series,
    selected_reg_name: str,
    selected_cls_name: str,
    primary_reg_importance: pd.DataFrame,
    primary_cls_importance: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    X, categorical, numeric = build_feature_frame(df)
    reg_template = regression_candidates(categorical, numeric)[selected_reg_name]
    cls_template = classification_candidates(categorical, numeric)[selected_cls_name]

    scenarios = {
        "Exclude count-frequency mismatch": ~df[
            "ada_count_consistency_status"
        ].eq("REVIEW_COUNT_MISMATCH"),
        "Exclude dependency-flagged rows": df["record_dependency_note"].isna(),
    }
    for scenario, keep in scenarios.items():
        dev = partition.isin(["train", "validation"]) & keep
        test = partition.eq("test") & keep
        reg = clone(reg_template).fit(X.loc[dev], df.loc[dev, "ada_frequency_percent"])
        reg_prediction = reg.predict(X.loc[test])
        rows.append(
            {
                "scenario": scenario,
                "outcome": "continuous",
                "model": selected_reg_name,
                "development_rows": int(dev.sum()),
                "test_rows": int(test.sum()),
                **evaluate_regression(
                    df.loc[test, "ada_frequency_percent"], reg_prediction
                ),
            }
        )
        reg_imp = permutation_table(
            reg,
            X.loc[test],
            df.loc[test, "ada_frequency_percent"],
            scoring="neg_mean_absolute_error",
            outcome="continuous",
            n_repeats=5,
            random_state=SEED + 100,
        )
        rank_compare = primary_reg_importance[["feature", "rank"]].merge(
            reg_imp[["feature", "rank"]], on="feature", suffixes=("_primary", "_scenario")
        )
        rows[-1]["importance_rank_spearman"] = float(
            spearmanr(
                rank_compare["rank_primary"], rank_compare["rank_scenario"]
            ).statistic
        )

        cls = clone(cls_template).fit(X.loc[dev], df.loc[dev, "ada_high_10"])
        cls_probability = cls.predict_proba(X.loc[test])[:, 1]
        rows.append(
            {
                "scenario": scenario,
                "outcome": "binary",
                "model": selected_cls_name,
                "development_rows": int(dev.sum()),
                "test_rows": int(test.sum()),
                **evaluate_classification(df.loc[test, "ada_high_10"], cls_probability),
            }
        )
        cls_imp = permutation_table(
            cls,
            X.loc[test],
            df.loc[test, "ada_high_10"],
            scoring="average_precision",
            outcome="binary",
            n_repeats=5,
            random_state=SEED + 200,
        )
        rank_compare = primary_cls_importance[["feature", "rank"]].merge(
            cls_imp[["feature", "rank"]], on="feature", suffixes=("_primary", "_scenario")
        )
        rows[-1]["importance_rank_spearman"] = float(
            spearmanr(
                rank_compare["rank_primary"], rank_compare["rank_scenario"]
            ).statistic
        )

    X_identity, categorical_identity, numeric_identity = build_feature_frame(
        df, include_molecule=True
    )
    dev = partition.isin(["train", "validation"])
    test = partition.eq("test")
    reg_identity = regression_candidates(categorical_identity, numeric_identity)[
        selected_reg_name
    ].fit(X_identity.loc[dev], df.loc[dev, "ada_frequency_percent"])
    rows.append(
        {
            "scenario": "Add molecule identity",
            "outcome": "continuous",
            "model": selected_reg_name,
            "development_rows": int(dev.sum()),
            "test_rows": int(test.sum()),
            **evaluate_regression(
                df.loc[test, "ada_frequency_percent"],
                reg_identity.predict(X_identity.loc[test]),
            ),
        }
    )
    cls_identity = classification_candidates(categorical_identity, numeric_identity)[
        selected_cls_name
    ].fit(X_identity.loc[dev], df.loc[dev, "ada_high_10"])
    rows.append(
        {
            "scenario": "Add molecule identity",
            "outcome": "binary",
            "model": selected_cls_name,
            "development_rows": int(dev.sum()),
            "test_rows": int(test.sum()),
            **evaluate_classification(
                df.loc[test, "ada_high_10"],
                cls_identity.predict_proba(X_identity.loc[test])[:, 1],
            ),
        }
    )

    molecule_split = GroupShuffleSplit(
        n_splits=1, test_size=0.20, random_state=SEED + 300
    )
    molecule_train_idx, molecule_test_idx = next(
        molecule_split.split(df, groups=df["molecule_inn_name"])
    )
    reg_molecule = clone(reg_template).fit(
        X.iloc[molecule_train_idx],
        df.iloc[molecule_train_idx]["ada_frequency_percent"],
    )
    rows.append(
        {
            "scenario": "Unseen-molecule holdout",
            "outcome": "continuous",
            "model": selected_reg_name,
            "development_rows": int(len(molecule_train_idx)),
            "test_rows": int(len(molecule_test_idx)),
            "test_molecules": int(
                df.iloc[molecule_test_idx]["molecule_inn_name"].nunique()
            ),
            **evaluate_regression(
                df.iloc[molecule_test_idx]["ada_frequency_percent"],
                reg_molecule.predict(X.iloc[molecule_test_idx]),
            ),
        }
    )
    cls_molecule = clone(cls_template).fit(
        X.iloc[molecule_train_idx], df.iloc[molecule_train_idx]["ada_high_10"]
    )
    rows.append(
        {
            "scenario": "Unseen-molecule holdout",
            "outcome": "binary",
            "model": selected_cls_name,
            "development_rows": int(len(molecule_train_idx)),
            "test_rows": int(len(molecule_test_idx)),
            "test_molecules": int(
                df.iloc[molecule_test_idx]["molecule_inn_name"].nunique()
            ),
            **evaluate_classification(
                df.iloc[molecule_test_idx]["ada_high_10"],
                cls_molecule.predict_proba(X.iloc[molecule_test_idx])[:, 1],
            ),
        }
    )
    return pd.DataFrame(rows)


def build_profile(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "column": df.columns,
            "dtype": [str(value) for value in df.dtypes],
            "missing_n": df.isna().sum().to_numpy(),
            "missing_percent": (df.isna().mean() * 100).to_numpy(),
            "unique_n": df.nunique(dropna=True).to_numpy(),
        }
    ).sort_values(["missing_percent", "column"], ascending=[False, True])


def build_model_input_missingness(df: pd.DataFrame) -> pd.DataFrame:
    """Summarize effective missingness for source fields that feed the model.

    Existing missingness indicators are used where cleaning converted a raw
    null into an explicit category. This keeps the statistic aligned with the
    model contract without treating blank audit notes or non-applicable fields
    as data-quality failures.
    """
    rows: list[dict[str, Any]] = []
    for spec in MODEL_INPUT_MISSINGNESS_SPECS:
        if "indicator" in spec:
            indicator = pd.to_numeric(df[spec["indicator"]], errors="coerce")
            missing = indicator.eq(spec["missing_when"]) | indicator.isna()
        else:
            values = df[spec["field"]]
            text_values = values.astype("string").str.strip()
            missing = values.isna() | text_values.eq("").fillna(False)
            missing_values = {
                str(value).strip().casefold()
                for value in spec.get("missing_values", [])
            }
            if missing_values:
                missing |= text_values.str.casefold().isin(missing_values).fillna(False)

        missing_n = int(missing.sum())
        rows.append(
            {
                "field": spec["field"],
                "display_label": spec["display_label"],
                "linked_model_features": spec["linked_model_features"],
                "missing_definition": spec["missing_definition"],
                "field_role": spec.get("field_role", "core model source field"),
                "include_in_figure": bool(spec.get("include_in_figure", True)),
                "exclusion_reason": spec.get("exclusion_reason", ""),
                "missing_n": missing_n,
                "missing_percent": missing_n / len(df) * 100,
                "available_n": int(len(df) - missing_n),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["missing_percent", "field"], ascending=[False, True]
    ).reset_index(drop=True)


def build_group_summary(df: pd.DataFrame, group: str) -> pd.DataFrame:
    return (
        df.groupby(group, dropna=False)
        .agg(
            rows=("idc_row_id", "size"),
            molecules=("molecule_inn_name", "nunique"),
            ada_mean=("ada_frequency_percent", "mean"),
            ada_median=("ada_frequency_percent", "median"),
            ada_q25=("ada_frequency_percent", lambda s: s.quantile(0.25)),
            ada_q75=("ada_frequency_percent", lambda s: s.quantile(0.75)),
            high_ada_rate=("ada_high_10", "mean"),
        )
        .reset_index()
        .sort_values("rows", ascending=False)
    )


def save_eda_figures(
    df: pd.DataFrame,
    model_input_missingness: pd.DataFrame,
    target_summary: pd.DataFrame,
    moa_summary: pd.DataFrame,
    figures: Path,
) -> None:
    sns.set_theme(style="whitegrid", context="notebook")

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    sns.histplot(df["ada_frequency_percent"], bins=40, ax=axes[0], color="#1D4ED8")
    axes[0].axvline(10, color="#DC2626", linestyle="--", label="10% threshold")
    axes[0].set(title="ADA frequency distribution", xlabel="ADA frequency (%)")
    axes[0].legend()
    sns.histplot(np.log1p(df["ada_frequency_percent"]), bins=40, ax=axes[1], color="#0F766E")
    axes[1].set(title="log1p-transformed ADA frequency", xlabel="log1p(ADA frequency)")
    fig.tight_layout()
    fig.savefig(figures / "01_ada_distribution.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    top_missing = model_input_missingness[
        model_input_missingness["missing_percent"].gt(0)
        & model_input_missingness["include_in_figure"]
    ].head(20).sort_values("missing_percent")
    fig_height = max(5.2, 0.42 * len(top_missing) + 1.8)
    fig, ax = plt.subplots(figsize=(10, fig_height))
    bars = ax.barh(
        top_missing["display_label"],
        top_missing["missing_percent"],
        color="#D97706",
    )
    ax.bar_label(
        bars,
        labels=[f"{value:.1f}%" for value in top_missing["missing_percent"]],
        padding=4,
        fontsize=9,
    )
    ax.set_xlim(0, 100)
    ax.set(
        title="Missingness in core model-relevant source fields",
        xlabel="Missing or not reported (%)",
        ylabel="",
    )
    fig.text(
        0.01,
        0.01,
        (
            "Scope excludes audit/review notes, derived helper columns, and "
            "conditionally applicable or semantically ambiguous attributes."
        ),
        ha="left",
        fontsize=8.5,
        color="#4B5563",
    )
    fig.tight_layout(rect=(0, 0.055, 1, 1))
    fig.savefig(figures / "02_missingness.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    top_targets = target_summary.head(12).sort_values("ada_median")
    fig, ax = plt.subplots(figsize=(9.5, 6.5))
    bars = ax.barh(
        top_targets["target_group"], top_targets["ada_median"], color="#2563EB"
    )
    for bar, median, rows in zip(
        bars, top_targets["ada_median"], top_targets["rows"]
    ):
        inside = median >= 80
        ax.text(
            median - 1 if inside else median + 0.8,
            bar.get_y() + bar.get_height() / 2,
            f"{median:.1f}% (n={rows})",
            va="center",
            ha="right" if inside else "left",
            fontsize=8.5,
            color="white" if inside else "#1F2937",
        )
    ax.set_xlim(0, 100)
    ax.set(
        title="12 largest target groups: median ADA frequency",
        xlabel="Median ADA frequency (%)",
    )
    fig.text(
        0.01,
        0.01,
        "Groups are selected by record count; values are descriptive and unadjusted.",
        ha="left",
        fontsize=8.5,
        color="#4B5563",
    )
    fig.tight_layout(rect=(0, 0.055, 1, 1))
    fig.savefig(figures / "03_target_group_median_ada.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    top_moa = moa_summary.head(12).sort_values("high_ada_rate")
    fig, ax = plt.subplots(figsize=(9.5, 6.5))
    high_ada_percent = top_moa["high_ada_rate"] * 100
    bars = ax.barh(top_moa["moa_group"], high_ada_percent, color="#0F766E")
    for bar, rate, rows in zip(bars, high_ada_percent, top_moa["rows"]):
        inside = rate >= 80
        ax.text(
            rate - 1 if inside else rate + 0.8,
            bar.get_y() + bar.get_height() / 2,
            f"{rate:.1f}% (n={rows})",
            va="center",
            ha="right" if inside else "left",
            fontsize=8.5,
            color="white" if inside else "#1F2937",
        )
    ax.set_xlim(0, 100)
    ax.set(
        title="12 largest MOA groups: high-ADA rate",
        xlabel="Records with ADA ≥10% (%)",
    )
    fig.text(
        0.01,
        0.01,
        "Groups are selected by record count; values are descriptive and unadjusted.",
        ha="left",
        fontsize=8.5,
        color="#4B5563",
    )
    fig.tight_layout(rect=(0, 0.055, 1, 1))
    fig.savefig(figures / "04_moa_group_high_ada.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def save_importance_plot(
    table: pd.DataFrame,
    path: Path,
    title: str,
    value: str,
    xlabel: str,
) -> None:
    top = table.head(15).sort_values(value)
    fig, ax = plt.subplots(figsize=(9.5, 6.5))
    error = None
    if "importance_sd" in top.columns and top["importance_sd"].notna().any():
        error = top["importance_sd"].fillna(0)
    ax.barh(
        top["feature"].map(
            lambda feature: FEATURE_DISPLAY_LABELS.get(
                str(feature), str(feature).replace("_", " ")
            )
        ),
        top[value],
        xerr=error,
        capsize=2 if error is not None else 0,
        color="#7C3AED",
        error_kw={"elinewidth": 0.8, "ecolor": "#4B5563"},
    )
    ax.set(title=title, xlabel=xlabel, ylabel="")
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_reports(
    paths: ProjectPaths,
    metadata: dict[str, Any],
    validation: dict[str, Any],
    split_summary: dict[str, Any],
    continuous_selected: str,
    binary_selected: str,
    performance: pd.DataFrame,
    count_metadata: dict[str, Any],
    feature_importance: pd.DataFrame,
    model_input_missingness: pd.DataFrame,
    sensitivity: pd.DataFrame,
) -> None:
    timestamp = metadata["run_timestamp_utc"]
    cont_perf = performance[
        performance["outcome"].eq("continuous") & performance["selected"].eq(True)
    ].iloc[0]
    bin_perf = performance[
        performance["outcome"].eq("binary") & performance["selected"].eq(True)
    ].iloc[0]
    count_perf = performance[
        performance["outcome"].eq("binomial_count")
        & performance["selected"].eq(True)
    ].iloc[0]
    top_cont = feature_importance[
        feature_importance["outcome"].eq("continuous")
        & feature_importance["method"].eq("held-out permutation importance")
    ].head(10)
    top_bin = feature_importance[
        feature_importance["outcome"].eq("binary")
        & feature_importance["method"].eq("held-out permutation importance")
    ].head(10)
    top_missingness = model_input_missingness[
        model_input_missingness["missing_percent"].gt(0)
        & model_input_missingness["include_in_figure"]
    ].head(7)

    def importance_lines(table: pd.DataFrame) -> str:
        return "\n".join(
            f"- {row.feature}: {row.importance_mean:.4f}"
            for row in table.itertuples()
        )

    def missingness_lines(table: pd.DataFrame) -> str:
        return "\n".join(
            f"- {row.display_label}: {row.missing_n} 条（{row.missing_percent:.1f}%）"
            for row in table.itertuples()
        )

    log_text = f"""# IDC 建模工作日志

运行时间（UTC）：{timestamp}

## 步骤 1：冻结输入版本与环境

- 输入文件：`IDC_modeling_table_final_model_ready.xlsx`
- SHA-256：`{metadata['input_sha256']}`
- Python：{metadata['python_version']}
- 解释器：项目本地 `.venv`
- scikit-learn：{metadata['sklearn_version']}
- pandas：{metadata['pandas_version']}
- 随机种子：{SEED}

关键点：虚拟环境仅用于当前项目。迁移到 Linux 时重建 `.venv`，不复制 Windows 虚拟环境目录。

### 执行审计

- 首次完整运行在二项模型评价阶段停止：分类版 `log_loss` 不接受0到1之间的比例型结局。
- 修正：改用按 `n_ada_assessed` 加权的二项交叉熵公式。
- 该异常发生在结果评价阶段，没有修改输入数据或改变数据划分。
- 初始纯研究组随机划分使测试集ADA≥10%比例达到48.3%，高于全体33.0%。最终改为按ADA区间分层的研究组划分，使三部分结局分布更接近总体，同时保持研究组完全隔离。

## 步骤 2：输入质量复核与结局定义

- 建模记录：{validation['rows']}
- 唯一 `idc_row_id`：{validation['unique_idc_row_id']}
- 独立拆分组：{validation['unique_model_split_groups']}
- ADA≥10%：{validation['high_ada_rows']} 条（{validation['high_ada_prevalence']:.1%}）
- 二项计数模型可用：{validation['count_model_eligible_rows']} 条
- 计数与频率不一致：{validation['count_mismatch_rows']} 条
- 嵌套/纵向依赖提示：{validation['dependency_flag_rows']} 条

关键点：连续结局为 `ada_frequency_percent`；二分类结局为 `ada_high_10`；二项模型仅使用 `binomial_count_model_eligible=True`。

## 步骤 3：特征工程

- 主分析排除分子名称和研究标识符，降低药物记忆和来源泄漏。
- 使用靶点组、MOA组、药物结构、适应证、给药途径、试验设计和ADA检测平台。
- 样本量、观察时间、剂量和序列长度使用 `log1p` 变换。
- 数值缺失值使用训练集内部中位数填补；类别缺失值编码为 `Missing`。
- 低频类别由 OneHotEncoder 合并为低频水平。

关键点：所有填补、标准化和编码均位于模型 Pipeline 内，仅在训练折拟合，避免预处理泄漏。

## 步骤 4：按研究组划分数据

| 分区 | 行数 | 研究组 | ADA均值 | ADA中位数 | ADA≥10%比例 |
|---|---:|---:|---:|---:|---:|
| 训练 | {split_summary['train']['rows']} | {split_summary['train']['groups']} | {split_summary['train']['ada_mean']:.2f} | {split_summary['train']['ada_median']:.2f} | {split_summary['train']['high_ada_prevalence']:.1%} |
| 验证 | {split_summary['validation']['rows']} | {split_summary['validation']['groups']} | {split_summary['validation']['ada_mean']:.2f} | {split_summary['validation']['ada_median']:.2f} | {split_summary['validation']['high_ada_prevalence']:.1%} |
| 测试 | {split_summary['test']['rows']} | {split_summary['test']['groups']} | {split_summary['test']['ada_mean']:.2f} | {split_summary['test']['ada_median']:.2f} | {split_summary['test']['high_ada_prevalence']:.1%} |

关键点：先按ADA频率区间分层，再按 `model_split_group` 隔离；同一研究不会跨训练、验证和测试分区。模型选择使用开发集上的5折 GroupKFold，最终测试集不参与选择。

## 步骤 5：连续结局模型

- 选择模型：{continuous_selected}
- 测试集 MAE：{cont_perf['test_MAE']:.3f} 个百分点
- 测试集 RMSE：{cont_perf['test_RMSE']:.3f} 个百分点
- 测试集 R²：{cont_perf['test_R2']:.3f}

## 步骤 6：二分类模型

- 选择模型：{binary_selected}
- 测试集 ROC-AUC：{bin_perf['test_ROC_AUC']:.3f}
- 测试集 PR-AUC：{bin_perf['test_PR_AUC']:.3f}
- 测试集 F1：{bin_perf['test_F1']:.3f}
- 测试集平衡准确率：{bin_perf['test_Balanced_Accuracy']:.3f}
- 测试集 Brier：{bin_perf['test_Brier']:.3f}

## 步骤 7：二项计数模型

- 拟合方式：{count_metadata['fit_method']}
- 开发集：{count_metadata['development_rows']} 条，测试集：{count_metadata['test_rows']} 条
- 测试集加权 MAE：{count_perf['test_weighted_MAE_pp']:.3f} 个百分点
- 测试集加权 Brier：{count_perf['test_weighted_Brier']:.4f}
- 测试集加权 Log Loss：{count_perf['test_weighted_Log_Loss']:.4f}

关键点：该模型使用评估人数作为频数权重，且未把ADA阳性计数或频率派生字段作为预测特征。

## 步骤 8：Feature Importance

### 连续模型前10项（测试集 permutation importance）

{importance_lines(top_cont)}

### 二分类模型前10项（测试集 permutation importance）

{importance_lines(top_bin)}

同时输出：5折分组交叉验证稳定性、线性模型系数、随机森林SHAP聚合重要性。

关键点：Feature importance 表示预测贡献，不代表因果作用。高度相关的变量可能相互分摊重要性。

## 步骤 9：敏感性分析

- 排除95条计数/频率不一致记录后重新拟合并比较性能与重要性排名。
- 排除4条依赖提示记录后重新拟合。
- 加入分子名称，评估药物身份记忆带来的性能变化。
- 使用未见分子留出测试，检查对新分子的泛化能力。

详细结果见结果工作簿和 `modeling_sensitivity.csv`。

## 步骤 10：结论与使用限制

- 主结果应以按研究组隔离的测试集为准。
- 若未见分子留出性能明显下降，说明模型更适合已知药物体系内预测，不宜直接外推到全新分子。
- 二项计数模型仅适用于计数一致的记录。
- 结果属于观察性预测分析，不应解释为靶点、MOA或结构特征对ADA的因果效应。

## 步骤 11：图形统计口径与可读性复核

- 缺失审计覆盖22个建模相关源字段；主图仅展示可直接解释的核心源字段，审核/说明字段、派生辅助列和条件适用或语义不确定字段不进入该图。
- 全字段技术缺失审计仍保留在 `profile.csv`；详细建模输入缺失口径保存于 `model_input_missingness.csv`。
- `coadministered_drugs` 空值可能表示无合并用药或未报告，`therapeutic_comparator` 对单臂研究可能不适用；两者保留在审计表并记录排除原因。
- Target/MOA 图标注百分比与组内记录数；Feature Importance/SHAP 图使用可读标签，置换重要性显示重复置换标准差。
- 本步骤仅修正统计展示和解释口径，不修改输入数据、特征集合、数据拆分或模型算法。

主要建模信息缺口：

{missingness_lines(top_missingness)}
"""
    (paths.outputs / "IDC_modeling_work_log.md").write_text(log_text, encoding="utf-8")

    report_text = f"""# IDC ADA 建模结果摘要

本报告由 `IDC_modeling_pipeline.py` 使用项目 `.venv` 自动生成。

## 核心结果

| 任务 | 最佳模型 | 主要测试指标 |
|---|---|---|
| ADA频率连续预测 | {continuous_selected} | MAE {cont_perf['test_MAE']:.3f} pp；R² {cont_perf['test_R2']:.3f} |
| ADA≥10%二分类 | {binary_selected} | ROC-AUC {bin_perf['test_ROC_AUC']:.3f}；PR-AUC {bin_perf['test_PR_AUC']:.3f}；Brier {bin_perf['test_Brier']:.3f} |
| ADA阳性/评估人数二项模型 | Binomial GLM | 加权MAE {count_perf['test_weighted_MAE_pp']:.3f} pp；加权Brier {count_perf['test_weighted_Brier']:.4f} |

## 解释原则

Feature importance、SHAP和回归系数用于解释预测模型，不用于证明因果关系。主分析不使用分子名称；加入分子名称和未见分子留出结果作为模型泛化敏感性分析。

## 主要限制

- ADA检测方法、研究设计和报告标准在来源研究间存在异质性。
- 95条记录的阳性计数与报告频率不一致，未进入二项模型。
- 少数记录存在嵌套或纵向依赖，已通过分组拆分和敏感性分析控制。
- 测试集评估反映当前数据分布，不能替代外部独立验证。

完整数值、特征重要性和敏感性分析见 `IDC_modeling_results.xlsx`。
"""
    (paths.outputs / "IDC_modeling_report.md").write_text(report_text, encoding="utf-8")


def run_pipeline() -> dict[str, Any]:
    root = locate_project_root()
    paths = make_paths(root)
    run_timestamp = datetime.now(timezone.utc).isoformat()
    metadata = {
        "run_timestamp_utc": run_timestamp,
        "input_file": str(paths.input_xlsx.relative_to(paths.root)),
        "input_sha256": file_sha256(paths.input_xlsx),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "pandas_version": pd.__version__,
        "numpy_version": np.__version__,
        "sklearn_version": sklearn.__version__,
        "statsmodels_version": sm.__version__,
        "shap_version": shap.__version__,
        "seed": SEED,
        "group_cv_folds": N_SPLITS,
    }

    df = pd.read_excel(paths.input_xlsx, sheet_name=MODEL_SHEET)
    df = prepare_dataframe(df)
    validation = validate_input(df)
    profile = build_profile(df)
    model_input_missingness = build_model_input_missingness(df)
    target_summary = build_group_summary(df, "target_group")
    moa_summary = build_group_summary(df, "moa_group")
    save_eda_figures(
        df,
        model_input_missingness,
        target_summary,
        moa_summary,
        paths.figures,
    )

    partition, split_summary = create_group_partitions(df)
    split_audit = df[
        ["idc_row_id", "model_split_group", "molecule_inn_name", "ada_high_10"]
    ].copy()
    split_audit["partition"] = partition

    X, categorical, numeric = build_feature_frame(df)
    dev_mask = partition.isin(["train", "validation"])
    test_mask = partition.eq("test")
    X_dev, X_test = X.loc[dev_mask], X.loc[test_mask]
    groups_dev = df.loc[dev_mask, "model_split_group"].astype(str)
    y_reg_dev = df.loc[dev_mask, "ada_frequency_percent"]
    y_reg_test = df.loc[test_mask, "ada_frequency_percent"]
    y_cls_dev = df.loc[dev_mask, "ada_high_10"].astype(int)
    y_cls_test = df.loc[test_mask, "ada_high_10"].astype(int)

    reg_candidates = regression_candidates(categorical, numeric)
    cls_candidates = classification_candidates(categorical, numeric)
    cv_reg = cross_validate_models(
        reg_candidates, X_dev, y_reg_dev, groups_dev, "continuous"
    )
    cv_cls = cross_validate_models(
        cls_candidates, X_dev, y_cls_dev, groups_dev, "binary"
    )
    cv_table = pd.concat([cv_reg, cv_cls], ignore_index=True)
    selected_reg = select_model(cv_table, "continuous")
    selected_cls = select_model(cv_table, "binary")

    test_reg, fitted_reg, reg_predictions = fit_and_test_candidates(
        reg_candidates,
        X_dev,
        y_reg_dev,
        X_test,
        y_reg_test,
        "continuous",
        selected_reg,
    )
    test_cls, fitted_cls, cls_predictions = fit_and_test_candidates(
        cls_candidates,
        X_dev,
        y_cls_dev,
        X_test,
        y_cls_test,
        "binary",
        selected_cls,
    )
    candidate_performance = pd.concat([test_reg, test_cls], ignore_index=True)
    performance = cv_table.merge(
        candidate_performance,
        on=["outcome", "model"],
        how="outer",
    )

    reg_permutation = permutation_table(
        fitted_reg[selected_reg],
        X_test,
        y_reg_test,
        scoring="neg_mean_absolute_error",
        outcome="continuous",
    )
    cls_permutation = permutation_table(
        fitted_cls[selected_cls],
        X_test,
        y_cls_test,
        scoring="average_precision",
        outcome="binary",
    )
    reg_stability = cv_permutation_stability(
        reg_candidates[selected_reg],
        X_dev,
        y_reg_dev,
        groups_dev,
        scoring="neg_mean_absolute_error",
        outcome="continuous",
    )
    cls_stability = cv_permutation_stability(
        cls_candidates[selected_cls],
        X_dev,
        y_cls_dev,
        groups_dev,
        scoring="average_precision",
        outcome="binary",
    )

    reg_shap, reg_shap_transformed = shap_importance(
        fitted_reg["Random forest"],
        X_test,
        categorical,
        outcome="continuous",
    )
    cls_shap, cls_shap_transformed = shap_importance(
        fitted_cls["Random forest"],
        X_test,
        categorical,
        outcome="binary",
    )
    ridge_coefficients = coefficient_table(
        fitted_reg["Ridge"], categorical, outcome="continuous"
    )
    logistic_coefficients = coefficient_table(
        fitted_cls["Logistic regression"], categorical, outcome="binary"
    )

    feature_importance = pd.concat(
        [reg_permutation, cls_permutation, reg_stability, cls_stability, reg_shap, cls_shap],
        ignore_index=True,
        sort=False,
    )
    # Keep scientific interpretation separate from algorithmic importance:
    # each predictor is labelled as molecular, clinical, or measurement.
    feature_importance["feature_layer"] = feature_importance["feature"].map(
        FEATURE_LAYER_BY_FEATURE
    )
    feature_layer_manifest = pd.DataFrame(build_feature_layer_manifest())

    count_performance, count_coefficients, count_metadata = fit_count_glm(
        df, partition
    )
    for table in (
        ridge_coefficients,
        logistic_coefficients,
        reg_shap_transformed,
        cls_shap_transformed,
    ):
        table["feature_layer"] = table["raw_feature"].map(
            FEATURE_LAYER_BY_FEATURE
        )
    count_coefficients["raw_feature"] = count_coefficients[
        "transformed_feature"
    ].map(
        lambda name: (
            "intercept"
            if str(name) == "intercept"
            else transformed_feature_to_raw(str(name), categorical)
        )
    )
    count_coefficients["feature_layer"] = count_coefficients["raw_feature"].map(
        FEATURE_LAYER_BY_FEATURE
    )
    performance = pd.concat([performance, count_performance], ignore_index=True, sort=False)

    sensitivity = sensitivity_analysis(
        df,
        partition,
        selected_reg,
        selected_cls,
        reg_permutation,
        cls_permutation,
    )

    predictions = pd.DataFrame(
        {
            "idc_row_id": df.loc[test_mask, "idc_row_id"].to_numpy(),
            "model_split_group": df.loc[test_mask, "model_split_group"].to_numpy(),
            "molecule_inn_name": df.loc[test_mask, "molecule_inn_name"].to_numpy(),
            "ada_frequency_percent_actual": y_reg_test.to_numpy(),
            "ada_frequency_percent_predicted": reg_predictions[selected_reg],
            "ada_high_10_actual": y_cls_test.to_numpy(),
            "ada_high_10_probability": cls_predictions[selected_cls],
        }
    )

    joblib.dump(
        fitted_reg[selected_reg], paths.models / "continuous_best_pipeline.joblib"
    )
    joblib.dump(
        fitted_cls[selected_cls], paths.models / "binary_best_pipeline.joblib"
    )

    save_importance_plot(
        reg_permutation,
        paths.figures / "05_continuous_permutation_importance.png",
        "Continuous model: held-out permutation importance",
        "importance_mean",
        "Increase in MAE after permutation (ADA percentage points)",
    )
    save_importance_plot(
        cls_permutation,
        paths.figures / "06_binary_permutation_importance.png",
        "Binary model: held-out permutation importance",
        "importance_mean",
        "Decrease in average precision after permutation",
    )
    save_importance_plot(
        reg_shap,
        paths.figures / "07_continuous_shap_importance.png",
        "Continuous random forest: aggregated SHAP importance",
        "mean_abs_shap",
        "Mean |SHAP value| (ADA percentage points)",
    )
    save_importance_plot(
        cls_shap,
        paths.figures / "08_binary_shap_importance.png",
        "Binary random forest: aggregated SHAP importance",
        "mean_abs_shap",
        "Mean |SHAP value| (model-output scale)",
    )

    tables = {
        "profile": profile,
        "model_input_missingness": model_input_missingness,
        "target_summary": target_summary,
        "moa_summary": moa_summary,
        "split_audit": split_audit,
        "performance": performance,
        "feature_layer_manifest": feature_layer_manifest,
        "feature_importance": feature_importance,
        "ridge_coefficients": ridge_coefficients,
        "logistic_coefficients": logistic_coefficients,
        "count_coefficients": count_coefficients,
        "reg_shap_transformed": reg_shap_transformed,
        "cls_shap_transformed": cls_shap_transformed,
        "sensitivity": sensitivity,
        "predictions": predictions,
    }
    for name, table in tables.items():
        table.to_csv(paths.work_artifacts / f"{name}.csv", index=False, encoding="utf-8")

    results = {
        "metadata": metadata,
        "validation": validation,
        "split_summary": split_summary,
        "selected_models": {
            "continuous": selected_reg,
            "binary": selected_cls,
            "binomial_count": "Binomial GLM",
        },
        "count_model": count_metadata,
        "artifacts": {name: f"{name}.csv" for name in tables},
    }
    (paths.work_artifacts / "modeling_results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False, default=json_default),
        encoding="utf-8",
    )
    write_reports(
        paths,
        metadata,
        validation,
        split_summary,
        selected_reg,
        selected_cls,
        performance,
        count_metadata,
        feature_importance,
        model_input_missingness,
        sensitivity,
    )
    return results


if __name__ == "__main__":
    result = run_pipeline()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=json_default))
