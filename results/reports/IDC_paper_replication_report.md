# IDC 论文复现报告：Figure 6 / Table S6

生成时间：2026-08-08T22:41:07.535789+00:00

## 结论

已建立与现有随机森林、TabPFN 完全分离的 `paper_replication` 流程。严格复现未运行：公开材料缺少作者生成的逐行派生变量与分析代码。

- 严格复现状态：`BLOCKED_EXACT_SOURCE_FIELDS`
- 公开数据代理运行：完成，完整案例 1,443 行；论文由残差自由度反推为 1,216 行。
- 代理模型中 deviance 最大的变量是 `Disease Indication`（88.232）。该排序不能作为论文结论的复现，因为 T-cell epitope、MOA、合并用药、剂量和间隔均使用了公开数据代理。
- 论文 Table S6 的残差自由度序列支持 Type-I（顺序）deviance；论文图按 deviance 大小展示，但模型加入顺序是：T-cell epitope → disease → therapeutic MOA → comedication → dose → interval → year → route。

## 为什么不能直接得到论文相同数值

作者公开了 IDC DS V1 原始表和聚合表，但没有公开 Figure 6 的分析代码，也没有公开以下逐行派生变量：NetMHCIIpan-4.3/OAS 过滤后的 T-cell epitope 数、四类 therapeutic immune MOA、五类疾病、三类合并用药、统一剂量、统一给药间隔。论文方法描述足以定义科学意图，但不足以唯一重建 1,216 行设计矩阵。

当前流程因此设置了严格闸门：只有把作者派生变量放入 `paper_replication/data/manual/paper_derived_variables.csv`，`--mode exact` 才会运行；缺字段、重复主键或样本数不符时会明确失败，而不会把代理结果伪装成精确复现。

## 公开数据代理实现

- 仅保留 `Therapeutic Exposed` 且 ADA frequency 非缺失的行，按 `<10%` / `>=10%` 构造二分类结局。
- 疾病映射为论文 Figure 4 的五组；肿瘤依据疾病描述中的血液系统关键词分为 hematological malignancy 与 solid tumor。
- therapeutic MOA 与 comedication 用透明关键词规则映射，供定位差异，不视为作者标签。
- 剂量从自由文本提取质量单位；`mg/kg` 采用 70 kg、`mg/m2` 采用 1.8 m2 的代理换算，均在逐行表中保留假设说明。
- 给药间隔从 `q2w`、`every N weeks`、weekly、给药日/周列表等表达式解析。
- 未公开的 T-cell epitope 数不被臆造；代理模型明确使用总序列长度，严格模式必须替换为作者方法的 epitope count。
- 使用 logistic GLM，并按 Table S6 残差自由度反推顺序计算逐项 deviance reduction 与卡方 p 值。

## 样本漏斗

| step | criterion | rows | note |
| --- | --- | --- | --- |
| 1 | Raw ADA-frequency rows | 3334 | User original IDC DB V1 / Clinical Trial |
| 2 | Therapeutic Exposed | 2705 | Paper population rule |
| 3 | Exposed with non-missing ADA frequency | 2666 | Binary outcome available |
| 4 | Sequence-length proxy available | 2365 | Not the paper epitope count |
| 5 | Dose proxy parsed | 2464 | Regex + stated body-size assumptions |
| 6 | Dose-interval proxy parsed | 1687 | Regex/list cadence parser |
| 7 | Trial completion year available | 2651 | Trial End Date |
| 8 | Complete public-data proxy model | 1443 | All eight proxy fields complete |
| 9 | Paper-inferred exact complete cases | 1216 | Inferred from Table S6 residual df |

## 代理结果（不可当作精确复现）

| variable | deviance | p_value |
| --- | --- | --- |
| Disease Indication | 88.2319 | 3.12612e-18 |
| Therapeutic Immune MOA Type | 58.9892 | 9.66415e-13 |
| T cell Epitope Content | 31.9017 | 1.62179e-08 |
| Year Trial was Completed | 31.367 | 2.13578e-08 |
| Route of Administration | 19.9198 | 0.000176368 |
| Dose Level | 7.15352 | 0.00748172 |
| Dose Interval | 0.559191 | 0.454586 |
| Comedication Immune MOA Type | 0.116222 | 0.943545 |

