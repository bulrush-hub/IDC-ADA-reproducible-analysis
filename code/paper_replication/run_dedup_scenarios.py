from __future__ import annotations

import json
import math
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import run_replication as base


# Two levels above this file is the portable repository root.
ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "outputs" / "paper_replication_dedup_scenarios"
DATA_DIR = OUTPUT_DIR / "data"
RESULT_DIR = OUTPUT_DIR / "results"
FIGURE_DIR = OUTPUT_DIR / "figures"
ARTIFACT_DIR = OUTPUT_DIR / "artifacts"
PAPER_TABLE = ROOT / "config" / "paper_table_s6.csv"

MODEL_REQUIRED_COLUMNS = [
    "sequence_length_proxy",
    "dose_interval_days_proxy",
    "dose_level_proxy",
    "trial_year_completed",
    "disease_indication_group_proxy",
    "therapeutic_moa_type_proxy",
    "comedication_moa_type_proxy",
    "route_group_proxy",
]

FULL_FORMULA = "high_ada ~ " + " + ".join(term for _, term in base.TERM_ORDER)


def normalized_key(series: pd.Series, missing_label: str) -> pd.Series:
    return (
        series.fillna(missing_label)
        .astype(str)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        .replace("", missing_label)
        .str.casefold()
    )


def add_selection_fields(candidate: pd.DataFrame) -> pd.DataFrame:
    data = candidate.copy()
    data["molecule_key"] = normalized_key(
        data["Molecule Assessed for ADA INN Name"], "<missing molecule>"
    )
    data["disease_category_key"] = normalized_key(
        data["Disease Indication Category"], "<missing disease category>"
    )
    data["model_ready_proxy"] = data[MODEL_REQUIRED_COLUMNS].notna().all(axis=1)
    data["manually_audited_bool"] = (
        data["Manually Audited"]
        .astype(str)
        .str.strip()
        .str.casefold()
        .isin({"true", "1", "yes"})
    )
    data["selection_tier"] = np.select(
        [
            data["manually_audited_bool"] & data["model_ready_proxy"],
            data["model_ready_proxy"],
            data["manually_audited_bool"],
        ],
        [1, 2, 3],
        default=4,
    ).astype(int)
    tier_descriptions = {
        1: "audited and proxy-model complete",
        2: "proxy-model complete",
        3: "audited but proxy-model incomplete",
        4: "neither audited nor proxy-model complete",
    }
    data["selection_tier_description"] = data["selection_tier"].map(tier_descriptions)
    data["patient_count_for_ranking"] = pd.to_numeric(
        data["Number of Patients analyzed for ADA"], errors="coerce"
    ).fillna(-1.0)
    return data


