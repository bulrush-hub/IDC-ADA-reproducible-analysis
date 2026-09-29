"""Reproducible TabPFN-3 benchmark for the IDC ADA modeling dataset.

This script intentionally reuses the exact row-level partition from the
baseline workflow and writes all intermediate analysis tables to
``work/tabpfn_artifacts``.  It never regenerates the train/test split.
"""

from __future__ import annotations

import gc
import hashlib
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
import torch
from dotenv import load_dotenv
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
from tabpfn import TabPFNClassifier, TabPFNRegressor
import tabpfn

from feature_layers import (
    FEATURE_LAYER_BY_FEATURE,
    PRIMARY_BINARY_FEATURES,
    PRIMARY_CATEGORICAL_FEATURES,
    PRIMARY_FEATURES,
    PRIMARY_NUMERIC_FEATURES,
)


SEED = 20260802
N_SPLITS = 5
N_ESTIMATORS = 8
PERMUTATION_REPEATS = 3
EXPECTED_TABPFN_VERSION = "8.2.0"
MODEL_SHEET = "Modeling_Data"

FEATURE_COLUMNS = list(PRIMARY_FEATURES)
CATEGORICAL_INDICES = tuple(range(len(PRIMARY_CATEGORICAL_FEATURES)))


def locate_project_root() -> Path:
    # Prefer the current working directory, then the portable release root.
    candidates = [Path.cwd(), Path(__file__).resolve().parents[2]]
    for candidate in candidates:
        if (
            candidate / "outputs" / "IDC_modeling_table_final_model_ready.xlsx"
        ).exists():
            return candidate.resolve()
    raise FileNotFoundError("Could not locate the IDC project root")


ROOT = locate_project_root()
OUTPUTS = ROOT / "outputs"
FIGURES = OUTPUTS / "modeling_figures"
ARTIFACTS = ROOT / "work" / "tabpfn_artifacts"
MODEL_CACHE = ROOT / "work" / "tabpfn_model_cache"
INPUT_XLSX = OUTPUTS / "IDC_modeling_table_final_model_ready.xlsx"
SPLIT_AUDIT = ROOT / "work" / "modeling_artifacts" / "split_audit.csv"
BASELINE_PERFORMANCE = ROOT / "work" / "modeling_artifacts" / "performance.csv"

for directory in (FIGURES, ARTIFACTS, MODEL_CACHE):
    directory.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / ".env", override=False)
os.environ["TABPFN_MODEL_CACHE_DIR"] = str(MODEL_CACHE)
os.environ.setdefault("TABPFN_NO_BROWSER", "1")


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
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for column in (
        "n_ada_assessed",
        "assessment_days",
        "dose_mg_extracted",
        "total_sequence_length",
    ):
        values = pd.to_numeric(result[column], errors="coerce").clip(lower=0)
        result[f"log_{column}"] = np.log1p(values)
    return result


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    df = prepare_dataframe(pd.read_excel(INPUT_XLSX, sheet_name=MODEL_SHEET))
    split = pd.read_csv(SPLIT_AUDIT, dtype={"idc_row_id": "string"})
    if split["idc_row_id"].duplicated().any():
        raise ValueError("split_audit.csv contains duplicate idc_row_id values")
    if set(split["partition"]) != {"train", "validation", "test"}:
        raise ValueError("Unexpected partition values in split_audit.csv")
    merged = df.merge(
        split[["idc_row_id", "partition"]],
        on="idc_row_id",
        how="left",
        validate="one_to_one",
    )
    if merged["partition"].isna().any() or len(merged) != len(split):
        raise ValueError("The modeling table does not match split_audit.csv")
    if not merged["ada_frequency_percent"].between(0, 100).all():
        raise ValueError("ADA frequency is outside 0-100")
    derived = (merged["ada_frequency_percent"] >= 10).astype(int)
    if not derived.equals(merged["ada_high_10"].astype(int)):
        raise ValueError("ada_high_10 is inconsistent with the 10% threshold")
    return merged, split


def build_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    X = df[FEATURE_COLUMNS].copy()
    for column in PRIMARY_CATEGORICAL_FEATURES:
        X[column] = X[column].fillna("Missing").astype(str)
    for column in PRIMARY_NUMERIC_FEATURES + PRIMARY_BINARY_FEATURES:
        X[column] = pd.to_numeric(X[column], errors="coerce").astype(float)
    return X


