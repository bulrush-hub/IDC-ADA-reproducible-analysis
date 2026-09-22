"""Post-process development-only OOF predictions for IDC validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import brentq, minimize
from scipy.special import expit, logit
from scipy.stats import spearmanr
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)


SEED = 20260802
BOOTSTRAP_REPEATS = 2000
# The release stores scripts in code/modeling; repository data and outputs are
# located two directory levels above this file.
ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "work" / "validation_stage2"
OUTPUTS = ROOT / "outputs"
FIGURES = OUTPUTS / "modeling_figures"
REPORT = OUTPUTS / "IDC_OOF_validation_report.md"
FIGURES.mkdir(parents=True, exist_ok=True)


MODEL_COLUMNS = {
    "Random forest": ("rf_regression", "rf_probability"),
    "TabPFN-3": ("tabpfn_regression", "tabpfn_probability"),
}


def safe_probability(probability: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(probability, dtype=float), 1e-8, 1 - 1e-8)


def calibration_parameters(actual: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    actual = np.asarray(actual, dtype=float)
    probability = safe_probability(probability)
    linear_predictor = logit(probability)

    def objective(parameters: np.ndarray) -> float:
        fitted = expit(parameters[0] + parameters[1] * linear_predictor)
        return float(-np.sum(actual * np.log(fitted) + (1 - actual) * np.log(1 - fitted)))

    result = minimize(objective, np.array([0.0, 1.0]), method="BFGS")
    if not result.success and not np.isfinite(result.fun):
        raise RuntimeError("Calibration intercept/slope optimization failed")

    def citl_equation(intercept: float) -> float:
        return float(np.sum(expit(linear_predictor + intercept)) - actual.sum())

    citl = float(brentq(citl_equation, -30, 30))
    return {
        "calibration_in_the_large": citl,
        "calibration_intercept_joint": float(result.x[0]),
        "calibration_slope": float(result.x[1]),
    }


def weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    return float(np.average(values[valid], weights=weights[valid])) if valid.any() else np.nan


def overall_metrics(predictions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scheme, subset in predictions.groupby("validation_scheme", observed=True):
        actual_reg = subset["ada_frequency_percent"].to_numpy(float)
        actual_cls = subset["ada_high_10"].to_numpy(int)
        weights = pd.to_numeric(subset["n_ada_assessed"], errors="coerce").to_numpy(float)
        for model, (regression_column, probability_column) in MODEL_COLUMNS.items():
            regression = subset[regression_column].to_numpy(float)
            probability = subset[probability_column].to_numpy(float)
            label = (probability >= 0.5).astype(int)
            calibration = calibration_parameters(actual_cls, probability)
            regression_slope, regression_intercept = np.polyfit(regression, actual_reg, 1)
            rows.extend(
                [
                    {
                        "validation_scheme": scheme,
                        "model": model,
                        "outcome": "continuous",
                        "metric": "MAE",
                        "value": mean_absolute_error(actual_reg, regression),
                    },
                    {
                        "validation_scheme": scheme,
                        "model": model,
                        "outcome": "continuous",
                        "metric": "RMSE",
                        "value": mean_squared_error(actual_reg, regression) ** 0.5,
                    },
                    {
                        "validation_scheme": scheme,
                        "model": model,
                        "outcome": "continuous",
                        "metric": "R2",
                        "value": r2_score(actual_reg, regression),
                    },
                    {
                        "validation_scheme": scheme,
                        "model": model,
                        "outcome": "continuous",
                        "metric": "Mean_bias_predicted_minus_observed",
                        "value": float(np.mean(regression - actual_reg)),
                    },
                    {
                        "validation_scheme": scheme,
                        "model": model,
                        "outcome": "continuous",
                        "metric": "Spearman",
                        "value": float(spearmanr(actual_reg, regression).statistic),
                    },
                    {
                        "validation_scheme": scheme,
                        "model": model,
                        "outcome": "continuous",
                        "metric": "Observed_on_predicted_intercept",
                        "value": float(regression_intercept),
                    },
                    {
                        "validation_scheme": scheme,
                        "model": model,
                        "outcome": "continuous",
                        "metric": "Observed_on_predicted_slope",
                        "value": float(regression_slope),
                    },
                    {
                        "validation_scheme": scheme,
                        "model": model,
                        "outcome": "continuous",
                        "metric": "Assessed_n_weighted_MAE",
                        "value": weighted_mean(np.abs(actual_reg - regression), weights),
                    },
                    {
                        "validation_scheme": scheme,
                        "model": model,
                        "outcome": "binary",
                        "metric": "ROC_AUC",
                        "value": roc_auc_score(actual_cls, probability),
                    },
                    {
                        "validation_scheme": scheme,
                        "model": model,
                        "outcome": "binary",
                        "metric": "PR_AUC",
                        "value": average_precision_score(actual_cls, probability),
                    },
                    {
                        "validation_scheme": scheme,
                        "model": model,
                        "outcome": "binary",
                        "metric": "Brier",
                        "value": brier_score_loss(actual_cls, probability),
                    },
                    {
                        "validation_scheme": scheme,
                        "model": model,
                        "outcome": "binary",
                        "metric": "Log_Loss",
                        "value": log_loss(actual_cls, safe_probability(probability), labels=[0, 1]),
                    },
                    {
                        "validation_scheme": scheme,
                        "model": model,
                        "outcome": "binary",
                        "metric": "F1_at_0.5",
                        "value": f1_score(actual_cls, label, zero_division=0),
                    },
                    {
                        "validation_scheme": scheme,
                        "model": model,
                        "outcome": "binary",
                        "metric": "Balanced_Accuracy_at_0.5",
                        "value": balanced_accuracy_score(actual_cls, label),
                    },
                    {
                        "validation_scheme": scheme,
                        "model": model,
                        "outcome": "binary",
                        "metric": "Calibration_in_the_large",
                        "value": calibration["calibration_in_the_large"],
                    },
                    {
                        "validation_scheme": scheme,
                        "model": model,
                        "outcome": "binary",
                        "metric": "Calibration_intercept_joint",
                        "value": calibration["calibration_intercept_joint"],
                    },
                    {
                        "validation_scheme": scheme,
                        "model": model,
                        "outcome": "binary",
                        "metric": "Calibration_slope",
                        "value": calibration["calibration_slope"],
                    },
                    {
                        "validation_scheme": scheme,
                        "model": model,
                        "outcome": "binary",
                        "metric": "Assessed_n_weighted_Brier",
                        "value": weighted_mean((actual_cls - probability) ** 2, weights),
                    },
                ]
            )
    return pd.DataFrame(rows)


def calibration_bins(predictions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scheme, subset in predictions.groupby("validation_scheme", observed=True):
        for model, (_, probability_column) in MODEL_COLUMNS.items():
            working = subset[["ada_high_10", probability_column]].copy()
            working["bin"] = pd.qcut(
                working[probability_column], q=10, labels=False, duplicates="drop"
            )
            summary = (
                working.groupby("bin", observed=True)
                .agg(
                    rows=("ada_high_10", "size"),
                    mean_predicted=(probability_column, "mean"),
                    observed_rate=("ada_high_10", "mean"),
                    minimum_predicted=(probability_column, "min"),
                    maximum_predicted=(probability_column, "max"),
                )
                .reset_index()
            )
            summary.insert(0, "model", model)
            summary.insert(0, "validation_scheme", scheme)
            rows.extend(summary.to_dict("records"))
    return pd.DataFrame(rows)


def threshold_table(predictions: pd.DataFrame) -> pd.DataFrame:
    study = predictions.loc[predictions["validation_scheme"].eq("study")]
    actual = study["ada_high_10"].to_numpy(int)
    rows: list[dict[str, object]] = []
    for model, (_, probability_column) in MODEL_COLUMNS.items():
        probability = study[probability_column].to_numpy(float)
        for threshold in np.arange(0.05, 0.801, 0.05):
            label = (probability >= threshold).astype(int)
            tn = int(np.sum((label == 0) & (actual == 0)))
            fp = int(np.sum((label == 1) & (actual == 0)))
            fn = int(np.sum((label == 0) & (actual == 1)))
            tp = int(np.sum((label == 1) & (actual == 1)))
            rows.append(
                {
                    "model": model,
                    "threshold": float(round(threshold, 2)),
                    "true_negative": tn,
                    "false_positive": fp,
                    "false_negative": fn,
                    "true_positive": tp,
                    "sensitivity": recall_score(actual, label, zero_division=0),
                    "specificity": tn / (tn + fp) if tn + fp else np.nan,
                    "precision": precision_score(actual, label, zero_division=0),
                    "negative_predictive_value": tn / (tn + fn) if tn + fn else np.nan,
                    "F1": f1_score(actual, label, zero_division=0),
                    "balanced_accuracy": balanced_accuracy_score(actual, label),
                    "predicted_positive_rate": float(label.mean()),
                    "selection_status": "Exploratory development-only; not locked",
                }
            )
    return pd.DataFrame(rows)


def metric_values(frame: pd.DataFrame) -> dict[str, float]:
    actual_reg = frame["ada_frequency_percent"].to_numpy(float)
    actual_cls = frame["ada_high_10"].to_numpy(int)
    rf_reg = frame["rf_regression"].to_numpy(float)
    tab_reg = frame["tabpfn_regression"].to_numpy(float)
    rf_prob = frame["rf_probability"].to_numpy(float)
    tab_prob = frame["tabpfn_probability"].to_numpy(float)
    rf_label = (rf_prob >= 0.5).astype(int)
    tab_label = (tab_prob >= 0.5).astype(int)
    return {
        "MAE": mean_absolute_error(actual_reg, rf_reg) - mean_absolute_error(actual_reg, tab_reg),
        "RMSE": mean_squared_error(actual_reg, rf_reg) ** 0.5 - mean_squared_error(actual_reg, tab_reg) ** 0.5,
        "R2": r2_score(actual_reg, tab_reg) - r2_score(actual_reg, rf_reg),
        "ROC_AUC": roc_auc_score(actual_cls, tab_prob) - roc_auc_score(actual_cls, rf_prob),
        "PR_AUC": average_precision_score(actual_cls, tab_prob) - average_precision_score(actual_cls, rf_prob),
        "F1_at_0.5": f1_score(actual_cls, tab_label, zero_division=0) - f1_score(actual_cls, rf_label, zero_division=0),
        "Balanced_Accuracy_at_0.5": balanced_accuracy_score(actual_cls, tab_label) - balanced_accuracy_score(actual_cls, rf_label),
        "Brier": brier_score_loss(actual_cls, rf_prob) - brier_score_loss(actual_cls, tab_prob),
        "Log_Loss": log_loss(actual_cls, safe_probability(rf_prob), labels=[0, 1]) - log_loss(actual_cls, safe_probability(tab_prob), labels=[0, 1]),
    }


def paired_cluster_bootstrap(predictions: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(SEED + 501)
    rows: list[dict[str, object]] = []
    for scheme, subset in predictions.groupby("validation_scheme", observed=True):
        group_column = "model_split_group" if scheme == "study" else "molecule_inn_name"
        group_values = subset[group_column].astype(str).unique()
        lookup = {group: subset.index[subset[group_column].astype(str).eq(group)].to_numpy() for group in group_values}
        point = metric_values(subset)
        samples: dict[str, list[float]] = {metric: [] for metric in point}
        valid_repeats = 0
        for _ in range(BOOTSTRAP_REPEATS):
            sampled_groups = rng.choice(group_values, size=len(group_values), replace=True)
            sampled_indices = np.concatenate([lookup[group] for group in sampled_groups])
            sampled = subset.loc[sampled_indices]
            if sampled["ada_high_10"].nunique() < 2:
                continue
            values = metric_values(sampled)
            for metric, value in values.items():
                samples[metric].append(float(value))
            valid_repeats += 1
        for metric, point_value in point.items():
            values = np.asarray(samples[metric], dtype=float)
            rows.append(
                {
                    "validation_scheme": scheme,
                    "metric": metric,
                    "tabpfn_improvement": point_value,
                    "ci_2_5": float(np.quantile(values, 0.025)),
                    "ci_97_5": float(np.quantile(values, 0.975)),
                    "probability_tabpfn_better": float(np.mean(values > 0)),
                    "valid_repeats": valid_repeats,
                    "resampling_unit": group_column,
                    "conclusion": (
                        "TabPFN improvement supported"
                        if np.quantile(values, 0.025) > 0
                        else "Random forest advantage supported"
                        if np.quantile(values, 0.975) < 0
                        else "Difference uncertain"
                    ),
                }
            )
    return pd.DataFrame(rows)


def subgroup_performance(predictions: pd.DataFrame) -> pd.DataFrame:
    study = predictions.loc[predictions["validation_scheme"].eq("study")].copy()
    study["assay_sensitivity_status"] = np.where(
        study["ada_assay_sensitivity_missing"].fillna(1).astype(int).eq(1),
        "Not reported",
        "Reported",
    )
    study["assessment_duration_band"] = pd.cut(
        pd.to_numeric(study["assessment_days"], errors="coerce"),
        bins=[-np.inf, 28, 84, 180, 365, np.inf],
        labels=["≤28 days", "29–84 days", "85–180 days", "181–365 days", ">365 days"],
    ).astype("string").fillna("Missing")
    study["assessed_sample_size_band"] = pd.cut(
        pd.to_numeric(study["n_ada_assessed"], errors="coerce"),
        bins=[-np.inf, 49, 199, 499, np.inf],
        labels=["<50", "50–199", "200–499", "≥500"],
    ).astype("string").fillna("Missing")
    dimensions = [
        "ada_assay_platform",
        "assay_sensitivity_status",
        "assessment_duration_band",
        "assessed_sample_size_band",
        "disease_category_clean",
        "route_clean",
        "labelled_as_biosimilar",
    ]
    rows: list[dict[str, object]] = []
    for dimension in dimensions:
        levels = study[dimension].astype("string").fillna("Missing")
        for level, index in levels.groupby(levels, observed=True).groups.items():
            subset = study.loc[index]
            actual_reg = subset["ada_frequency_percent"].to_numpy(float)
            actual_cls = subset["ada_high_10"].to_numpy(int)
            ready = (
                len(subset) >= 50
                and subset["model_split_group"].nunique() >= 20
                and actual_cls.sum() >= 10
                and (len(actual_cls) - actual_cls.sum()) >= 10
            )
            for model, (regression_column, probability_column) in MODEL_COLUMNS.items():
                probability = subset[probability_column].to_numpy(float)
                row = {
                    "dimension": dimension,
                    "level": str(level),
                    "model": model,
                    "rows": len(subset),
                    "study_groups": subset["model_split_group"].nunique(),
                    "molecules": subset["molecule_inn_name"].nunique(),
                    "positive_rows": int(actual_cls.sum()),
                    "negative_rows": int(len(actual_cls) - actual_cls.sum()),
                    "readiness": "Ready" if ready else "Descriptive only",
                    "MAE": mean_absolute_error(actual_reg, subset[regression_column]),
                    "Brier": brier_score_loss(actual_cls, probability),
                    "ROC_AUC": roc_auc_score(actual_cls, probability) if np.unique(actual_cls).size == 2 else np.nan,
                    "PR_AUC": average_precision_score(actual_cls, probability) if actual_cls.sum() else np.nan,
                }
                rows.append(row)
    return pd.DataFrame(rows)


def error_by_actual_band(predictions: pd.DataFrame) -> pd.DataFrame:
    study = predictions.loc[predictions["validation_scheme"].eq("study")].copy()
    study["actual_ada_band"] = pd.cut(
        study["ada_frequency_percent"],
        bins=[-0.001, 0, 1, 5, 10, 25, 50, 100],
        labels=["0", ">0–1", ">1–5", ">5–10", ">10–25", ">25–50", ">50–100"],
        include_lowest=True,
    )
    rows: list[dict[str, object]] = []
    for band, subset in study.groupby("actual_ada_band", observed=True):
        for model, (regression_column, _) in MODEL_COLUMNS.items():
            error = subset[regression_column] - subset["ada_frequency_percent"]
            rows.append(
                {
                    "actual_ada_band": str(band),
                    "model": model,
                    "rows": len(subset),
                    "study_groups": subset["model_split_group"].nunique(),
                    "MAE": float(np.mean(np.abs(error))),
                    "mean_bias_predicted_minus_observed": float(np.mean(error)),
                }
            )
    return pd.DataFrame(rows)


def save_figures(bins: pd.DataFrame, thresholds: pd.DataFrame, errors: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2))
    for axis, scheme, title in zip(
        axes,
        ["study", "molecule"],
        ["New-study validation", "Unseen-molecule validation"],
    ):
        subset = bins.loc[bins["validation_scheme"].eq(scheme)]
        axis.plot([0, 1], [0, 1], linestyle="--", color="#64748B", label="Ideal")
        for model, color in [("Random forest", "#64748B"), ("TabPFN-3", "#0F766E")]:
            model_data = subset.loc[subset["model"].eq(model)]
            axis.plot(
                model_data["mean_predicted"],
                model_data["observed_rate"],
                marker="o",
                linewidth=2,
                label=model,
                color=color,
            )
        axis.set(title=title, xlabel="Mean predicted probability", ylabel="Observed high-ADA rate", xlim=(0, 1), ylim=(0, 1))
        axis.grid(alpha=0.2)
        axis.legend(frameon=False)
    fig.suptitle("Development-only OOF calibration")
    fig.tight_layout()
    fig.savefig(FIGURES / "oof_calibration_curves.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2))
    for axis, metric, label in zip(axes, ["F1", "balanced_accuracy"], ["F1", "Balanced accuracy"]):
        for model, color in [("Random forest", "#64748B"), ("TabPFN-3", "#0F766E")]:
            model_data = thresholds.loc[thresholds["model"].eq(model)]
            axis.plot(model_data["threshold"], model_data[metric], marker="o", label=model, color=color)
        axis.set(title=f"{label} across probability thresholds", xlabel="Probability threshold", ylabel=label)
        axis.grid(alpha=0.2)
        axis.legend(frameon=False)
    fig.suptitle("Exploratory threshold sensitivity — development OOF only")
    fig.tight_layout()
    fig.savefig(FIGURES / "oof_threshold_sensitivity.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    order = ["0", ">0–1", ">1–5", ">5–10", ">10–25", ">25–50", ">50–100"]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    positions = np.arange(len(order))
    width = 0.38
    for offset, (model, color) in zip([-width / 2, width / 2], [("Random forest", "#64748B"), ("TabPFN-3", "#0F766E")]):
        model_data = errors.loc[errors["model"].eq(model)].set_index("actual_ada_band").reindex(order)
        ax.bar(positions + offset, model_data["MAE"], width, label=model, color=color)
    ax.set_xticks(positions, order)
    ax.set(title="OOF continuous error by observed ADA band", xlabel="Observed ADA frequency band (%)", ylabel="MAE (percentage points)")
    ax.grid(axis="y", alpha=0.2)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIGURES / "oof_error_by_ada_band.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def value(metrics: pd.DataFrame, scheme: str, model: str, metric: str) -> float:
    return float(
        metrics.loc[
            metrics["validation_scheme"].eq(scheme)
            & metrics["model"].eq(model)
            & metrics["metric"].eq(metric),
            "value",
        ].iloc[0]
    )


def write_report(metrics: pd.DataFrame, bootstrap: pd.DataFrame, runtime: pd.DataFrame) -> None:
    study_rows = []
    molecule_rows = []
    report_metrics = ["MAE", "RMSE", "R2", "ROC_AUC", "PR_AUC", "Brier", "Log_Loss", "Calibration_slope"]
    for scheme, rows in [("study", study_rows), ("molecule", molecule_rows)]:
        for metric in report_metrics:
            rows.append(
                f"| {metric} | {value(metrics, scheme, 'Random forest', metric):.4f} | "
                f"{value(metrics, scheme, 'TabPFN-3', metric):.4f} |"
            )
    supported = bootstrap.loc[
        bootstrap["validation_scheme"].eq("study")
        & bootstrap["conclusion"].ne("Difference uncertain")
    ]
    supported_text = ", ".join(
        f"{row.metric} ({row.conclusion})" for row in supported.itertuples(index=False)
    ) or "无"
    total_runtime = runtime[["fit_seconds", "predict_seconds"]].sum().sum()
    content = f"""# IDC 开发集 OOF 校准与泛化验证报告

