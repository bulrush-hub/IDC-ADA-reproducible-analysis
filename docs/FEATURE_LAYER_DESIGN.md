# ADA预测三层特征设计

更新日期：2026-09-29  
适用范围：IDC 主随机森林、TabPFN-3、开发集 OOF 和后续 sequence-based ADA prediction。

## 1. 设计目标

把预测信息按科学问题分成三层，避免把“分子本身的免疫原性”“临床暴露情境”和“检测机会”混为一个难以解释的总模型。

1. **Molecular layer**：这个 biologic 自身的哪些性质与 ADA 风险有关？哪些信号可以外推到未见过的新分子？
2. **Clinical layer**：同一种 biologic 在什么治疗和患者情境下更容易观察到 ADA？
3. **Measurement layer**：这个研究设计和检测流程有多大概率检测或报告出 ADA？

代码中的唯一特征定义位于 `code/modeling/feature_layers.py`。基线、TabPFN 和 OOF 脚本均从该文件导入特征，避免多份列表逐渐不一致。

## 2. 当前锁定基线：29项

本次只重组解释层级，不改变已经查看过封存测试集的29项输入，也不改变原始列顺序。因此既有性能结果仍代表原锁定基线。

### 2.1 Molecular features（14项）

- 类别：`protein_modality`、`species`、`antibody_backbone_clean`、`light_chain_clean`、`conjugate_modification_clean`、`target_group`、`moa_group`、`labelled_as_biosimilar`、`sequence_verified`
- 数值：`log_total_sequence_length`、`n_sequence_chains`、`n_unique_sequences`、`max_chain_length`
- 二元：`sequence_available`

这一层是后续 sequence-based ADA prediction 的主体。当前的序列信息仍较粗，只反映是否有序列、序列长度和链数，还没有真正的表位、理化或表示学习特征。

### 2.2 Clinical features（6项）

- 类别：`disease_category_clean`、`route_clean`
- 数值：`log_dose_mg_extracted`
- 二元：`has_coadministered_drugs`、`comedication_missing`、`dose_mg_missing`

这一层回答给药途径、剂量、疾病和联合治疗情境下的观察差异。当前尚不能可靠控制患者免疫状态、疾病严重程度和标准化给药间隔。

严格回答“同一种 biologic 在什么 clinical context 下更容易观察到 ADA”时，不能只拟合 pooled clinical-only 模型。应使用分子随机截距/固定效应、同一分子内对比或分子表示条件化模型，并按分子与研究设计交叉验证。否则 clinical feature 仍可能吸收不同分子组成造成的差异。

### 2.3 Measurement features（9项）

- 类别：`ada_assay_platform`、`prospective_or_retrospective`、`randomized_or_not`、`trial_blinding`、`therapeutic_comparator`
- 数值：`log_n_ada_assessed`、`log_assessment_days`
- 二元：`ada_assay_missing`、`ada_assay_sensitivity_missing`

这一层描述检测平台、随访机会、样本量和研究设计。它主要解释“是否更容易检测/报告 ADA”，不能解释为 biologic 的内在免疫原性。

当前 IDC 表主要包含已经形成可提取 ADA 记录的研究/治疗臂，没有“开展了研究但没有检测或没有报告 ADA”的完整分母。因此，现有数据可以分析 measurement feature 与**已观察 ADA 值**之间的关联，但不能直接估计“所有研究中报告 ADA 的概率”。若要回答后一个问题，需要补充未检测/未报告研究，并单独定义报告结局；必要时使用两阶段 selection/hurdle 模型。

## 3. 下一版本候选字段

下列字段存在于当前模型表中，但不直接加入已经锁定的基线。新增特征必须只在开发集上完成清洗、选择和消融分析，封存测试集不再用于选择。

| 层级 | 候选字段 | 当前数据情况 | 加入前要求 |
|---|---|---|---|
| Molecular | `expression_system` | 0%缺失，6个水平 | 检查分子聚类、稀有水平和与 modality 的共线性 |
| Molecular | `fc_modifications_clean` | 69.7%缺失，12个非空水平 | 区分“未修饰”和“未报告”，复核文本标准化 |
| Molecular | `target_clean` | 74个水平 | 与 `target_group` 比较，防止稀有靶点记忆 |
| Molecular | `mechanism_of_action_reviewed` | 97个水平 | 优先形成可重复的MOA多标签编码，而不是直接使用长文本 |
| Molecular | 重/轻链及完整蛋白序列 | 22.5%记录缺少可用序列派生量 | 计算可迁移的序列表示，并严格按分子分组验证 |
| Clinical | `patient_population` | 1.5%缺失，但有673个自由文本水平 | 建立受控分类，如健康受试者、既往治疗和免疫状态 |
| Clinical | 给药间隔 | 只有给药方案自由文本，尚无标准数值列 | 解析为 `dosing_interval_days`，保留解析置信度和缺失指示 |
| Clinical | `coadministered_drugs` | 67.4%缺失，200个非空水平 | 标准化药名和免疫抑制类别，不把未报告当作无联合用药 |
| Measurement | `ada_assay_sensitivity` | 75.3%缺失，且单位/表达不统一 | 统一单位、下限和定性描述，再与缺失指示配对使用 |

## 4. 后续模型比较顺序

建议在开发集内预注册下列模型，不再根据封存测试集反复挑选：

1. Molecular-only：评估 biologic 本身可预测到什么程度。
2. Clinical-only：评估临床情境的预测能力。
3. Measurement-only：评估检测和报告过程的影响。
4. Molecular + Clinical：预测分子在临床情境下的综合风险。
5. Molecular + Clinical + Measurement：完整观察模型。
6. 完整模型去除 Measurement：检查排序和误差是否主要由检测机会驱动。
7. 同一分子临床情境模型：分子随机截距或分子固定效应，只解释分子内 clinical variation。
8. 报告/检测模型：只有获得未检测或未报告研究分母后才拟合，不能用当前表的缺失值替代该分母。

每个比较至少同时报告按研究分组和按分子分组的 OOF 指标。sequence-based 模型的主判断应以按分子分组的结果为准，因为随机行划分或仅按研究划分仍可能让同一分子的序列信息进入训练和验证两侧。

## 5. 解释边界

- 三层是科学解释框架，不是因果识别策略。
- Measurement feature 的高重要性不表示它引发 ADA，只表示它影响被观察到的概率。
- Molecular feature importance 只有在按分子隔离验证后，才能用于讨论对新 biologic 的可迁移预测。
- 自由文本字段不能直接作为普通类别变量加入；必须先建立版本化、可审计的标准化规则。
- 任何新特征、阈值和校准方法均应在开发集决定，再用新的外部数据验证。