## 来源与版本

- 最终论文与方法：[Frontiers 文章](https://www.frontiersin.org/journals/immunology/articles/10.3389/fimmu.2026.1816949/full)
- 作者数据仓库：[IDC-DB GitHub](https://github.com/Immunogenicity-Database-Collaborative/IDC-DB)，冻结提交 `049c8a5252396be64ac2a95a68a04384b57faa07`
- Frontiers 的 Data Sheet 1 与 Table 1/2 已保存到 `paper_replication/data/raw/`，哈希见结果工作簿 `Source_Manifest`。
- 用户提供的 bioRxiv PDF 也已纳入哈希审计；Table S6 数值与最终 Frontiers 补充材料一致。

## 下一步获得严格复现所需材料

1. 优先向作者索取 Figure 6 的逐行分析表或脚本，尤其是 epitope count 与三类人工分组列。
2. 将逐行值填入生成的 `outputs/paper_replication/artifacts/manual_review_template.csv`，完成后保存为 `paper_replication/data/manual/paper_derived_variables.csv`。使用 `replication_row_key` 作为唯一键；公开表中的 `IDC Row identifier` 存在重复，保留作来源审计。
3. 运行 `.venv\Scripts\python.exe paper_replication\run_replication.py --mode exact`。
4. 核对完整案例 N=1,216、最终 residual df=1,199，以及每项 df/deviance/p 值；若不同，先检查模型顺序和缺失值口径，不调整结果来迎合论文。


## 复现差异定位与稳健性诊断

本节仅评估公开数据代理结果的稳定性，不改变严格复现状态，也不把代理分析解释为论文结果。

### 顺序敏感性

对每个变量分别执行“最先进入”和“最后进入”模型的确定性场景，并保留论文残差自由度所推断的原始顺序。Type-I deviance 的变化范围如下：

| variable | proxy_paper_order_deviance | minimum_deviance | median_deviance | maximum_deviance | deviance_range | range_to_paper_order_ratio |
| --- | --- | --- | --- | --- | --- | --- |
| T cell Epitope Content | 31.9017 | 23.3115 | 31.9017 | 46.4417 | 23.1302 | 0.725048 |
| Disease Indication | 88.2319 | 8.82896 | 88.2319 | 131.931 | 123.102 | 1.39521 |
| Therapeutic Immune MOA Type | 58.9892 | 21.2304 | 58.9892 | 125.944 | 104.713 | 1.77512 |
| Comedication Immune MOA Type | 0.116222 | 0.0322693 | 0.116222 | 13.7796 | 13.7473 | 118.284 |
| Dose Level | 7.15352 | 2.11069 | 7.15352 | 32.6931 | 30.5824 | 4.27516 |
| Dose Interval | 0.559191 | 0.0195543 | 0.559191 | 2.64384 | 2.62428 | 4.693 |
| Year Trial was Completed | 31.367 | 17.3934 | 31.367 | 55.5434 | 38.15 | 1.21624 |
| Route of Administration | 19.9198 | 19.7912 | 19.9198 | 120.405 | 100.614 | 5.05097 |

### 完整模型逐项删减检验

下表是在固定 1,443 行代理完整案例上，从完整模型中逐项删除变量所得的 likelihood-ratio deviance。它不依赖进入顺序，但仍依赖公开代理变量定义。

| variable | df | conditional_deviance | p_value | n_complete |
| --- | --- | --- | --- | --- |
| T cell Epitope Content | 1 | 27.7976 | 1.34691e-07 | 1443 |
| Disease Indication | 4 | 8.82896 | 0.0655198 | 1443 |
| Therapeutic Immune MOA Type | 3 | 21.2304 | 9.42895e-05 | 1443 |
| Comedication Immune MOA Type | 2 | 0.578062 | 0.748989 | 1443 |
| Dose Level | 1 | 3.85637 | 0.0495574 | 1443 |
| Dose Interval | 1 | 0.0536028 | 0.816909 | 1443 |
| Year Trial was Completed | 1 | 19.234 | 1.15636e-05 | 1443 |
| Route of Administration | 3 | 19.9198 | 0.000176368 | 1443 |

### 代理字段完整性

| variable | candidate_rows | available_rows | missing_rows | missing_percent | proxy_field |
| --- | --- | --- | --- | --- | --- |
| ADA binary outcome | 2666 | 2666 | 0 | 0 | high_ada |
| T cell Epitope Content proxy | 2666 | 2365 | 301 | 0.112903 | sequence_length_proxy |
| Disease Indication proxy | 2666 | 2666 | 0 | 0 | disease_indication_group_proxy |
| Therapeutic Immune MOA Type proxy | 2666 | 2666 | 0 | 0 | therapeutic_moa_type_proxy |
| Comedication Immune MOA Type proxy | 2666 | 2666 | 0 | 0 | comedication_moa_type_proxy |
| Dose Level proxy | 2666 | 2464 | 202 | 0.0757689 | dose_level_proxy |
| Dose Interval proxy | 2666 | 1687 | 979 | 0.367217 | dose_interval_days_proxy |
| Year Trial was Completed | 2666 | 2651 | 15 | 0.00562641 | trial_year_completed |
| Route of Administration proxy | 2666 | 2666 | 0 | 0 | route_group_proxy |
| Any required proxy-model field | 2666 | 1443 | 1223 | 0.45874 | complete-case intersection |

### ADA 结局分布

| stage | outcome | rows | stage_rows | percent_of_stage |
| --- | --- | --- | --- | --- |
| Exposed + outcome candidate | Low ADA (<10%) | 1788 | 2666 | 0.670668 |
| Exposed + outcome candidate | High ADA (>=10%) | 878 | 2666 | 0.329332 |
| Complete public-data proxy model | Low ADA (<10%) | 994 | 1443 | 0.688843 |
| Complete public-data proxy model | High ADA (>=10%) | 449 | 1443 | 0.311157 |


## 用户提供原始数据集验证

已将用户提供的 `IDC_DB_V1_All_Tables.xlsx` 冻结复制到 `paper_replication/data/raw/User_IDC_DB_V1_All_Tables.xlsx`，并改为 all-tables 数据提取的主输入。

- 用户文件与作者 GitHub V1.00 文件大小、二进制 SHA-256 完全一致。
- Frontiers Table 2 的 Excel 容器哈希不同，但六张工作表的维度和全部单元格值均与用户文件一致，差异单元格数为 0。
- 因此切换到用户原始文件不会改变治疗药物、序列或临床试验记录；它只强化了来源链和本地可迁移性。

| comparator_id | binary_identical_to_user | all_sheet_values_identical_to_user | sheet | user_rows | comparator_rows | user_columns | comparator_columns | exact_cell_values | differing_cells |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| author_github_v1_00 | True | True | Licensing | 2 | 2 | 1 | 1 | True | 0 |
| author_github_v1_00 | True | True | Therapeutic | 219 | 219 | 24 | 24 | True | 0 |
| author_github_v1_00 | True | True | Sequence | 223 | 223 | 8 | 8 | True | 0 |
| author_github_v1_00 | True | True | Clinical Trial | 3335 | 3335 | 43 | 43 | True | 0 |
| author_github_v1_00 | True | True | Variables Explained | 80 | 80 | 2 | 2 | True | 0 |
| author_github_v1_00 | True | True | Controlled Language | 16 | 16 | 20 | 20 | True | 0 |
| frontiers_table_2 | False | True | Licensing | 2 | 2 | 1 | 1 | True | 0 |
| frontiers_table_2 | False | True | Therapeutic | 219 | 219 | 24 | 24 | True | 0 |
| frontiers_table_2 | False | True | Sequence | 223 | 223 | 8 | 8 | True | 0 |
| frontiers_table_2 | False | True | Clinical Trial | 3335 | 3335 | 43 | 43 | True | 0 |
| frontiers_table_2 | False | True | Variables Explained | 80 | 80 | 2 | 2 | True | 0 |
| frontiers_table_2 | False | True | Controlled Language | 16 | 16 | 20 | 20 | True | 0 |
