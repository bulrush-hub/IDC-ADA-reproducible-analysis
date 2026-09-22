"""Post-process the completed IDC TabPFN run into audit-ready deliverables."""

from __future__ import annotations

import json
from pathlib import Path

import nbformat as nbf
import numpy as np
import pandas as pd
from nbclient import NotebookClient
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


# The release stores scripts in code/modeling; repository data and outputs are
# located two directory levels above this file.
ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "outputs"
ARTIFACTS = ROOT / "work" / "tabpfn_artifacts"
BASELINE_ARTIFACTS = ROOT / "work" / "modeling_artifacts"
SEED = 20260802
BOOTSTRAP_REPEATS = 2000
PIPELINE_WALL_SECONDS = 1238.5


def selected_baseline_rows() -> tuple[pd.Series, pd.Series]:
    performance = pd.read_csv(BASELINE_ARTIFACTS / "performance.csv")
    selected = performance["selected"].astype(str).str.lower().eq("true")
    reg = performance.loc[performance["outcome"].eq("continuous") & selected].iloc[0]
    cls = performance.loc[performance["outcome"].eq("binary") & selected].iloc[0]
    return reg, cls


def build_cv_comparison() -> pd.DataFrame:
    current_reg, current_cls = selected_baseline_rows()
    tab = pd.read_csv(ARTIFACTS / "tabpfn_cv_summary.csv")
    tab_map = {
        (row.outcome, row.metric): (row.mean, row.sd)
        for row in tab.itertuples(index=False)
    }
    definitions = [
        ("continuous", "MAE", "cv_MAE_mean", "cv_MAE_sd", False),
        ("continuous", "RMSE", "cv_RMSE_mean", "cv_RMSE_sd", False),
        ("continuous", "R2", "cv_R2_mean", "cv_R2_sd", True),
        ("binary", "ROC_AUC", "cv_ROC_AUC_mean", "cv_ROC_AUC_sd", True),
        ("binary", "PR_AUC", "cv_PR_AUC_mean", "cv_PR_AUC_sd", True),
        ("binary", "F1", "cv_F1_mean", "cv_F1_sd", True),
        (
            "binary",
            "Balanced_Accuracy",
            "cv_Balanced_Accuracy_mean",
            "cv_Balanced_Accuracy_sd",
            True,
        ),
        ("binary", "Brier", "cv_Brier_mean", "cv_Brier_sd", False),
    ]
    rows = []
    for outcome, metric, mean_col, sd_col, higher in definitions:
        baseline = current_reg if outcome == "continuous" else current_cls
        current_mean = float(baseline[mean_col])
        current_sd = float(baseline[sd_col])
        tab_mean, tab_sd = tab_map[(outcome, metric)]
        improvement = tab_mean - current_mean if higher else current_mean - tab_mean
        rows.append(
            {
                "outcome": outcome,
                "metric": metric,
                "higher_is_better": higher,
                "current_model": baseline["model"],
                "current_cv_mean": current_mean,
                "current_cv_sd": current_sd,
                "tabpfn_model": "TabPFN-3",
                "tabpfn_cv_mean": float(tab_mean),
                "tabpfn_cv_sd": float(tab_sd),
                "tabpfn_improvement": float(improvement),
                "winner_by_mean": "TabPFN" if improvement > 0 else str(baseline["model"]),
            }
        )
    result = pd.DataFrame(rows)
    result.to_csv(ARTIFACTS / "tabpfn_cv_comparison.csv", index=False)
    return result


def metric_values(data: pd.DataFrame) -> dict[tuple[str, str], tuple[float, float]]:
    y_reg = data["ada_frequency_percent_actual_current"].to_numpy(float)
    current_reg = data["ada_frequency_percent_predicted"].to_numpy(float)
    tab_reg = data["tabpfn_regression_raw"].to_numpy(float)
    y_cls = data["ada_high_10_actual_current"].to_numpy(int)
    current_prob = data["ada_high_10_probability"].to_numpy(float)
    tab_prob = data["tabpfn_probability_ada_high_10"].to_numpy(float)
    current_label = (current_prob >= 0.5).astype(int)
    tab_label = (tab_prob >= 0.5).astype(int)
    return {
        ("continuous", "MAE"): (
            mean_absolute_error(y_reg, current_reg),
            mean_absolute_error(y_reg, tab_reg),
        ),
        ("continuous", "RMSE"): (
            mean_squared_error(y_reg, current_reg) ** 0.5,
            mean_squared_error(y_reg, tab_reg) ** 0.5,
        ),
        ("continuous", "R2"): (
            r2_score(y_reg, current_reg),
            r2_score(y_reg, tab_reg),
        ),
        ("binary", "ROC_AUC"): (
            roc_auc_score(y_cls, current_prob),
            roc_auc_score(y_cls, tab_prob),
        ),
        ("binary", "PR_AUC"): (
            average_precision_score(y_cls, current_prob),
            average_precision_score(y_cls, tab_prob),
        ),
        ("binary", "F1"): (
            f1_score(y_cls, current_label, zero_division=0),
            f1_score(y_cls, tab_label, zero_division=0),
        ),
        ("binary", "Balanced_Accuracy"): (
            balanced_accuracy_score(y_cls, current_label),
            balanced_accuracy_score(y_cls, tab_label),
        ),
        ("binary", "Brier"): (
            brier_score_loss(y_cls, current_prob),
            brier_score_loss(y_cls, tab_prob),
        ),
        ("binary", "Log_Loss"): (
            log_loss(y_cls, np.clip(current_prob, 1e-15, 1 - 1e-15), labels=[0, 1]),
            log_loss(y_cls, np.clip(tab_prob, 1e-15, 1 - 1e-15), labels=[0, 1]),
        ),
    }