def make_regressor(*, fit_mode: str = "fit_preprocessors") -> TabPFNRegressor:
    return TabPFNRegressor(
        n_estimators=N_ESTIMATORS,
        auto_scale_n_estimators=True,
        categorical_features_indices=CATEGORICAL_INDICES,
        device="auto",
        random_state=SEED,
        fit_mode=fit_mode,
        show_progress_bar=False,
    )


def make_classifier(*, fit_mode: str = "fit_preprocessors") -> TabPFNClassifier:
    return TabPFNClassifier(
        n_estimators=N_ESTIMATORS,
        auto_scale_n_estimators=True,
        categorical_features_indices=CATEGORICAL_INDICES,
        device="auto",
        random_state=SEED,
        fit_mode=fit_mode,
        show_progress_bar=False,
    )


def regression_metrics(y_true: pd.Series | np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    return {
        "MAE": float(mean_absolute_error(y_true, prediction)),
        "RMSE": float(mean_squared_error(y_true, prediction) ** 0.5),
        "R2": float(r2_score(y_true, prediction)),
    }


def classification_metrics(y_true: pd.Series | np.ndarray, probability: np.ndarray) -> dict[str, float]:
    probability = np.asarray(probability, dtype=float)
    label = (probability >= 0.5).astype(int)
    safe_probability = np.clip(probability, 1e-15, 1 - 1e-15)
    return {
        "ROC_AUC": float(roc_auc_score(y_true, probability)),
        "PR_AUC": float(average_precision_score(y_true, probability)),
        "F1": float(f1_score(y_true, label, zero_division=0)),
        "Balanced_Accuracy": float(balanced_accuracy_score(y_true, label)),
        "Brier": float(brier_score_loss(y_true, probability)),
        "Log_Loss": float(log_loss(y_true, safe_probability, labels=[0, 1])),
    }


def grouped_cross_validation(
    X: pd.DataFrame,
    y_reg: pd.Series,
    y_cls: pd.Series,
    groups: pd.Series,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    splitter = GroupKFold(n_splits=N_SPLITS)
    for fold, (train_idx, valid_idx) in enumerate(
        splitter.split(X, y_reg, groups), start=1
    ):
        X_train, X_valid = X.iloc[train_idx], X.iloc[valid_idx]

        reg = make_regressor()
        start = time.perf_counter()
        reg.fit(X_train, y_reg.iloc[train_idx])
        fit_seconds = time.perf_counter() - start
        start = time.perf_counter()
        reg_prediction = np.asarray(reg.predict(X_valid), dtype=float)
        predict_seconds = time.perf_counter() - start
        rows.append(
            {
                "outcome": "continuous",
                "fold": fold,
                **regression_metrics(y_reg.iloc[valid_idx], reg_prediction),
                "fit_seconds": fit_seconds,
                "predict_seconds": predict_seconds,
                "validation_rows": len(valid_idx),
                "validation_groups": groups.iloc[valid_idx].nunique(),
            }
        )
        del reg
        gc.collect()

        clf = make_classifier()
        start = time.perf_counter()
        clf.fit(X_train, y_cls.iloc[train_idx])
        fit_seconds = time.perf_counter() - start
        start = time.perf_counter()
        probability = np.asarray(clf.predict_proba(X_valid)[:, 1], dtype=float)
        predict_seconds = time.perf_counter() - start
        rows.append(
            {
                "outcome": "binary",
                "fold": fold,
                **classification_metrics(y_cls.iloc[valid_idx], probability),
                "fit_seconds": fit_seconds,
                "predict_seconds": predict_seconds,
                "validation_rows": len(valid_idx),
                "validation_groups": groups.iloc[valid_idx].nunique(),
            }
        )
        del clf
        gc.collect()
    return pd.DataFrame(rows)


def summarize_cv(folds: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    metric_map = {
        "continuous": ["MAE", "RMSE", "R2", "fit_seconds", "predict_seconds"],
        "binary": [
            "ROC_AUC",
            "PR_AUC",
            "F1",
            "Balanced_Accuracy",
            "Brier",
            "Log_Loss",
            "fit_seconds",
            "predict_seconds",
        ],
    }
    for outcome, metrics in metric_map.items():
        subset = folds.loc[folds["outcome"].eq(outcome)]
        for metric in metrics:
            values = pd.to_numeric(subset[metric], errors="coerce").dropna()
            rows.append(
                {
                    "outcome": outcome,
                    "metric": metric,
                    "mean": float(values.mean()),
                    "sd": float(values.std(ddof=1)),
                    "folds": int(len(values)),
                }
            )
    return pd.DataFrame(rows)


def permutation_importance_table(
    X_test: pd.DataFrame,
    y_true: pd.Series,
    predict: Callable[[pd.DataFrame], np.ndarray],
    score: Callable[[pd.Series, np.ndarray], float],
    *,
    outcome: str,
) -> pd.DataFrame:
    baseline = score(y_true, predict(X_test))
    rows: list[dict[str, Any]] = []
    for feature_number, feature in enumerate(FEATURE_COLUMNS):
        changes: list[float] = []
        for repeat in range(PERMUTATION_REPEATS):
            rng = np.random.default_rng(SEED + feature_number * 101 + repeat)
            shuffled = X_test.copy()
            shuffled[feature] = rng.permutation(shuffled[feature].to_numpy())
            changes.append(float(score(y_true, predict(shuffled)) - baseline))
        rows.append(
            {
                "outcome": outcome,
                "feature": feature,
                "feature_layer": FEATURE_LAYER_BY_FEATURE[feature],
                "importance_mean": float(np.mean(changes)),
                "importance_sd": float(np.std(changes, ddof=1)),
                "repeats": PERMUTATION_REPEATS,
                "importance_definition": (
                    "increase in MAE after permutation"
                    if outcome == "continuous"
                    else "decrease in ROC-AUC after permutation"
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["outcome", "importance_mean"], ascending=[True, False]
    )


def build_comparison(test_metrics: pd.DataFrame) -> pd.DataFrame:
    baseline = pd.read_csv(BASELINE_PERFORMANCE)
    selected = baseline["selected"].astype(str).str.lower().eq("true")
    current_reg = baseline.loc[
        baseline["outcome"].eq("continuous") & selected
    ].iloc[0]
    current_cls = baseline.loc[
        baseline["outcome"].eq("binary") & selected
    ].iloc[0]
    tab_reg = test_metrics.loc[
        test_metrics["outcome"].eq("continuous")
        & test_metrics["prediction_variant"].eq("raw")
    ].iloc[0]
    tab_cls = test_metrics.loc[test_metrics["outcome"].eq("binary")].iloc[0]
    definitions = [
        ("continuous", "MAE", "test_MAE", "MAE", False),
        ("continuous", "RMSE", "test_RMSE", "RMSE", False),
        ("continuous", "R2", "test_R2", "R2", True),
        ("binary", "ROC_AUC", "test_ROC_AUC", "ROC_AUC", True),
        ("binary", "PR_AUC", "test_PR_AUC", "PR_AUC", True),
        ("binary", "F1", "test_F1", "F1", True),
        (
            "binary",
            "Balanced_Accuracy",
            "test_Balanced_Accuracy",
            "Balanced_Accuracy",
            True,
        ),
        ("binary", "Brier", "test_Brier", "Brier", False),
        ("binary", "Log_Loss", "test_Log_Loss", "Log_Loss", False),
    ]
    rows: list[dict[str, Any]] = []
    for outcome, metric, current_col, tab_col, higher_is_better in definitions:
        current_row = current_reg if outcome == "continuous" else current_cls
        tab_row = tab_reg if outcome == "continuous" else tab_cls
        current_value = float(current_row[current_col])
        tab_value = float(tab_row[tab_col])
        winner = (
            "TabPFN"
            if (tab_value > current_value) == higher_is_better
            else str(current_row["model"])
        )
        rows.append(
            {
                "outcome": outcome,
                "metric": metric,
                "higher_is_better": higher_is_better,
                "current_model": current_row["model"],
                "current_value": current_value,
                "tabpfn_model": "TabPFN-3",
                "tabpfn_value": tab_value,
                "tabpfn_minus_current": tab_value - current_value,
                "winner": winner,
            }
        )
    return pd.DataFrame(rows)


def save_comparison_figure(comparison: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    for axis, outcome, title in zip(
        axes,
        ("continuous", "binary"),
        ("Continuous ADA frequency", "ADA >=10% classification"),
    ):
        data = comparison.loc[comparison["outcome"].eq(outcome)].copy()
        current = data["current_value"].to_numpy(float)
        tab_value = data["tabpfn_value"].to_numpy(float)
        indices = np.arange(len(data))
        width = 0.38
        axis.bar(indices - width / 2, current, width, label="Current model", color="#64748B")
        axis.bar(indices + width / 2, tab_value, width, label="TabPFN-3", color="#0F766E")
        axis.set_xticks(indices, data["metric"], rotation=35, ha="right")
        axis.set_title(title)
        axis.grid(axis="y", alpha=0.25)
        axis.legend(frameon=False)
    fig.suptitle("Independent test-set performance: current model vs TabPFN-3")
    fig.tight_layout()
    fig.savefig(FIGURES / "tabpfn_performance_comparison.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_report(
    comparison: pd.DataFrame,
    test_metrics: pd.DataFrame,
    metadata: dict[str, Any],
) -> None:
    rows = []
    for row in comparison.itertuples(index=False):
        rows.append(
            f"| {row.outcome} | {row.metric} | {row.current_value:.4f} | "
            f"{row.tabpfn_value:.4f} | {row.winner} |"
        )
    reg_raw = test_metrics.loc[
        test_metrics["outcome"].eq("continuous")
        & test_metrics["prediction_variant"].eq("raw")
    ].iloc[0]
    cls = test_metrics.loc[test_metrics["outcome"].eq("binary")].iloc[0]
    content = f"""# IDC TabPFN-3 与当前模型比较

## 设计

- TabPFN 包版本：{metadata['tabpfn_version']}；默认权重：TabPFN-3。
- 输入：与当前模型相同的 {len(FEATURE_COLUMNS)} 个特征，不加入分子名称或研究/来源标识。
- 数据拆分：直接复用 `split_audit.csv`；开发集为 train+validation，测试集保持封存。
- 模型选择评估：开发集 5 折 GroupKFold；同一 `model_split_group` 不跨折。
- TabPFN 预处理：保留原始类别列并显式标记类别索引；不做 one-hot 或缩放。

## 独立测试集结果

| 结局 | 指标 | 当前模型 | TabPFN-3 | 更优者 |
|---|---|---:|---:|---|
{chr(10).join(rows)}

TabPFN 连续预测（未裁剪）：MAE {reg_raw['MAE']:.3f} pp，RMSE {reg_raw['RMSE']:.3f} pp，R2 {reg_raw['R2']:.3f}。

TabPFN 二分类：ROC-AUC {cls['ROC_AUC']:.3f}，PR-AUC {cls['PR_AUC']:.3f}，F1 {cls['F1']:.3f}，Brier {cls['Brier']:.3f}。

## 解释限制

- 这是按研究组隔离的内部独立测试，不是外部验证。
- 置换重要性表示预测贡献，不表示因果关系；相关特征会分摊重要性。
- TabPFN-3 权重和输出受 Prior Labs 非商业许可约束，生产或商业用途需另行确认授权。
- 对全新分子的外推风险仍以既有“未见分子留出”敏感性分析为准。
"""
    (OUTPUTS / "IDC_TabPFN_comparison_report.md").write_text(content, encoding="utf-8")


def main() -> None:
    if tabpfn.__version__ != EXPECTED_TABPFN_VERSION:
        raise RuntimeError(
            f"Expected tabpfn {EXPECTED_TABPFN_VERSION}, got {tabpfn.__version__}"
        )
    df, split = load_inputs()
    X = build_feature_frame(df)
    dev_mask = df["partition"].isin(["train", "validation"])
    test_mask = df["partition"].eq("test")
    X_dev, X_test = X.loc[dev_mask].reset_index(drop=True), X.loc[test_mask].reset_index(drop=True)
    y_reg_dev = df.loc[dev_mask, "ada_frequency_percent"].reset_index(drop=True)
    y_reg_test = df.loc[test_mask, "ada_frequency_percent"].reset_index(drop=True)
    y_cls_dev = df.loc[dev_mask, "ada_high_10"].astype(int).reset_index(drop=True)
    y_cls_test = df.loc[test_mask, "ada_high_10"].astype(int).reset_index(drop=True)
    groups_dev = df.loc[dev_mask, "model_split_group"].astype(str).reset_index(drop=True)

    cv_folds = grouped_cross_validation(X_dev, y_reg_dev, y_cls_dev, groups_dev)
    cv_summary = summarize_cv(cv_folds)
    cv_folds.to_csv(ARTIFACTS / "tabpfn_cv_folds.csv", index=False)
    cv_summary.to_csv(ARTIFACTS / "tabpfn_cv_summary.csv", index=False)

    runtime_rows: list[dict[str, Any]] = []
    reg = make_regressor(fit_mode="fit_with_cache")
    start = time.perf_counter()
    reg.fit(X_dev, y_reg_dev)
    runtime_rows.append({"outcome": "continuous", "phase": "fit", "seconds": time.perf_counter() - start})
    start = time.perf_counter()
    reg_prediction = np.asarray(reg.predict(X_test), dtype=float)
    runtime_rows.append({"outcome": "continuous", "phase": "test_predict", "seconds": time.perf_counter() - start})
    reg_clipped = np.clip(reg_prediction, 0, 100)

    clf = make_classifier(fit_mode="fit_with_cache")
    start = time.perf_counter()
    clf.fit(X_dev, y_cls_dev)
    runtime_rows.append({"outcome": "binary", "phase": "fit", "seconds": time.perf_counter() - start})
    start = time.perf_counter()
    cls_probability = np.asarray(clf.predict_proba(X_test)[:, 1], dtype=float)
    runtime_rows.append({"outcome": "binary", "phase": "test_predict", "seconds": time.perf_counter() - start})

    test_metrics = pd.DataFrame(
        [
            {"outcome": "continuous", "prediction_variant": "raw", **regression_metrics(y_reg_test, reg_prediction)},
            {"outcome": "continuous", "prediction_variant": "clipped_0_100", **regression_metrics(y_reg_test, reg_clipped)},
            {"outcome": "binary", "prediction_variant": "probability", **classification_metrics(y_cls_test, cls_probability)},
        ]
    )

    predictions = df.loc[test_mask, ["idc_row_id", "model_split_group", "molecule_inn_name"]].reset_index(drop=True)
    predictions["ada_frequency_percent_actual"] = y_reg_test
    predictions["tabpfn_regression_raw"] = reg_prediction
    predictions["tabpfn_regression_clipped_0_100"] = reg_clipped
    predictions["ada_high_10_actual"] = y_cls_test
    predictions["tabpfn_probability_ada_high_10"] = cls_probability
    predictions["tabpfn_predicted_ada_high_10"] = (cls_probability >= 0.5).astype(int)

    reg_importance = permutation_importance_table(
        X_test,
        y_reg_test,
        lambda frame: np.asarray(reg.predict(frame), dtype=float),
        lambda actual, pred: float(mean_absolute_error(actual, pred)),
        outcome="continuous",
    )
    cls_importance = permutation_importance_table(
        X_test,
        y_cls_test,
        lambda frame: np.asarray(clf.predict_proba(frame)[:, 1], dtype=float),
        lambda actual, pred: float(roc_auc_score(actual, pred)) * -1,
        outcome="binary",
    )
    importance = pd.concat([reg_importance, cls_importance], ignore_index=True)

    comparison = build_comparison(test_metrics)
    runtime = pd.DataFrame(runtime_rows)
    test_metrics.to_csv(ARTIFACTS / "tabpfn_test_metrics.csv", index=False)
    predictions.to_csv(ARTIFACTS / "tabpfn_predictions.csv", index=False)
    importance.to_csv(ARTIFACTS / "tabpfn_feature_importance.csv", index=False)
    comparison.to_csv(ARTIFACTS / "tabpfn_comparison.csv", index=False)
    runtime.to_csv(ARTIFACTS / "tabpfn_runtime.csv", index=False)
    save_comparison_figure(comparison)

    metadata = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "input_file": str(INPUT_XLSX.relative_to(ROOT)),
        "input_sha256": file_sha256(INPUT_XLSX),
        "split_file": str(SPLIT_AUDIT.relative_to(ROOT)),
        "split_sha256": file_sha256(SPLIT_AUDIT),
        "rows": len(df),
        "development_rows": int(dev_mask.sum()),
        "test_rows": int(test_mask.sum()),
        "feature_count": len(FEATURE_COLUMNS),
        "categorical_feature_count": len(PRIMARY_CATEGORICAL_FEATURES),
        "numeric_and_binary_feature_count": len(PRIMARY_NUMERIC_FEATURES) + len(PRIMARY_BINARY_FEATURES),
        "tabpfn_version": tabpfn.__version__,
        "tabpfn_model_version": "TabPFN-3 default checkpoint",
        "n_estimators": N_ESTIMATORS,
        "seed": SEED,
        "cv_folds": N_SPLITS,
        "permutation_repeats": PERMUTATION_REPEATS,
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "torch_version": torch.__version__,
        "torch_cuda_available": torch.cuda.is_available(),
        "torch_cuda_version": torch.version.cuda,
        "sklearn_version": sklearn.__version__,
        "pandas_version": pd.__version__,
        "numpy_version": np.__version__,
        "model_cache": str(MODEL_CACHE.relative_to(ROOT)),
        "license": "TabPFN-3 Non-Commercial License v1.0",
    }
    (ARTIFACTS / "tabpfn_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )
    write_report(comparison, test_metrics, metadata)

    print(comparison.to_string(index=False))
    print(f"Artifacts written to: {ARTIFACTS}")


if __name__ == "__main__":
    main()
