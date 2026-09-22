r"""Audit IDC validation readiness without fitting or selecting a model.

Run only with a project-local environment:

    .\.venv-tabpfn\Scripts\python.exe outputs\IDC_validation_readiness.py

The script may inspect partition identifiers across the full dataset, but all
subgroup readiness summaries are calculated on train+validation only. Test
outcomes are never used.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd


# The release stores scripts in code/modeling; repository data and outputs are
# located two directory levels above this file.
ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "outputs" / "IDC_modeling_table_final_model_ready.xlsx"
SPLIT = ROOT / "work" / "modeling_artifacts" / "split_audit.csv"
ARTIFACTS = ROOT / "work" / "validation_stage2"
REPORT = ROOT / "outputs" / "IDC_validation_readiness_report.md"
ARTIFACTS.mkdir(parents=True, exist_ok=True)


class DisjointSet:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        self.parent.setdefault(item, item)
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def component_labels(frame: pd.DataFrame) -> pd.Series:
    dsu = DisjointSet()
    for row in frame[["model_split_group", "molecule_inn_name"]].itertuples(index=False):
        dsu.union(f"study::{row.model_split_group}", f"molecule::{row.molecule_inn_name}")
    roots = {
        root: index + 1
        for index, root in enumerate(
            sorted({dsu.find(f"study::{value}") for value in frame["model_split_group"]})
        )
    }
    return frame["model_split_group"].map(
        lambda value: f"component_{roots[dsu.find(f'study::{value}')]:04d}"
    )


def pairwise_overlap(values: dict[str, set[str]], dimension: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    pairs = [("train", "validation"), ("train", "test"), ("validation", "test")]
    for left, right in pairs:
        overlap = values[left] & values[right]
        rows.append(
            {
                "dimension": dimension,
                "partition_left": left,
                "partition_right": right,
                "left_unique": len(values[left]),
                "right_unique": len(values[right]),
                "overlap_unique": len(overlap),
                "overlap_examples": " | ".join(sorted(overlap)[:12]),
            }
        )
    return rows


def subgroup_summary(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    prepared["assay_sensitivity_status"] = np.where(
        prepared["ada_assay_sensitivity_missing"].fillna(1).astype(int).eq(1),
        "Not reported",
        "Reported",
    )
    prepared["assessment_duration_band"] = pd.cut(
        pd.to_numeric(prepared["assessment_days"], errors="coerce"),
        bins=[-np.inf, 28, 84, 180, 365, np.inf],
        labels=["≤28 days", "29–84 days", "85–180 days", "181–365 days", ">365 days"],
    ).astype("string").fillna("Missing")
    prepared["assessed_sample_size_band"] = pd.cut(
        pd.to_numeric(prepared["n_ada_assessed"], errors="coerce"),
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
        values = prepared[dimension].astype("string").fillna("Missing")
        for level, index in values.groupby(values, dropna=False).groups.items():
            subset = prepared.loc[index]
            positive = int(subset["ada_high_10"].sum())
            total = int(len(subset))
            groups = int(subset["model_split_group"].nunique())
            rows.append(
                {
                    "dimension": dimension,
                    "level": str(level),
                    "rows": total,
                    "study_groups": groups,
                    "molecules": int(subset["molecule_inn_name"].nunique()),
                    "positive_rows": positive,
                    "negative_rows": total - positive,
                    "high_ada_prevalence": positive / total if total else np.nan,
                    "ada_mean": float(subset["ada_frequency_percent"].mean()),
                    "ada_median": float(subset["ada_frequency_percent"].median()),
                    "readiness": (
                        "Ready"
                        if total >= 50 and groups >= 20 and positive >= 10 and total - positive >= 10
                        else "Descriptive only"
                    ),
                }
            )
    return pd.DataFrame(rows).sort_values(["dimension", "rows"], ascending=[True, False])


def main() -> None:
    df = pd.read_excel(INPUT, sheet_name="Modeling_Data")
    split = pd.read_csv(SPLIT, dtype={"idc_row_id": "string"})
    if split["idc_row_id"].duplicated().any() or df["idc_row_id"].duplicated().any():
        raise ValueError("idc_row_id must be unique in both sources")
    merged = df.merge(
        split[["idc_row_id", "partition"]],
        on="idc_row_id",
        how="inner",
        validate="one_to_one",
    )
    if len(merged) != len(df) or set(merged["partition"]) != {"train", "validation", "test"}:
        raise ValueError("Modeling table and split audit do not align")

    partition_summary = (
        merged.groupby("partition", observed=True)
        .agg(
            rows=("idc_row_id", "size"),
            study_groups=("model_split_group", "nunique"),
            molecules=("molecule_inn_name", "nunique"),
        )
        .reset_index()
    )
    study_sets = {
        name: set(part["model_split_group"].astype(str))
        for name, part in merged.groupby("partition", observed=True)
    }
    molecule_sets = {
        name: set(part["molecule_inn_name"].astype(str))
        for name, part in merged.groupby("partition", observed=True)
    }
    overlap = pd.DataFrame(
        pairwise_overlap(study_sets, "model_split_group")
        + pairwise_overlap(molecule_sets, "molecule_inn_name")
    )

    dev = merged.loc[merged["partition"].isin(["train", "validation"])].copy()
    dev["study_molecule_component"] = component_labels(dev)
    component_summary = (
        dev.groupby("study_molecule_component", observed=True)
        .agg(
            rows=("idc_row_id", "size"),
            study_groups=("model_split_group", "nunique"),
            molecules=("molecule_inn_name", "nunique"),
            high_ada_prevalence=("ada_high_10", "mean"),
        )
        .reset_index()
        .sort_values("rows", ascending=False)
    )
    subgroup = subgroup_summary(dev)

    dev_molecules = set(dev["molecule_inn_name"].astype(str))
    test_identifiers = merged.loc[merged["partition"].eq("test"), ["molecule_inn_name"]]
    test_molecules = set(test_identifiers["molecule_inn_name"].astype(str))
    unseen_test_molecules = sorted(test_molecules - dev_molecules)
    seen_test_molecules = sorted(test_molecules & dev_molecules)

    partition_summary.to_csv(ARTIFACTS / "partition_summary.csv", index=False)
    overlap.to_csv(ARTIFACTS / "partition_overlap.csv", index=False)
    component_summary.to_csv(ARTIFACTS / "study_molecule_components.csv", index=False)
    subgroup.to_csv(ARTIFACTS / "subgroup_readiness.csv", index=False)

    largest_component = component_summary.iloc[0]
    metadata = {
        "rows": int(len(merged)),
        "development_rows": int(len(dev)),
        "test_rows": int(merged["partition"].eq("test").sum()),
        "development_study_groups": int(dev["model_split_group"].nunique()),
        "development_molecules": int(dev["molecule_inn_name"].nunique()),
        "study_molecule_components": int(len(component_summary)),
        "largest_component_rows": int(largest_component["rows"]),
        "largest_component_study_groups": int(largest_component["study_groups"]),
        "largest_component_molecules": int(largest_component["molecules"]),
        "test_molecules": len(test_molecules),
        "test_molecules_seen_in_development": len(seen_test_molecules),
        "test_molecules_unseen_in_development": len(unseen_test_molecules),
        "unseen_test_molecule_names": unseen_test_molecules,
        "test_outcome_used": False,
    }
    (ARTIFACTS / "readiness_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    ready_counts = (
        subgroup.groupby("dimension")["readiness"]
        .apply(lambda values: int(values.eq("Ready").sum()))
        .to_dict()
    )
    report = f"""# IDC 下一阶段验证就绪度审计