## 设计锁定

- 仅使用原 train+validation 开发集 2,237 行；未使用 374 行封存测试结局。
- 研究验证：5 折 `GroupKFold(model_split_group)`，评价新研究泛化。
- 分子验证：5 折 `GroupKFold(molecule_inn_name)`，评价全新分子压力测试。
- 两个模型使用相同 29 项信息；随机森林保留原预处理，TabPFN-3 使用原生类别输入。
- 阈值表仅用于开发集敏感性，不据此修改封存测试结论。

## 研究组隔离 OOF

| 指标 | 随机森林 | TabPFN-3 |
|---|---:|---:|
{chr(10).join(study_rows)}

研究组在每折训练/验证间重叠为 0；分子可跨折出现。配对研究组 Bootstrap 中有方向支持的指标：{supported_text}。

主要观察：TabPFN-3 的 OOF MAE 为 {value(metrics, 'study', 'TabPFN-3', 'MAE'):.3f}，低于随机森林的 {value(metrics, 'study', 'Random forest', 'MAE'):.3f}；但 RMSE 与 R²几乎相同。随机森林的 ROC-AUC/PR-AUC 较高，而 TabPFN-3 的 Brier 略低。上述配对差异的 95% Bootstrap 区间均跨 0，不能据此宣布开发集上的稳定胜者。