def build_paired_bootstrap() -> pd.DataFrame:
    current = pd.read_csv(BASELINE_ARTIFACTS / "predictions.csv")
    tab = pd.read_csv(ARTIFACTS / "tabpfn_predictions.csv")
    merged = current.merge(tab, on="idc_row_id", suffixes=("_current", "_tab"), validate="one_to_one")
    if len(merged) != 374:
        raise ValueError("Prediction merge did not preserve all 374 test rows")
    if not np.allclose(
        merged["ada_frequency_percent_actual_current"],
        merged["ada_frequency_percent_actual_tab"],
    ):
        raise ValueError("Continuous actual outcomes do not match")
    if not np.array_equal(
        merged["ada_high_10_actual_current"].to_numpy(int),
        merged["ada_high_10_actual_tab"].to_numpy(int),
    ):
        raise ValueError("Binary actual outcomes do not match")

    definitions = {
        ("continuous", "MAE"): False,
        ("continuous", "RMSE"): False,
        ("continuous", "R2"): True,
        ("binary", "ROC_AUC"): True,
        ("binary", "PR_AUC"): True,
        ("binary", "F1"): True,
        ("binary", "Balanced_Accuracy"): True,
        ("binary", "Brier"): False,
        ("binary", "Log_Loss"): False,
    }
    point = metric_values(merged)
    groups = merged["model_split_group_current"].astype(str).unique()
    by_group = {
        group: merged.loc[merged["model_split_group_current"].astype(str).eq(group)]
        for group in groups
    }
    rng = np.random.default_rng(SEED + 77)
    boot = {key: [] for key in definitions}
    for _ in range(BOOTSTRAP_REPEATS):
        sampled = rng.choice(groups, size=len(groups), replace=True)
        sample = pd.concat([by_group[group] for group in sampled], ignore_index=True)
        try:
            values = metric_values(sample)
        except ValueError:
            continue
        for key, higher in definitions.items():
            current_value, tab_value = values[key]
            improvement = tab_value - current_value if higher else current_value - tab_value
            boot[key].append(float(improvement))

    rows = []
    for key, higher in definitions.items():
        current_value, tab_value = point[key]
        point_improvement = tab_value - current_value if higher else current_value - tab_value
        distribution = np.asarray(boot[key], dtype=float)
        ci_low, ci_high = np.quantile(distribution, [0.025, 0.975])
        if ci_low > 0:
            conclusion = "TabPFN improvement supported"
        elif ci_high < 0:
            conclusion = "Current model advantage supported"
        else:
            conclusion = "Difference uncertain"
        rows.append(
            {
                "outcome": key[0],
                "metric": key[1],
                "higher_is_better": higher,
                "current_value": float(current_value),
                "tabpfn_value": float(tab_value),
                "tabpfn_improvement": float(point_improvement),
                "improvement_ci_2_5": float(ci_low),
                "improvement_ci_97_5": float(ci_high),
                "bootstrap_probability_tabpfn_better": float(np.mean(distribution > 0)),
                "bootstrap_repeats_valid": int(len(distribution)),
                "resampling_unit": "model_split_group",
                "conclusion": conclusion,
            }
        )
    result = pd.DataFrame(rows)
    result.to_csv(ARTIFACTS / "tabpfn_paired_bootstrap.csv", index=False)
    return result


def dataframe_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    cleaned = frame.astype(object).where(pd.notna(frame), None)
    return cleaned.to_dict(orient="records")


