"""Build and execute the user-facing IDC modeling notebook."""

from __future__ import annotations

import os
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "outputs" / "IDC_modeling_analysis.ipynb"
os.environ.setdefault("IPYTHONDIR", str(ROOT / "work" / ".ipython"))
os.environ.setdefault("JUPYTER_CONFIG_DIR", str(ROOT / "work" / ".jupyter"))

nb = nbf.v4.new_notebook()
nb["metadata"] = {
    "kernelspec": {
        "display_name": "IDC project .venv",
        "language": "python",
        "name": "python3",
    },
    "language_info": {"name": "python", "version": "3.12"},
}

cells = []
cells.append(
    nbf.v4.new_markdown_cell(
        """# IDC ADA 建模分析

本 Notebook 按工作大纲展示最终模型流程：数据版本冻结、结局定义、EDA、特征工程、研究组隔离、模型比较、Feature Importance、SHAP、二项模型和敏感性分析。

核心建模代码位于同目录的 `IDC_modeling_pipeline.py`。本 Notebook 默认读取已验证结果；将末尾的 `RUN_FULL_PIPELINE` 设为 `True` 可完整重跑。"""
    )
)
cells.append(
    nbf.v4.new_code_cell(
        """from pathlib import Path
import json
import sys
import pandas as pd
from IPython.display import Image, display

def find_project_root():
    for candidate in [Path.cwd(), Path.cwd().parent]:
        if (candidate / "outputs" / "IDC_modeling_table_final_model_ready.xlsx").exists():
            return candidate.resolve()
    raise FileNotFoundError("Project root not found")

ROOT = find_project_root()
ARTIFACTS = ROOT / "work" / "modeling_artifacts"
FIGURES = ROOT / "outputs" / "modeling_figures"
assert ".venv" in str(Path(sys.executable).resolve()), "Notebook is not running in the project .venv"
print("Project root:", ROOT)
print("Python:", sys.executable)"""
    )
)

cells.append(nbf.v4.new_markdown_cell("## 步骤 1：冻结输入版本与环境"))
cells.append(
    nbf.v4.new_code_cell(
        """results = json.loads((ARTIFACTS / "modeling_results.json").read_text(encoding="utf-8"))
pd.Series(results["metadata"], name="value").to_frame()"""
    )
)

cells.append(nbf.v4.new_markdown_cell("## 步骤 2：结局定义与输入质量复核"))
cells.append(
    nbf.v4.new_code_cell(
        """validation = pd.Series(results["validation"], name="value").to_frame()
display(validation)
print("Continuous outcome: ada_frequency_percent")
print("Binary outcome: ada_high_10 (ADA frequency >= 10%)")
print("Count model: binomial_count_model_eligible rows only")"""
    )
)

cells.append(
    nbf.v4.new_markdown_cell(
        """## 步骤 3：探索性数据分析

EDA用于理解分布和缺失结构，不在此阶段根据测试集表现删除变量。主分析不使用分子名称、研究ID或来源ID作为预测特征。"""
    )
)
cells.append(
    nbf.v4.new_code_cell(
        """profile = pd.read_csv(ARTIFACTS / "profile.csv")
model_input_missingness = pd.read_csv(ARTIFACTS / "model_input_missingness.csv")
target_summary = pd.read_csv(ARTIFACTS / "target_summary.csv")
moa_summary = pd.read_csv(ARTIFACTS / "moa_summary.csv")
print("Model-input missingness audit (full-column profile remains available separately):")
display(model_input_missingness)
display(target_summary.head(10))
display(moa_summary.head(10))
display(Image(filename=str(FIGURES / "01_ada_distribution.png")))
display(Image(filename=str(FIGURES / "02_missingness.png")))"""
    )
)

cells.append(
    nbf.v4.new_markdown_cell(
        """## 步骤 4：特征工程与研究组隔离

数值特征在 Pipeline 内中位数填补并标准化；类别变量在训练折内填补、合并低频水平并独热编码。划分先按ADA频率区间分层，再按 `model_split_group` 隔离。"""
    )
)
cells.append(
    nbf.v4.new_code_cell(
        """split_audit = pd.read_csv(ARTIFACTS / "split_audit.csv")
split_summary = pd.DataFrame(results["split_summary"]).T
display(split_summary)
group_overlap = {
    (a, b): len(set(split_audit.loc[split_audit.partition.eq(a), "model_split_group"]) &
                set(split_audit.loc[split_audit.partition.eq(b), "model_split_group"]))
    for a, b in [("train", "validation"), ("train", "test"), ("validation", "test")]
}
group_overlap"""
    )
)

