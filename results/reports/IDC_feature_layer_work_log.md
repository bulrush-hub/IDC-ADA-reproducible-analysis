# IDC ADA三层特征重构工作日志

日期：2026-09-29

## 任务

把主模型特征划分为 Molecular、Clinical、Measurement 三层，为后续 sequence-based ADA prediction、临床情境分析和检测偏倚分析建立统一代码入口。

## 数据核对

- 核对文件：`data/cleaned/IDC_modeling_table_final_model_ready.xlsx` 的 `Modeling_Data`。
- 数据规模：2,611行、87列。
- 当前锁定基线：29项预测特征。
- 分层结果：Molecular 14项、Clinical 6项、Measurement 9项，合计29项，无遗漏、无跨层重复。

候选字段核对结果：

- `expression_system`：0%缺失，6个水平。
- `fc_modifications_clean`：69.7%缺失，12个非空水平。
- `patient_population`：1.5%缺失，但有673个自由文本水平。
- `coadministered_drugs`：67.4%缺失，200个非空水平。
- `ada_assay_sensitivity`：75.3%缺失，154个非空表达。
- `dosing_schedule_description`：7.1%缺失，但仍是1,202种自由文本；当前没有标准化的 `dosing_interval_days`。

## 代码修改

1. 新增 `code/modeling/feature_layers.py`，集中定义三层特征、研究问题、未来候选字段和完整性断言。
2. `IDC_modeling_pipeline.py`、`IDC_TabPFN_pipeline.py` 和 `IDC_oof_validation.py` 改为从同一模块导入29项特征。
3. 保留原29项特征和原始列顺序，避免仅因重排造成随机森林或TabPFN结果变化。
4. 基线结果下次运行时新增 `feature_layer_manifest.csv`。
5. feature importance、SHAP、线性系数和二项模型系数输出新增 `feature_layer` 标签。
6. TabPFN置换重要性新增 `feature_layer` 标签。
7. 新增 `docs/FEATURE_LAYER_DESIGN.md`，记录三层含义、候选字段、缺失率、验证顺序和解释边界。

## 关键决策

- 本次不把候选字段直接加入已经锁定的29项基线。
- 原因是封存测试集结果已经查看；此时根据新想法增加特征并反复读取同一测试集，会形成测试集适配。
- `expression_system` 虽然完整度高，也应先在开发集做按研究和按分子的分组OOF消融。
- `fc_modifications_clean`、患者人群、具体联合用药和ADA灵敏度需先完成缺失语义或文本标准化。
- 后续 sequence-based 模型必须以按分子隔离的验证为主，防止相同分子的序列信号跨折泄漏。
- “同一种 biologic 的 clinical context”需要分子内或层级模型；普通 pooled 模型不能保证是同分子比较。
- 当前IDC表缺少未检测/未报告ADA研究的完整分母；Measurement层不能直接估计所有研究中的ADA报告概率。

## 本次未执行

- 未重新拟合随机森林或TabPFN。
- 未覆盖既有性能表、预测文件或封存测试结果。
- 未把自由文本直接编码为高基数类别。
