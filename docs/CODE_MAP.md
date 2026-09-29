# 代码地图与运行依赖

本文档说明每个主要入口负责什么、读取什么、写出什么。所有命令均应从仓库根目录运行。

## 清洗

### `code/cleaning/IDC_Clean_final_model_ready.ipynb`

- 作用：执行文本标准化、冗余源观察去重、主键修复、target/MOA 映射、人工审核覆盖、ADA QC 与最终建模字段筛选。
- 关键输出：`data/cleaned/IDC_modeling_table_final_model_ready.xlsx`。
- 关键断言：2,611 行、主键唯一、无 `Bevacizumab + CD22` 残留、MOA 无未分类、二项计数模型可用 2,506 行。
- 注意：发布目录包含已审核输出。若从最初外部建模表重新执行，应先把该输入冻结到项目相对路径并记录哈希。

## 基线建模

### `code/modeling/feature_layers.py`

- 作用：集中定义 Molecular、Clinical、Measurement 三层特征及其科学问题。
- 当前状态：把锁定的29项基线特征完整映射到三层，不改变特征集合或历史列顺序。
- 后续候选：记录 `expression_system`、`fc_modifications_clean`、患者人群、给药间隔和序列衍生特征，但不在未经开发集验证时自动加入模型。
- 设计说明：`docs/FEATURE_LAYER_DESIGN.md`。

### `code/modeling/IDC_modeling_pipeline.py`

- 输入：`data/cleaned/IDC_modeling_table_final_model_ready.xlsx`。
- 作用：固定29项三层特征，按研究组隔离训练/验证/测试；比较回归、分类和二项计数模型；输出预测、性能、特征层清单、敏感性、Permutation importance、SHAP 和系数。
- 随机种子：`20260802`。
- 环境：`.venv`。

发布包中脚本保留了原项目的相对输出路径。若直接在本仓库运行，可把 `data/cleaned/IDC_modeling_table_final_model_ready.xlsx` 复制到 `outputs/`，或在脚本中显式修改输入路径；任何修改都应记录在运行日志中。

## TabPFN-3

### `code/modeling/IDC_TabPFN_pipeline.py`

- 作用：用与基线相同的 29 项信息和分区运行 TabPFN-3，并生成开发集分组 CV、封存测试预测和置换重要性。
- 固定版本：`tabpfn==8.2.0`；估计器数 8；随机种子 `20260802`。
- 环境：`.venv-tabpfn`。
- 权重：首次运行时按许可下载；权重不在仓库中。

### `code/modeling/IDC_TabPFN_postprocess.py`

- 作用：与已冻结的随机森林结果对齐，计算配对 bootstrap、生成比较表、报告和 Notebook。

## 验证与 OOF

### `code/modeling/IDC_validation_readiness.py`

- 作用：审计研究/分子跨分区重叠、研究—分子连通分量和亚组分析就绪度；不拟合模型。

### `code/modeling/IDC_oof_validation.py`

- 作用：在 2,237 行开发集上分别生成按研究组和按分子隔离的 OOF 预测。
- 参数：`--schemes study,molecule`。
- 禁止读取封存测试结局用于模型选择。

### `code/modeling/IDC_oof_postprocess.py`

- 作用：计算区分度、概率误差、校准、阈值敏感性、聚类 bootstrap、亚组性能和高 ADA 误差。

## 论文复现

### `code/paper_replication/run_replication.py`

- `--mode proxy`：公开数据代理分析；当前完整案例 1,443。
- `--mode exact`：要求作者逐行派生变量、唯一键、允许水平和完整案例数全部通过校验；预期完整案例 1,216。
- `--allow-sample-mismatch` 只用于诊断，不能用于宣称精确复现。

### `code/paper_replication/run_dedup_scenarios.py`

- 输出一分子一行（110 行，完整 GLM 66）和一分子×疾病一行（146 行，完整 GLM 78）。
- 代表行按已冻结的审核/完整性/中位数距离/样本量/源行号规则选择，不合成不同研究的字段。

### `code/paper_replication/run_grouped_nested_cv.py`

- 外层 5 折 × 10 次重复，内层 4 折，均按分子分组。
- 随机种子 `20260809`；L2 网格 `[0.001, 0.01, 0.1, 1.0, 10.0]`。
- 计算 row-weighted 与 molecule-balanced 指标、分子聚类 bootstrap 和外层置换重要性。

## 工作簿生成器

`code/workbook_builders/` 保存将 CSV/JSON 汇总为 Excel、渲染预览和执行校验的脚本。它们依赖原 Codex 工作区提供的表格运行时；核心统计结果均另存为 CSV/JSON，不依赖 Excel 才能审计。