def select_representative_rows(
    candidate: pd.DataFrame,
    group_columns: list[str],
    scenario_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = candidate.copy()
    group = data.groupby(group_columns, dropna=False, sort=True)
    data["group_source_rows"] = group["replication_row_key"].transform("size").astype(int)
    data["group_audited_rows"] = group["manually_audited_bool"].transform("sum").astype(int)
    data["group_model_ready_rows"] = group["model_ready_proxy"].transform("sum").astype(int)
    data["group_ada_median"] = group["ada_frequency_percent"].transform("median")
    data["group_ada_min"] = group["ada_frequency_percent"].transform("min")
    data["group_ada_max"] = group["ada_frequency_percent"].transform("max")
    data["ada_distance_from_group_median"] = (
        data["ada_frequency_percent"] - data["group_ada_median"]
    ).abs()

    sort_columns = [
        *group_columns,
        "selection_tier",
        "ada_distance_from_group_median",
        "patient_count_for_ranking",
        "source_excel_row",
    ]
    ascending = [True] * len(group_columns) + [True, True, False, True]
    ranked = data.sort_values(sort_columns, ascending=ascending, kind="stable")
    ranked["selection_rank_within_group"] = (
        ranked.groupby(group_columns, dropna=False, sort=False).cumcount() + 1
    )
    selected = ranked.loc[ranked["selection_rank_within_group"].eq(1)].copy()
    selected.insert(0, "scenario_id", scenario_id)

    audit = ranked[[
        *group_columns,
        "replication_row_key",
        "source_excel_row",
        "Molecule Assessed for ADA INN Name",
        "Disease Indication Category",
        "IDC Row identifier",
        "Trial ID",
        "ada_frequency_percent",
        "high_ada",
        "manually_audited_bool",
        "model_ready_proxy",
        "selection_tier",
        "selection_tier_description",
        "ada_distance_from_group_median",
        "patient_count_for_ranking",
        "selection_rank_within_group",
        "group_source_rows",
        "group_audited_rows",
        "group_model_ready_rows",
        "group_ada_median",
        "group_ada_min",
        "group_ada_max",
    ]].copy()
    audit.insert(0, "scenario_id", scenario_id)
    audit["selected"] = audit["selection_rank_within_group"].eq(1)
    return selected, audit


def export_columns(frame: pd.DataFrame, include_disease_key: bool) -> list[str]:
    columns = [
        "scenario_id",
        "molecule_key",
    ]
    if include_disease_key:
        columns.append("disease_category_key")
    columns.extend(
        [
            "Molecule Assessed for ADA INN Name",
            "Disease Indication Category",
            "Disease Indication Description",
            "replication_row_key",
            "source_excel_row",
            "IDC Row identifier",
            "Trial ID",
            "External Source Identifier",
            "Therapeutic Assessed for ADA ID",
            "Manually Audited",
            "manually_audited_bool",
            "model_ready_proxy",
            "selection_tier",
            "selection_tier_description",
            "group_source_rows",
            "group_audited_rows",
            "group_model_ready_rows",
            "group_ada_median",
            "group_ada_min",
            "group_ada_max",
            "ada_distance_from_group_median",
            "Number of Patients analyzed for ADA",
            "ada_frequency_percent",
            "high_ada",
            "therapeutic_moa_type_proxy",
            "disease_indication_group_proxy",
            "sequence_length_proxy",
            "dose_interval_days_proxy",
            "route_group_proxy",
            "comedication_moa_type_proxy",
            "dose_level_proxy",
            "trial_year_completed",
            "dose_unit_parsed",
            "dose_proxy_assumption",
            "interval_parse_rule",
        ]
    )
    return columns


def model_fit_summary(frame: pd.DataFrame, scenario_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    model = smf.glm(
        formula=FULL_FORMULA,
        data=frame,
        family=sm.families.Binomial(),
    ).fit(maxiter=300, disp=0)
    null_model = smf.glm(
        formula="high_ada ~ 1",
        data=frame,
        family=sm.families.Binomial(),
    ).fit(maxiter=300, disp=0)
    summary = pd.DataFrame(
        [
            {
                "scenario_id": scenario_id,
                "n_complete": int(len(frame)),
                "high_ada_rows": int(frame["high_ada"].sum()),
                "high_ada_percent": float(frame["high_ada"].mean()),
                "parameters": int(len(model.params)),
                "null_deviance": float(null_model.deviance),
                "residual_deviance": float(model.deviance),
                "deviance_explained": float(null_model.deviance - model.deviance),
                "mcfadden_pseudo_r2": float(1 - model.llf / null_model.llf),
                "aic": float(model.aic),
                "formula": FULL_FORMULA,
                "interpretation": "In-sample proxy GLM fit; not cross-validated performance and not exact paper replication.",
            }
        ]
    )
    confidence = model.conf_int(alpha=0.05)
    coefficient_rows = []
    for term in model.params.index:
        estimate = float(model.params[term])
        low = float(confidence.loc[term, 0])
        high = float(confidence.loc[term, 1])
        coefficient_rows.append(
            {
                "scenario_id": scenario_id,
                "term": term,
                "coefficient": estimate,
                "standard_error": float(model.bse[term]),
                "z_value": float(model.tvalues[term]),
                "p_value": float(model.pvalues[term]),
                "odds_ratio": float(np.exp(np.clip(estimate, -30, 30))),
                "odds_ratio_ci_low": float(np.exp(np.clip(low, -30, 30))),
                "odds_ratio_ci_high": float(np.exp(np.clip(high, -30, 30))),
                "odds_ratio_was_clipped": bool(
                    abs(estimate) > 30 or abs(low) > 30 or abs(high) > 30
                ),
                "n_complete": int(len(frame)),
            }
        )
    return summary, pd.DataFrame(coefficient_rows)


def scenario_summary(
    candidate: pd.DataFrame,
    selected: pd.DataFrame,
    model_frame: pd.DataFrame,
    scenario_id: str,
    group_definition: str,
) -> dict[str, object]:
    return {
        "scenario_id": scenario_id,
        "group_definition": group_definition,
        "source_candidate_rows": int(len(candidate)),
        "selected_rows": int(len(selected)),
        "rows_removed": int(len(candidate) - len(selected)),
        "rows_removed_percent": float(1 - len(selected) / len(candidate)),
        "unique_molecules": int(selected["molecule_key"].nunique()),
        "unique_molecule_disease_groups": int(
            selected.groupby(["molecule_key", "disease_category_key"], dropna=False).ngroups
        ),
        "selected_audited_rows": int(selected["manually_audited_bool"].sum()),
        "selected_proxy_model_ready_rows": int(selected["model_ready_proxy"].sum()),
        "proxy_model_complete_cases": int(len(model_frame)),
        "high_ada_selected_rows": int(selected["high_ada"].sum()),
        "high_ada_selected_percent": float(selected["high_ada"].mean()),
        "selection_rule": "tier: audited+complete > complete > audited > other; then ADA nearest group median > larger ADA patient count > lower source row",
    }


def comparison_table(
    paper: pd.DataFrame,
    baseline: pd.DataFrame,
    molecule: pd.DataFrame,
    molecule_disease: pd.DataFrame,
) -> pd.DataFrame:
    result = paper[["display_rank", "model_order", "variable", "deviance", "p_value"]].rename(
        columns={"deviance": "published_deviance", "p_value": "published_p_value"}
    )
    for label, frame in [
        ("all_public_rows", baseline),
        ("one_per_molecule", molecule),
        ("one_per_molecule_disease_category", molecule_disease),
    ]:
        subset = frame[["variable", "deviance", "p_value", "n_complete"]].rename(
            columns={
                "deviance": f"{label}_deviance",
                "p_value": f"{label}_p_value",
                "n_complete": f"{label}_n_complete",
            }
        )
        result = result.merge(subset, on="variable", how="left", validate="one_to_one")
    return result


def dataframe_to_markdown(frame: pd.DataFrame, digits: int = 6) -> str:
    def render(value: object) -> str:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return ""
        if isinstance(value, (float, np.floating)):
            return f"{float(value):.{digits}g}"
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = [
        "| " + " | ".join(map(str, frame.columns)) + " |",
        "| " + " | ".join(["---"] * len(frame.columns)) + " |",
    ]
    lines.extend(
        "| " + " | ".join(render(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    )
    return "\n".join(lines)


def make_figure(comparison: pd.DataFrame, target: Path) -> None:
    labels = comparison["variable"].tolist()
    y = np.arange(len(labels))
    series = [
        ("Published Table S6", "published_deviance", "#17365D"),
        ("All public rows", "all_public_rows_deviance", "#6B7280"),
        ("One row per molecule", "one_per_molecule_deviance", "#D97706"),
        (
            "One row per molecule × disease category",
            "one_per_molecule_disease_category_deviance",
            "#0F766E",
        ),
    ]
    fig, ax = plt.subplots(figsize=(12, 8))
    height = 0.19
    offsets = [-1.5 * height, -0.5 * height, 0.5 * height, 1.5 * height]
    for offset, (name, column, color) in zip(offsets, series, strict=True):
        ax.barh(y + offset, comparison[column], height=height, color=color, label=name)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlabel("Sequential reduction in model deviance")
    ax.set_title("IDC deduplication-scenario comparison")
    ax.grid(axis="x", alpha=0.25)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.legend(frameon=False, loc="lower right")
    fig.text(
        0.01,
        0.01,
        "Deduplicated scenarios use deterministic representative source rows and public proxy variables; they are sensitivity analyses, not exact paper replications.",
        fontsize=8.5,
        color="#6B7280",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(target, dpi=300, bbox_inches="tight")
    plt.close(fig)


def json_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return frame.replace({np.nan: None}).to_dict(orient="records")


def main() -> int:
    for directory in [OUTPUT_DIR, DATA_DIR, RESULT_DIR, FIGURE_DIR, ARTIFACT_DIR]:
        directory.mkdir(parents=True, exist_ok=True)

    clinical = base.load_records("clinical_trial")
    therapeutic = base.load_records("therapeutic")
    sequence = base.load_records("sequence")
    candidate = add_selection_fields(
        base.prepare_public_candidate(clinical, therapeutic, sequence)
    )

    molecule_selected, molecule_audit = select_representative_rows(
        candidate,
        ["molecule_key"],
        "one_row_per_molecule",
    )
    molecule_disease_selected, molecule_disease_audit = select_representative_rows(
        candidate,
        ["molecule_key", "disease_category_key"],
        "one_row_per_molecule_disease_category",
    )

    molecule_columns = export_columns(molecule_selected, include_disease_key=False)
    molecule_disease_columns = export_columns(
        molecule_disease_selected, include_disease_key=True
    )
    molecule_table = molecule_selected[molecule_columns].sort_values("molecule_key")
    molecule_disease_table = molecule_disease_selected[molecule_disease_columns].sort_values(
        ["molecule_key", "disease_category_key"]
    )

    if not molecule_table["molecule_key"].is_unique:
        raise AssertionError("Scenario 1 does not have exactly one row per molecule.")
    if molecule_disease_table.duplicated(
        ["molecule_key", "disease_category_key"]
    ).any():
        raise AssertionError(
            "Scenario 2 does not have exactly one row per molecule and disease category."
        )

    molecule_model = base.modeling_frame_from_proxy(molecule_selected)
    molecule_disease_model = base.modeling_frame_from_proxy(molecule_disease_selected)
    baseline_model = base.modeling_frame_from_proxy(candidate)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        baseline_deviance = base.sequential_deviance(
            baseline_model, "all_public_rows_reference"
        )
        molecule_deviance = base.sequential_deviance(
            molecule_model, "one_row_per_molecule"
        )
        molecule_disease_deviance = base.sequential_deviance(
            molecule_disease_model, "one_row_per_molecule_disease_category"
        )
        molecule_order_summary, molecule_order_runs = base.order_sensitivity(molecule_model)
        molecule_disease_order_summary, molecule_disease_order_runs = base.order_sensitivity(
            molecule_disease_model
        )
        molecule_drop_one = base.drop_one_likelihood_ratio(molecule_model)
        molecule_disease_drop_one = base.drop_one_likelihood_ratio(molecule_disease_model)
        baseline_fit, baseline_coefficients = model_fit_summary(
            baseline_model, "all_public_rows_reference"
        )
        molecule_fit, molecule_coefficients = model_fit_summary(
            molecule_model, "one_row_per_molecule"
        )
        molecule_disease_fit, molecule_disease_coefficients = model_fit_summary(
            molecule_disease_model, "one_row_per_molecule_disease_category"
        )

    paper = pd.read_csv(PAPER_TABLE)
    comparison = comparison_table(
        paper,
        baseline_deviance,
        molecule_deviance,
        molecule_disease_deviance,
    )
    summaries = pd.DataFrame(
        [
            scenario_summary(
                candidate,
                molecule_selected,
                molecule_model,
                "one_row_per_molecule",
                "normalized Molecule Assessed for ADA INN Name",
            ),
            scenario_summary(
                candidate,
                molecule_disease_selected,
                molecule_disease_model,
                "one_row_per_molecule_disease_category",
                "normalized molecule + raw Disease Indication Category",
            ),
        ]
    )
    fit_summary = pd.concat(
        [baseline_fit, molecule_fit, molecule_disease_fit], ignore_index=True
    )
    outcome_summary = pd.concat(
        [
            base.outcome_balance(molecule_selected, molecule_model).assign(
                scenario_id="one_row_per_molecule"
            ),
            base.outcome_balance(molecule_disease_selected, molecule_disease_model).assign(
                scenario_id="one_row_per_molecule_disease_category"
            ),
        ],
        ignore_index=True,
    )

    molecule_table.to_csv(DATA_DIR / "one_row_per_molecule.csv", index=False)
    molecule_disease_table.to_csv(
        DATA_DIR / "one_row_per_molecule_disease_category.csv", index=False
    )
    molecule_audit.to_csv(ARTIFACT_DIR / "selection_audit_molecule.csv", index=False)
    molecule_disease_audit.to_csv(
        ARTIFACT_DIR / "selection_audit_molecule_disease_category.csv", index=False
    )
    summaries.to_csv(RESULT_DIR / "scenario_summary.csv", index=False)
    comparison.to_csv(RESULT_DIR / "sequential_deviance_comparison.csv", index=False)
    molecule_deviance.to_csv(RESULT_DIR / "deviance_one_per_molecule.csv", index=False)
    molecule_disease_deviance.to_csv(
        RESULT_DIR / "deviance_one_per_molecule_disease_category.csv", index=False
    )
    fit_summary.to_csv(RESULT_DIR / "fit_summary.csv", index=False)
    molecule_coefficients.to_csv(RESULT_DIR / "coefficients_one_per_molecule.csv", index=False)
    molecule_disease_coefficients.to_csv(
        RESULT_DIR / "coefficients_one_per_molecule_disease_category.csv", index=False
    )
    molecule_order_summary.to_csv(
        RESULT_DIR / "order_sensitivity_one_per_molecule.csv", index=False
    )
    molecule_disease_order_summary.to_csv(
        RESULT_DIR / "order_sensitivity_one_per_molecule_disease_category.csv", index=False
    )
    molecule_order_runs.to_csv(
        ARTIFACT_DIR / "order_scenarios_one_per_molecule.csv", index=False
    )
    molecule_disease_order_runs.to_csv(
        ARTIFACT_DIR / "order_scenarios_one_per_molecule_disease_category.csv", index=False
    )
    molecule_drop_one.to_csv(RESULT_DIR / "drop_one_one_per_molecule.csv", index=False)
    molecule_disease_drop_one.to_csv(
        RESULT_DIR / "drop_one_one_per_molecule_disease_category.csv", index=False
    )
    outcome_summary.to_csv(RESULT_DIR / "outcome_balance.csv", index=False)

    make_figure(comparison, FIGURE_DIR / "dedup_deviance_comparison.png")

    rules = pd.DataFrame(
        [
            {
                "priority": 1,
                "rule": "Group key",
                "scenario_1": "normalized molecule INN name",
                "scenario_2": "normalized molecule INN name + raw Disease Indication Category",
                "purpose": "Defines exactly one retained source row per requested group.",
            },
            {
                "priority": 2,
                "rule": "Selection tier 1",
                "scenario_1": "manually audited and proxy-model complete",
                "scenario_2": "same",
                "purpose": "Preserve reviewed records that can enter the eight-factor proxy model.",
            },
            {
                "priority": 3,
                "rule": "Selection tier 2",
                "scenario_1": "proxy-model complete",
                "scenario_2": "same",
                "purpose": "Retain model usability when no audited complete record exists.",
            },
            {
                "priority": 4,
                "rule": "Selection tier 3/4",
                "scenario_1": "audited incomplete, then other",
                "scenario_2": "same",
                "purpose": "Still retain one source row even when a group cannot enter modeling.",
            },
            {
                "priority": 5,
                "rule": "Within-tier ranking",
                "scenario_1": "ADA nearest group median; larger ADA patient N; lower source row",
                "scenario_2": "same within molecule-disease group",
                "purpose": "Avoid arbitrary first-row selection and make ties deterministic.",
            },
        ]
    )

    metadata = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "output_directory": str(OUTPUT_DIR),
        "original_results_untouched": True,
        "source_candidate_rows": int(len(candidate)),
        "scenario_1_rows": int(len(molecule_table)),
        "scenario_1_model_n": int(len(molecule_model)),
        "scenario_2_rows": int(len(molecule_disease_table)),
        "scenario_2_model_n": int(len(molecule_disease_model)),
        "baseline_model_n": int(len(baseline_model)),
        "selection_rule_version": "dedup_representative_v1",
        "source_all_tables": "data/raw/User_IDC_DB_V1_All_Tables.xlsx",
    }
    (ARTIFACT_DIR / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    payload = {
        "metadata": metadata,
        "tables": {
            "Scenario_Summary": json_records(summaries),
            "Selection_Rules": json_records(rules),
            "Data_Molecule": json_records(molecule_table),
            "Data_Molecule_Disease": json_records(molecule_disease_table),
            "S6_Comparison": json_records(comparison),
            "Deviance_Molecule": json_records(molecule_deviance),
            "Deviance_Molecule_Disease": json_records(molecule_disease_deviance),
            "Fit_Summary": json_records(fit_summary),
            "Coefficients_Molecule": json_records(molecule_coefficients),
            "Coefficients_Molecule_Disease": json_records(molecule_disease_coefficients),
            "Order_Sensitivity_Molecule": json_records(molecule_order_summary),
            "Order_Sensitivity_Molecule_Disease": json_records(
                molecule_disease_order_summary
            ),
            "Drop_One_Molecule": json_records(molecule_drop_one),
            "Drop_One_Molecule_Disease": json_records(molecule_disease_drop_one),
            "Outcome_Balance": json_records(outcome_summary),
        },
    }
    (ARTIFACT_DIR / "workbook_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report = f"""# IDC 两种去重场景分析报告

生成时间：{metadata['generated_utc']}

## 结论范围

本分析创建两个独立清洗场景，不修改、不覆盖 `outputs/paper_replication/` 原始结果。每个组保留一条真实来源记录，不合成跨试验字段。

## 场景摘要

{dataframe_to_markdown(summaries)}

## 顺序 deviance 对照

{dataframe_to_markdown(comparison)}

## 模型拟合摘要

{dataframe_to_markdown(fit_summary)}

## 解释限制

- 场景 1 将同一药物的所有临床试验、适应证和给药方案压缩为一条代表记录；样本量从 2,666 条候选记录降为 {len(molecule_table)} 条，完整模型仅 {len(molecule_model)} 条。
- 场景 2 保留每个药物在每个原始 `Disease Indication Category` 中的一条代表记录，共 {len(molecule_disease_table)} 条，完整模型 {len(molecule_disease_model)} 条。
- 两个结果回答的是“不同去重口径下代理模型如何变化”，不是论文 Figure 6 的精确复现，也不是独立外部验证。
- 由于完整模型样本量小且参数较多，系数、p 值和优势比可能不稳定；应重点查看方向、量级和两场景一致性，不宜只按 0.05 阈值下结论。
"""
    (OUTPUT_DIR / "IDC_dedup_scenarios_report.md").write_text(report, encoding="utf-8")

    log = f"""# IDC 去重场景工作日志

## {metadata['generated_utc']} — 新建独立结果分支

1. 读取用户确认的 IDC DB V1 原始 all-tables 数据，不修改原始工作簿。
2. 复用现有公开数据清洗和代理变量规则，候选集为 Therapeutic Exposed 且 ADA frequency 非缺失的 {len(candidate):,} 行。
3. 场景 1 按标准化药物 INN 名称分组，每种药物保留一条真实来源记录。
4. 场景 2 按标准化药物 INN 名称与原始 `Disease Indication Category` 分组，每个药物-疾病大类保留一条真实来源记录。
5. 代表行选择优先级为：人工审核且字段完整 > 字段完整 > 人工审核 > 其他；同层级按 ADA 最接近组内中位数、患者数较大、来源行号较小排序。
6. 验证场景 1 分组键唯一，输出 {len(molecule_table):,} 行；场景 2 组合键唯一，输出 {len(molecule_disease_table):,} 行。
7. 在两个场景上分别运行与 paper_replication 相同的八因素顺序 logistic GLM、drop-one LRT 和顺序敏感性分析。
8. 所有文件写入 `outputs/paper_replication_dedup_scenarios/`；原始 `outputs/paper_replication/` 未写入。
9. Python 依赖仅使用项目 `.venv`，未修改系统或全局 Python。
"""
    (OUTPUT_DIR / "IDC_dedup_scenarios_work_log.md").write_text(log, encoding="utf-8")

    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