def write_payload(cv_comparison: pd.DataFrame, bootstrap: pd.DataFrame) -> None:
    metadata = json.loads((ARTIFACTS / "tabpfn_metadata.json").read_text(encoding="utf-8"))
    metadata["full_pipeline_wall_seconds"] = PIPELINE_WALL_SECONDS
    metadata["bootstrap_repeats"] = BOOTSTRAP_REPEATS
    (ARTIFACTS / "tabpfn_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    payload = {
        "metadata": metadata,
        "test_comparison": dataframe_records(pd.read_csv(ARTIFACTS / "tabpfn_comparison.csv")),
        "cv_comparison": dataframe_records(cv_comparison),
        "cv_folds": dataframe_records(pd.read_csv(ARTIFACTS / "tabpfn_cv_folds.csv")),
        "feature_importance": dataframe_records(pd.read_csv(ARTIFACTS / "tabpfn_feature_importance.csv")),
        "predictions": dataframe_records(pd.read_csv(ARTIFACTS / "tabpfn_predictions.csv")),
        "runtime": dataframe_records(pd.read_csv(ARTIFACTS / "tabpfn_runtime.csv")),
        "bootstrap": dataframe_records(bootstrap),
    }
    (ARTIFACTS / "tabpfn_workbook_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def write_report(cv_comparison: pd.DataFrame, bootstrap: pd.DataFrame) -> None:
    test = pd.read_csv(ARTIFACTS / "tabpfn_comparison.csv")
    cv_rows = []
    for row in cv_comparison.itertuples(index=False):
        cv_rows.append(
            f"| {row.outcome} | {row.metric} | {row.current_cv_mean:.4f} ± {row.current_cv_sd:.4f} | "
            f"{row.tabpfn_cv_mean:.4f} ± {row.tabpfn_cv_sd:.4f} | {row.winner_by_mean} |"
        )
    test_rows = []
    for row in test.itertuples(index=False):
        test_rows.append(
            f"| {row.outcome} | {row.metric} | {row.current_value:.4f} | "
            f"{row.tabpfn_value:.4f} | {row.winner} |"
        )
    boot_rows = []
    for row in bootstrap.itertuples(index=False):
        boot_rows.append(
            f"| {row.outcome} | {row.metric} | {row.tabpfn_improvement:.4f} | "
            f"[{row.improvement_ci_2_5:.4f}, {row.improvement_ci_97_5:.4f}] | {row.conclusion} |"
        )
    report = f"""# IDC TabPFN-3 与当前模型性能比较

## 结论摘要

TabPFN-3 在封存测试集上显著改善连续 ADA 频率预测：MAE 从 10.585 降至 7.601 个百分点，R² 从 0.461 提高到 0.617。二分类的 ROC-AUC、PR-AUC、Brier 和 Log Loss 也优于当前随机森林；但使用未经调优的固定 0.5 阈值时，F1 与平衡准确率略低。

开发集 5 折分组交叉验证的优势没有测试集那么一致：TabPFN 连续 MAE 更低，但连续 R²、二分类 ROC-AUC 等若干指标与随机森林接近或略差。因此应把 TabPFN 视为值得保留的候选模型，而不是仅凭一次测试集全面替换当前模型。

## 独立测试集

| 结局 | 指标 | 当前随机森林 | TabPFN-3 | 点估计更优者 |
|---|---|---:|---:|---|
{chr(10).join(test_rows)}

## 开发集 5 折 GroupKFold

| 结局 | 指标 | 当前随机森林 | TabPFN-3 | 均值更优者 |
|---|---|---:|---:|---|
{chr(10).join(cv_rows)}

## 按研究组配对 bootstrap

`TabPFN improvement` 已统一指标方向：正值表示 TabPFN 更好。重采样单位为 `model_split_group`，重复 {BOOTSTRAP_REPEATS} 次。

| 结局 | 指标 | TabPFN improvement | 95% CI | 判断 |
|---|---|---:|---:|---|
{chr(10).join(boot_rows)}

## 方法与限制

- 比较使用相同 29 个特征、相同研究组拆分和相同 374 行封存测试集。
- TabPFN 使用官方推荐的原生类别处理，不做 one-hot 或缩放；随机森林保留既有预处理。
- 二分类 F1 与平衡准确率按固定 0.5 阈值计算，没有在测试集调阈值。
- Feature importance 为测试集置换重要性，只表示预测贡献，不表示因果关系。
- 本次环境为 CPU 版 PyTorch；完整流水线约 {PIPELINE_WALL_SECONDS / 60:.1f} 分钟。速度不能代表 GPU 部署性能。
- TabPFN-3 权重和输出受非商业许可约束；生产或商业使用需另行确认授权。
- 测试集仍属于当前数据库的内部独立拆分，不能替代外部验证；对全新分子的外推风险仍需单独评估。
"""
    (OUTPUTS / "IDC_TabPFN_comparison_report.md").write_text(report, encoding="utf-8")


def write_executed_notebook() -> None:
    notebook = nbf.v4.new_notebook()
    notebook.metadata.kernelspec = {
        "display_name": "Python 3 (IDC TabPFN)",
        "language": "python",
        "name": "python3",
    }
    notebook.cells = [
        nbf.v4.new_markdown_cell(
            "# IDC TabPFN-3 performance comparison\n\n"
            "This executed notebook reads the locked analysis artifacts. It does not refit models or alter the sealed test set."
        ),
        nbf.v4.new_code_cell(
            "from pathlib import Path\n"
            "import json, pandas as pd, numpy as np, tabpfn, torch\n"
            "from IPython.display import display, Image\n"
            "ROOT = Path.cwd()\n"
            "ART = ROOT / 'work' / 'tabpfn_artifacts'\n"
            "assert tabpfn.__version__ == '8.2.0'\n"
            "metadata = json.loads((ART/'tabpfn_metadata.json').read_text(encoding='utf-8'))\n"
            "display(pd.Series(metadata, name='value').to_frame())"
        ),
        nbf.v4.new_markdown_cell("## Independent test-set comparison"),
        nbf.v4.new_code_cell(
            "test = pd.read_csv(ART/'tabpfn_comparison.csv')\n"
            "display(test)\n"
            "display(Image(filename=str(ROOT/'outputs'/'modeling_figures'/'tabpfn_performance_comparison.png')))"
        ),
        nbf.v4.new_markdown_cell("## Development-set 5-fold grouped cross-validation"),
        nbf.v4.new_code_cell(
            "cv = pd.read_csv(ART/'tabpfn_cv_comparison.csv')\n"
            "display(cv)"
        ),
        nbf.v4.new_markdown_cell("## Paired cluster bootstrap on the sealed test set"),
        nbf.v4.new_code_cell(
            "boot = pd.read_csv(ART/'tabpfn_paired_bootstrap.csv')\n"
            "display(boot)"
        ),
        nbf.v4.new_markdown_cell("## TabPFN permutation importance"),
        nbf.v4.new_code_cell(
            "importance = pd.read_csv(ART/'tabpfn_feature_importance.csv')\n"
            "for outcome in ['continuous','binary']:\n"
            "    print(outcome)\n"
            "    display(importance.query('outcome == @outcome').nlargest(10, 'importance_mean'))"
        ),
        nbf.v4.new_markdown_cell("## Prediction integrity checks"),
        nbf.v4.new_code_cell(
            "pred = pd.read_csv(ART/'tabpfn_predictions.csv')\n"
            "checks = {\n"
            " 'rows': len(pred),\n"
            " 'unique_idc_row_id': pred.idc_row_id.is_unique,\n"
            " 'finite_regression': np.isfinite(pred.tabpfn_regression_raw).all(),\n"
            " 'finite_probability': np.isfinite(pred.tabpfn_probability_ada_high_10).all(),\n"
            " 'regression_min': pred.tabpfn_regression_raw.min(),\n"
            " 'regression_max': pred.tabpfn_regression_raw.max(),\n"
            " 'probability_min': pred.tabpfn_probability_ada_high_10.min(),\n"
            " 'probability_max': pred.tabpfn_probability_ada_high_10.max(),\n"
            "}\n"
            "display(pd.Series(checks, name='value').to_frame())\n"
            "assert checks['rows'] == 374 and checks['unique_idc_row_id']\n"
            "assert checks['finite_regression'] and checks['finite_probability']"
        ),
        nbf.v4.new_markdown_cell(
            "## Interpretation\n\n"
            "TabPFN-3 is the stronger test-set model for continuous prediction and probability ranking/calibration. "
            "Its cross-validation advantage is less consistent, and fixed-threshold F1/balanced accuracy do not improve. "
            "Retain both models until external or molecule-level validation confirms the replacement decision."
        ),
    ]
    client = NotebookClient(
        notebook,
        timeout=180,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    )
    client.execute()
    nbf.write(notebook, OUTPUTS / "IDC_TabPFN_comparison.ipynb")


def main() -> None:
    cv_comparison = build_cv_comparison()
    bootstrap = build_paired_bootstrap()
    write_payload(cv_comparison, bootstrap)
    write_report(cv_comparison, bootstrap)
    write_executed_notebook()
    print(bootstrap.to_string(index=False))


if __name__ == "__main__":
    main()