cells.append(nbf.v4.new_markdown_cell("## 步骤 5：候选模型与开发集分组交叉验证"))
cells.append(
    nbf.v4.new_code_cell(
        """performance = pd.read_csv(ARTIFACTS / "performance.csv")
selected_models = results["selected_models"]
print("Selected models:", selected_models)
display(performance[performance.outcome.isin(["continuous", "binary"])])"""
    )
)

cells.append(nbf.v4.new_markdown_cell("## 步骤 6：独立测试集评价"))
cells.append(
    nbf.v4.new_code_cell(
        """selected_performance = performance[performance["selected"].fillna(False)].copy()
display(selected_performance)
predictions = pd.read_csv(ARTIFACTS / "predictions.csv")
display(predictions.head(10))"""
    )
)

cells.append(
    nbf.v4.new_markdown_cell(
        """## 步骤 7：Feature Importance 与 SHAP

Permutation importance 在隔离测试集上计算；稳定性结果来自5折 GroupKFold。SHAP使用随机森林解释模型并聚合回原始特征。重要性代表预测贡献，不代表因果作用。"""
    )
)
cells.append(
    nbf.v4.new_code_cell(
        """importance = pd.read_csv(ARTIFACTS / "feature_importance.csv")
held_out = importance[importance.method.eq("held-out permutation importance")]
display(held_out.groupby("outcome", group_keys=False).head(15))
display(Image(filename=str(FIGURES / "05_continuous_permutation_importance.png")))
display(Image(filename=str(FIGURES / "06_binary_permutation_importance.png")))"""
    )
)
cells.append(
    nbf.v4.new_code_cell(
        """shap_rows = importance[importance.method.str.contains("SHAP", na=False)]
display(shap_rows.groupby("outcome", group_keys=False).head(15))
display(Image(filename=str(FIGURES / "07_continuous_shap_importance.png")))
display(Image(filename=str(FIGURES / "08_binary_shap_importance.png")))"""
    )
)

cells.append(nbf.v4.new_markdown_cell("## 步骤 8：二项计数模型"))
cells.append(
    nbf.v4.new_code_cell(
        """display(performance[performance.outcome.eq("binomial_count")])
pd.Series(results["count_model"], name="value").to_frame()"""
    )
)

cells.append(
    nbf.v4.new_markdown_cell(
        """## 步骤 9：敏感性与泛化分析

包括排除计数不一致记录、排除依赖记录、加入分子身份以及未见分子留出。未见分子表现是判断外推能力的关键限制。"""
    )
)
cells.append(
    nbf.v4.new_code_cell(
        """sensitivity = pd.read_csv(ARTIFACTS / "sensitivity.csv")
display(sensitivity)"""
    )
)

cells.append(
    nbf.v4.new_markdown_cell(
        """## 步骤 10：结论与完整重跑

- 研究组隔离测试用于评估已观察药物空间内的泛化。
- 未见分子测试明显更难，因此不能把当前模型直接视为新分子ADA风险的可靠外部预测器。
- Feature importance用于预测解释，不证明因果关系。
- 二项模型只使用计数一致记录，并以评估人数作为权重。"""
    )
)
cells.append(
    nbf.v4.new_code_cell(
        """RUN_FULL_PIPELINE = False
if RUN_FULL_PIPELINE:
    import importlib.util
    module_path = ROOT / "outputs" / "IDC_modeling_pipeline.py"
    spec = importlib.util.spec_from_file_location("idc_modeling_pipeline", module_path)
    pipeline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pipeline)
    pipeline.run_pipeline()
else:
    print("Set RUN_FULL_PIPELINE = True to regenerate all model results.")"""
    )
)

nb["cells"] = cells
nbf.validate(nb)
client = NotebookClient(
    nb,
    timeout=900,
    kernel_name="python3",
    resources={"metadata": {"path": str(ROOT)}},
)
client.execute()
nbf.validate(nb)
nbf.write(nb, OUTPUT)
print(OUTPUT)
