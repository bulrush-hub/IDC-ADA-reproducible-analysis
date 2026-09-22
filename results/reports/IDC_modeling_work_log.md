# IDC 建模工作日志

运行时间（UTC）：2026-08-08T14:28:59.609869+00:00

## 步骤 1：冻结输入版本与环境

- 输入文件：`IDC_modeling_table_final_model_ready.xlsx`
- SHA-256：`1B64526057CE479A94DAC4F622F46FA9C22EF31E16DC892DC086BBAC08A64AA1`
- Python：3.12.13
- 解释器：项目本地 `.venv`
- scikit-learn：1.9.0
- pandas：3.0.5
- 随机种子：20260802

关键点：虚拟环境仅用于当前项目。迁移到 Linux 时重建 `.venv`，不复制 Windows 虚拟环境目录。

### 执行审计

- 首次完整运行在二项模型评价阶段停止：分类版 `log_loss` 不接受0到1之间的比例型结局。
- 修正：改用按 `n_ada_assessed` 加权的二项交叉熵公式。
- 该异常发生在结果评价阶段，没有修改输入数据或改变数据划分。
- 初始纯研究组随机划分使测试集ADA≥10%比例达到48.3%，高于全体33.0%。最终改为按ADA区间分层的研究组划分，使三部分结局分布更接近总体，同时保持研究组完全隔离。

## 步骤 2：输入质量复核与结局定义

- 建模记录：2611
- 唯一 `idc_row_id`：2611
- 独立拆分组：680
- ADA≥10%：861 条（33.0%）
- 二项计数模型可用：2506 条
- 计数与频率不一致：95 条
- 嵌套/纵向依赖提示：4 条

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
| 训练 | 1864 | 484 | 13.66 | 3.00 | 33.0% |
| 验证 | 373 | 98 | 14.51 | 3.10 | 33.0% |
| 测试 | 374 | 98 | 12.75 | 3.10 | 32.9% |

关键点：先按ADA频率区间分层，再按 `model_split_group` 隔离；同一研究不会跨训练、验证和测试分区。模型选择使用开发集上的5折 GroupKFold，最终测试集不参与选择。

## 步骤 5：连续结局模型

- 选择模型：Random forest
- 测试集 MAE：10.585 个百分点
- 测试集 RMSE：15.142 个百分点
- 测试集 R²：0.461

## 步骤 6：二分类模型

- 选择模型：Random forest
- 测试集 ROC-AUC：0.855
- 测试集 PR-AUC：0.768
- 测试集 F1：0.701
- 测试集平衡准确率：0.775
- 测试集 Brier：0.159

## 步骤 7：二项计数模型

- 拟合方式：L2-regularized GLM fallback
- 开发集：2136 条，测试集：370 条
- 测试集加权 MAE：10.261 个百分点
- 测试集加权 Brier：0.0202
- 测试集加权 Log Loss：0.3757

关键点：该模型使用评估人数作为频数权重，且未把ADA阳性计数或频率派生字段作为预测特征。

## 步骤 8：Feature Importance

### 连续模型前10项（测试集 permutation importance）

- therapeutic_comparator: 1.5756
- labelled_as_biosimilar: 1.3217
- route_clean: 1.0049
- antibody_backbone_clean: 0.9215
- target_group: 0.6457
- log_assessment_days: 0.5112
- log_n_ada_assessed: 0.4116
- protein_modality: 0.3576
- log_dose_mg_extracted: 0.2993
- ada_assay_platform: 0.2573

### 二分类模型前10项（测试集 permutation importance）

- route_clean: 0.0449
- log_n_ada_assessed: 0.0401
- therapeutic_comparator: 0.0333
- target_group: 0.0211
- randomized_or_not: 0.0195
- log_dose_mg_extracted: 0.0165
- log_assessment_days: 0.0146
- labelled_as_biosimilar: 0.0133
- disease_category_clean: 0.0125
- ada_assay_platform: 0.0124

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

## 步骤 11：图形统计口径与可读性复核（2026-08-08）

### 发现的问题

- 原 `02_missingness.png` 直接按全字段 `isna()` 排序，把 `record_review_note`、`target_correction_note`、`moa_review_note`、`record_dependency_note` 等“仅在出现问题时填写”的审核备注误画成高缺失字段。
- `half_life_extension_partner`、`progeny_of`、`fc_modifications` 等只对部分分子适用；空值通常代表“不适用”，不能与建模输入缺失混为一谈。
- 原图还混入 `log_*` 等派生字段，因此同一源信息可能被重复计数。
- Target/MOA 描述图没有标明每组记录数；Feature Importance/SHAP 图使用内部变量名，且置换重要性的坐标含义与不确定性没有明确展示。

### 修正方法

- 保留 `profile.csv` 作为全字段技术审计，不删除任何字段，也不修改原始数据。
- 新增 `model_input_missingness.csv`，审计 22 个建模相关源字段，并记录：展示名称、关联模型特征、字段角色、是否进入主图、排除原因、缺失判定规则、缺失数、缺失率和可用数。
- 对已显式编码的缺失使用现有指示变量计算，例如 `ada_assay_missing`、`dose_mg_missing`、`sequence_available`；疾病类别中的 `Unspecified` 按有效缺失计入。
- 主缺失图排除审核/说明字段、派生辅助列和条件适用字段，并在图下注明统计范围。`coadministered_drugs` 的空值可能表示“无合并用药组”或“未报告”，`therapeutic_comparator` 对单臂研究可能不适用；两者保留在审计表但不作为真实缺失率绘图。
- Target/MOA 图增加百分比和 `n`；重要性图改为可读标签，置换重要性加入重复置换标准差误差线，并明确 MAE/average precision 的坐标含义。

### 修正后的主要真实信息缺口

| 建模相关源字段 | 缺失数 | 缺失率 |
|---|---:|---:|
| ADA assay sensitivity | 1967 | 75.3% |
| ADA assay platform | 1290 | 49.4% |
| Sequence-derived descriptors | 587 | 22.5% |
| Randomization status | 528 | 20.2% |
| Extracted dose | 525 | 20.1% |
| Sequence verification status | 293 | 11.2% |
| Trial blinding | 243 | 9.3% |

### 执行与验证

- 使用项目本地 `.venv` 完整重跑 `IDC_modeling_pipeline.py`，没有安装或修改任何全局 Python 依赖。
- 输入 SHA-256 保持为 `1B64526057CE479A94DAC4F622F46FA9C22EF31E16DC892DC086BBAC08A64AA1`；数据、特征集合、拆分和模型算法未因本次图形修正而改变。
- 连续与二分类最佳模型仍均为 Random forest；测试集结果保持为连续模型 MAE 10.585、R² 0.461，二分类 ROC-AUC 0.855、PR-AUC 0.768、Brier 0.159。
- 已重新生成 8 张主建模图并逐张视觉检查；重新构建 `IDC_modeling_analysis.ipynb`，23 个单元格中 12 个代码单元格全部执行，错误为 0。