## 分子隔离 OOF 压力测试

| 指标 | 随机森林 | TabPFN-3 |
|---|---:|---:|
{chr(10).join(molecule_rows)}

每折分子重叠为 0，但同一多臂研究的其他分子仍可能在训练折；五折分别有 8、22、17、13、19 个研究组发生这种上下文重叠。因此本结果比原研究拆分更接近新分子任务，但仍不是完全独立外部验证。

主要观察：两模型的分子 OOF ROC-AUC 均约为 0.64，明显低于研究组 OOF；TabPFN-3 的连续 MAE 为 {value(metrics, 'molecule', 'TabPFN-3', 'MAE'):.3f}，随机森林为 {value(metrics, 'molecule', 'Random forest', 'MAE'):.3f}，但差异区间跨 0。当前特征对全新分子的二分类区分能力有限。

## 校准解释

- 理想校准截距/CITL 为 0，理想校准斜率为 1。
- 斜率小于 1 通常表示预测过于极端；大于 1 表示预测变化范围偏窄。
- 校准曲线采用开发集 OOF 十分位汇总；正式外部验证仍需柔性曲线及区间。
- 研究组 OOF 中，随机森林 CITL/斜率为 {value(metrics, 'study', 'Random forest', 'Calibration_in_the_large'):.3f}/{value(metrics, 'study', 'Random forest', 'Calibration_slope'):.3f}，TabPFN-3 为 {value(metrics, 'study', 'TabPFN-3', 'Calibration_in_the_large'):.3f}/{value(metrics, 'study', 'TabPFN-3', 'Calibration_slope'):.3f}。TabPFN 的总体概率水平更接近观测率，但斜率提示概率仍过于极端；随机森林则整体风险水平偏高且变化范围偏窄。