## 结论

- 开发集：{len(dev):,} 行、{dev['model_split_group'].nunique():,} 个研究组、{dev['molecule_inn_name'].nunique():,} 个分子。
- 测试集：{metadata['test_rows']:,} 行、{metadata['test_molecules']:,} 个分子；其中 {metadata['test_molecules_seen_in_development']:,} 个在开发集出现过，{metadata['test_molecules_unseen_in_development']:,} 个完全未见。
- 原拆分的研究组跨分区重叠为 0；分子跨分区存在重叠。因此当前测试回答的是“新研究记录”泛化，不是严格的“全新分子”泛化。
- 开发集的研究—分子二部图形成 {metadata['study_molecule_components']:,} 个连通分量；最大分量包含 {metadata['largest_component_rows']:,} 行、{metadata['largest_component_study_groups']:,} 个研究组和 {metadata['largest_component_molecules']:,} 个分子。
- 连通分量结果决定能否同时保证研究和分子零重叠；如果最大分量过大，五折双重隔离会高度不平衡，应把按分子验证和按研究验证分别报告。
- 本审计没有使用测试集结局。

## 亚组分析就绪度

“Ready”要求至少 50 行、20 个研究组、10 个阳性和 10 个阴性；否则只做描述，不做模型优劣结论。

| 维度 | 可正式描述的水平数 |
|---|---:|
{chr(10).join(f'| {key} | {value} |' for key, value in ready_counts.items())}

详细水平、样本数、研究组数和事件数见 `work/validation_stage2/subgroup_readiness.csv`。

## 对下一步的直接影响

1. 首先生成按研究组隔离的开发集 OOF 预测，用于校准和阈值敏感性。
2. 另行生成按分子隔离的 OOF 预测，明确报告研究上下文是否仍有重叠。
3. 对 assay platform、检测灵敏度报告状态、评估时长和样本量做预设亚组分析。
4. 外部验证数据应优先选择既有研究组和分子均未出现的新来源或后续时间段。
"""
    REPORT.write_text(report, encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
