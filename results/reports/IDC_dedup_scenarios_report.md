# IDC 两种去重场景分析报告

生成时间：2026-08-08T23:10:49.856175+00:00

## 结论范围

本分析创建两个独立清洗场景，不修改、不覆盖 `outputs/paper_replication/` 原始结果。每个组保留一条真实来源记录，不合成跨试验字段。

## 场景摘要

| scenario_id | group_definition | source_candidate_rows | selected_rows | rows_removed | rows_removed_percent | unique_molecules | unique_molecule_disease_groups | selected_audited_rows | selected_proxy_model_ready_rows | proxy_model_complete_cases | high_ada_selected_rows | high_ada_selected_percent | selection_rule |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| one_row_per_molecule | normalized Molecule Assessed for ADA INN Name | 2666 | 110 | 2556 | 0.95874 | 110 | 110 | 70 | 66 | 66 | 31 | 0.281818 | tier: audited+complete > complete > audited > other; then ADA nearest group median > larger ADA patient count > lower source row |
| one_row_per_molecule_disease_category | normalized molecule + raw Disease Indication Category | 2666 | 146 | 2520 | 0.945236 | 110 | 146 | 81 | 78 | 78 | 34 | 0.232877 | tier: audited+complete > complete > audited > other; then ADA nearest group median > larger ADA patient count > lower source row |

## 顺序 deviance 对照

| display_rank | model_order | variable | published_deviance | published_p_value | all_public_rows_deviance | all_public_rows_p_value | all_public_rows_n_complete | one_per_molecule_deviance | one_per_molecule_p_value | one_per_molecule_n_complete | one_per_molecule_disease_category_deviance | one_per_molecule_disease_category_p_value | one_per_molecule_disease_category_n_complete |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 3 | Therapeutic Immune MOA Type | 111.419 | 5.43e-24 | 58.9892 | 9.66415e-13 | 1443 | 8.33579 | 0.0395586 | 66 | 9.70271 | 0.0212698 | 78 |
| 2 | 2 | Disease Indication | 48.0379 | 9.27e-10 | 88.2319 | 3.12612e-18 | 1443 | 2.22944 | 0.693643 | 66 | 3.35866 | 0.499691 | 78 |
| 3 | 1 | T cell Epitope Content | 44.4769 | 2.57e-11 | 31.9017 | 1.62179e-08 | 1443 | 0.0623672 | 0.802793 | 66 | 0.0254558 | 0.873237 | 78 |
| 4 | 6 | Dose Interval | 17.13 | 3.49e-05 | 0.559191 | 0.454586 | 1443 | 3.35403 | 0.0670406 | 66 | 1.79288 | 0.180576 | 78 |
| 5 | 8 | Route of Administration | 7.05026 | 0.070313 | 19.9198 | 0.000176368 | 1443 | 0.472307 | 0.924932 | 66 | 0.491358 | 0.920786 | 78 |
| 6 | 4 | Comedication Immune MOA Type | 5.15492 | 0.075967 | 0.116222 | 0.943545 | 1443 | 0.973166 | 0.614723 | 66 | 1.59364 | 0.45076 | 78 |
| 7 | 5 | Dose Level | 5.07256 | 0.024307 | 7.15352 | 0.00748172 | 1443 | 3.99083 | 0.0457486 | 66 | 2.93333 | 0.0867682 | 78 |
| 8 | 7 | Year Trial was Completed | 4.75985 | 0.029131 | 31.367 | 2.13578e-08 | 1443 | 0.837932 | 0.359989 | 66 | 0.397523 | 0.528371 | 78 |

## 模型拟合摘要

| scenario_id | n_complete | high_ada_rows | high_ada_percent | parameters | null_deviance | residual_deviance | deviance_explained | mcfadden_pseudo_r2 | aic | formula | interpretation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all_public_rows_reference | 1443 | 449 | 0.311157 | 17 | 1789.39 | 1551.15 | 238.239 | 0.13314 | 1585.15 | high_ada ~ tcell + C(disease) + C(moa) + C(comed) + dose + dose_interval + trial_year + C(route) | In-sample proxy GLM fit; not cross-validated performance and not exact paper replication. |
| one_row_per_molecule | 66 | 13 | 0.19697 | 17 | 65.4948 | 45.2389 | 20.2559 | 0.309274 | 79.2389 | high_ada ~ tcell + C(disease) + C(moa) + C(comed) + dose + dose_interval + trial_year + C(route) | In-sample proxy GLM fit; not cross-validated performance and not exact paper replication. |
| one_row_per_molecule_disease_category | 78 | 13 | 0.166667 | 17 | 70.2875 | 49.992 | 20.2956 | 0.28875 | 83.992 | high_ada ~ tcell + C(disease) + C(moa) + C(comed) + dose + dose_interval + trial_year + C(route) | In-sample proxy GLM fit; not cross-validated performance and not exact paper replication. |

## 解释限制

- 场景 1 将同一药物的所有临床试验、适应证和给药方案压缩为一条代表记录；样本量从 2,666 条候选记录降为 110 条，完整模型仅 66 条。
- 场景 2 保留每个药物在每个原始 `Disease Indication Category` 中的一条代表记录，共 146 条，完整模型 78 条。
- 两个结果回答的是“不同去重口径下代理模型如何变化”，不是论文 Figure 6 的精确复现，也不是独立外部验证。
- 由于完整模型样本量小且参数较多，系数、p 值和优势比可能不稳定；应重点查看方向、量级和两场景一致性，不宜只按 0.05 阈值下结论。

## 最终交付文件

- 两张清洗后数据表：`data/one_row_per_molecule.csv` 与 `data/one_row_per_molecule_disease_category.csv`。
- 汇总工作簿：`IDC_dedup_scenarios_results.xlsx`，共 17 个工作表。
- 完整代表行选择审计：`artifacts/selection_audit_molecule.csv` 与 `artifacts/selection_audit_molecule_disease_category.csv`。
- 机械校验结果：两个输出键均无重复，入选记录均为组内排序第 1 名，工作簿导出前后公式错误扫描均为 0。