## ADA 数据特有的稳健性

- 已按 assay platform、assay sensitivity 是否报告、评估时长、样本量、疾病、给药途径和 biosimilar 状态生成描述性亚组性能表。
- 同时计算未加权研究层面误差和按 `n_ada_assessed` 加权的敏感性指标；后者不等同于患者级模型。
- 由于 FDA/EMA 明确指出 ADA 检出受灵敏度、drug tolerance、采样与治疗背景影响，这些亚组差异应优先解释为测量与可迁移性问题，不能直接解释为药物因果效应。
- 对实际 ADA >50% 的记录，两模型均明显低估：随机森林平均低估约 40.3 个百分点，TabPFN-3 约 36.4 个百分点。这是下一轮模型或特征改进应优先处理的误差区域。
- 开发集探索性阈值曲线中，随机森林 F1/平衡准确率在约 0.40 较高，TabPFN-3 在约 0.30 较高；这些阈值没有经过嵌套外层评价，不能锁定或回填到封存测试集。

## 下一决策

1. 当前仍不应在封存测试集重新调阈值或校准。
2. 若二分类结果用于实际行动，先由领域专家定义合理概率阈值和假阳性/假阴性代价，再实施嵌套校准与决策曲线。
3. 新数据应优先同时隔离研究来源和分子，并在收集前锁定模型；现有测试集仅 3 个完全未见分子，不能承担这一任务。
4. 外部验证样本量应围绕校准斜率、ROC-AUC 和目标净获益的置信区间精度计算。

