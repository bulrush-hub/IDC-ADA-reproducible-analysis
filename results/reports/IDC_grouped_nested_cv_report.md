# IDC 按药物分组的嵌套交叉验证报告

生成时间：2026-08-09T00:30:08.054460+00:00

## 评估问题

本流程回答两种去重操作对“预测新药物分子 High ADA（ADA frequency >=10%）”的影响。所有外层和内层划分均以标准化分子名为分组键；同一药物不会同时出现在训练与验证数据中。

## 核心性能

| scenario_label | n_rows | n_groups | positive_rows | prevalence | weighting | roc_auc | roc_auc_ci_low | roc_auc_ci_high | average_precision | average_precision_ci_low | average_precision_ci_high | balanced_accuracy_0_5 | brier_score | log_loss | calibration_gap_predicted_minus_observed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| All public rows (grouped by molecule) | 1443 | 66 | 449 | 0.31116 | row_weighted | 0.56851 | 0.46637 | 0.65925 | 0.33237 | 0.20568 | 0.49473 | 0.48336 | 0.2286 | 0.64824 | 0.018075 |
| All public rows (grouped by molecule) | 1443 | 66 | 449 | 0.23936 | molecule_balanced | 0.54332 | 0.43087 | 0.65916 | 0.30386 | 0.18165 | 0.48242 | 0.54044 | 0.19003 | 0.56641 | 0.072848 |
| One row per molecule | 66 | 66 | 13 | 0.19697 | row_weighted | 0.40639 | 0.24238 | 0.57987 | 0.1738 | 0.10003 | 0.30864 | 0.5 | 0.1616 | 0.50722 | 0.00020628 |
| One row per molecule | 66 | 66 | 13 | 0.19697 | molecule_balanced | 0.40639 | 0.23656 | 0.58782 | 0.1738 | 0.10029 | 0.3172 | 0.5 | 0.1616 | 0.50722 | 0.00020628 |
| One row per molecule × disease category | 78 | 66 | 13 | 0.16667 | row_weighted | 0.39408 | 0.22094 | 0.58835 | 0.16359 | 0.082187 | 0.35207 | 0.5 | 0.14066 | 0.45751 | 0.00011404 |
| One row per molecule × disease category | 78 | 66 | 13 | 0.19697 | molecule_balanced | 0.39671 | 0.22265 | 0.58519 | 0.19525 | 0.10122 | 0.39377 | 0.5 | 0.16099 | 0.50694 | -0.030651 |

## 泄漏控制的置换重要性（每个场景前三项）

| scenario_id | variable | mean_delta_log_loss | ci_low | ci_high | positive_fraction |
| --- | --- | --- | --- | --- | --- |
| all_public_rows_grouped | Year Trial was Completed | 0.0071219 | -0.0044714 | 0.033849 | 0.74 |
| all_public_rows_grouped | Dose Level | 0.0038718 | -0.010597 | 0.019701 | 0.62667 |
| all_public_rows_grouped | T cell Epitope Content | 0.0026426 | -0.024106 | 0.016312 | 0.79333 |
| one_row_per_molecule | Dose Interval | 0.0061542 | -0.013906 | 0.052631 | 0.74 |
| one_row_per_molecule | Dose Level | 0.0054097 | -0.064142 | 0.062984 | 0.76667 |
| one_row_per_molecule | Therapeutic Immune MOA Type | -0.00013411 | -0.027187 | 0.017447 | 0.5 |
| one_row_per_molecule_disease_category | Dose Level | 0.0039776 | -0.025036 | 0.060546 | 0.80667 |
| one_row_per_molecule_disease_category | Dose Interval | 0.0026442 | -0.0092935 | 0.060979 | 0.62667 |
| one_row_per_molecule_disease_category | Therapeutic Immune MOA Type | 0.00034326 | -0.0064761 | 0.015727 | 0.68 |

## 解释限制

- 结果是公开代理变量上的内部、按药物分组交叉验证，不是外部验证，也不是论文 Figure 6 的精确复现。
- 去重场景只有 66 或 78 行、13 个 High ADA 事件；置信区间和校准结果可能很宽。
- 未去重口径虽然有 1,443 行，但只有 66 个独立药物，置信区间按药物聚类而不是把 1,443 行视为独立样本。
- Average precision 必须与本场景 High ADA 患病率比较；普通 accuracy 在类别不平衡时可能产生误导。
- 置换重要性为外层测试集 log loss 的变化，负值或跨 0 表示贡献不稳定；它不是因果效应。

## 最终判断

- 以“每个药物总权重相同”为主要口径时，三种模型的 ROC-AUC 95% 区间全部覆盖 0.5。
- 三种模型的 Brier score 与 log loss 均劣于仅预测本场景患病率的常数模型。
- 两种去重模型在 0.5 阈值下均未预测出任何 High ADA，balanced accuracy 均为 0.5。
- 8 个变量在三种口径下的外层置换重要性区间均跨越 0；当前没有可确认的稳定预测因子。
- 因此，去重改善了验证设计和数据独立性，但没有改善公开代理变量对“新药物”High ADA 的预测能力；当前主要限制是独立药物数和 High ADA 事件数，而不是选择哪一种去重口径。

## 交付内容

- `IDC_grouped_nested_cv_results.xlsx`：12 个工作表，包含方法、队列、性能、校准、重复结果、置换重要性、正则化、折诊断、OOF 预测和 QC。
- `results/`：可直接用于后续统计与绘图的汇总 CSV。
- `artifacts/oof_predictions.csv`：1,587 行逐记录 OOF 概率。
- `artifacts/nested_tuning_results.csv` 与 `outer_fold_diagnostics.csv`：完整内层调参和外层分组审计。