本轮两套 OOF 训练与预测累计模型计时时间约 {total_runtime:.1f} 秒；全流程墙钟时间记录在 `work/validation_stage2/oof_metadata.json`。
"""
    REPORT.write_text(content, encoding="utf-8")


def main() -> None:
    predictions = pd.read_csv(ARTIFACTS / "oof_predictions.csv")
    runtime = pd.read_csv(ARTIFACTS / "oof_runtime.csv")
    fold_metrics = pd.read_csv(ARTIFACTS / "oof_fold_metrics.csv")
    readiness = pd.read_csv(ARTIFACTS / "subgroup_readiness.csv")
    partition_overlap = pd.read_csv(ARTIFACTS / "partition_overlap.csv")
    if len(predictions) != 2237 * 2:
        raise ValueError("Expected two complete 2,237-row OOF schemes")
    if predictions[["rf_regression", "tabpfn_regression", "rf_probability", "tabpfn_probability"]].isna().any().any():
        raise ValueError("OOF predictions contain missing values")

    metrics = overall_metrics(predictions)
    bins = calibration_bins(predictions)
    thresholds = threshold_table(predictions)
    bootstrap = paired_cluster_bootstrap(predictions)
    subgroup = subgroup_performance(predictions)
    errors = error_by_actual_band(predictions)

    metrics.to_csv(ARTIFACTS / "oof_overall_metrics.csv", index=False)
    bins.to_csv(ARTIFACTS / "oof_calibration_bins.csv", index=False)
    thresholds.to_csv(ARTIFACTS / "oof_threshold_sensitivity.csv", index=False)
    bootstrap.to_csv(ARTIFACTS / "oof_paired_bootstrap.csv", index=False)
    subgroup.to_csv(ARTIFACTS / "oof_subgroup_performance.csv", index=False)
    errors.to_csv(ARTIFACTS / "oof_error_by_actual_band.csv", index=False)
    save_figures(bins, thresholds, errors)
    write_report(metrics, bootstrap, runtime)

    summary = {
        "rows_per_scheme": 2237,
        "schemes": sorted(predictions["validation_scheme"].unique()),
        "overall_metric_rows": len(metrics),
        "bootstrap_repeats": BOOTSTRAP_REPEATS,
        "thresholds_per_model": int(thresholds.groupby("model").size().iloc[0]),
        "subgroup_rows": len(subgroup),
        "sealed_test_outcome_used": False,
    }
    (ARTIFACTS / "oof_postprocess_metadata.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    payload_frames = {
        "overall_metrics": metrics,
        "paired_bootstrap": bootstrap,
        "threshold_sensitivity": thresholds,
        "calibration_bins": bins,
        "subgroup_performance": subgroup,
        "error_by_actual_band": errors,
        "fold_metrics": fold_metrics,
        "runtime": runtime,
        "readiness": readiness,
        "partition_overlap": partition_overlap,
        "oof_predictions": predictions,
    }
    payload = {
        "summary": summary,
        **{
            key: json.loads(frame.to_json(orient="records"))
            for key, frame in payload_frames.items()
        },
    }
    (ARTIFACTS / "oof_workbook_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
