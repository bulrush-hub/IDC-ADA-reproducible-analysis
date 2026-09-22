# IDC paper_replication 工作日志

## 2026-08-08T22:41:07.542158+00:00 — 建立独立复现流程

1. 冻结来源：Frontiers Data Sheet 1、Table 1、Table 2；作者 GitHub V1.00 commit `049c8a5252396be64ac2a95a68a04384b57faa07`；用户提供 bioRxiv PDF。
2. 验证数据规模：218 therapeutics、222 sequence rows、3,334 ADA-frequency rows；公开数据与论文 Figure 1 数量口径一致。
3. 锁定方法：ADA `<10%` / `>=10%`；8 个因素；Table S6 残差自由度反推 1,216 完整案例及 Type-I 公式顺序。
4. 识别复现阻断：作者未公开逐行 epitope count、MOA/疾病/合并用药映射、剂量/间隔派生规则及分析代码。
5. 实现严格闸门：`paper_replication\data\manual\paper_derived_variables.csv` 不存在或不合格时，严格复现不运行。
6. 实现公开数据代理：所有替代变量均带 proxy 标识与逐行解析说明；代理结果不覆盖、不替代论文结果。
7. 完成顺序 deviance logistic GLM；代理完整案例数 1,443，严格状态 `BLOCKED_EXACT_SOURCE_FIELDS`。
8. 生成样本漏斗、来源哈希、字段可用性、逐行审核模板、Table S6 对照和 Figure 6 审计图。

## 关键分析点

- Figure 6 的“重要性”是顺序 deviance contribution，不是随机森林/TabPFN 的 feature importance，两者不能直接比较。
- 顺序 deviance 依赖公式顺序；交换 disease 与 MOA 等项会改变数值。
- 论文图按 deviance 排序，Table S6 的 residual df 才暴露实际加入顺序。
- 精确复现的首要瓶颈是作者派生设计矩阵，不是更换模型或继续调参。
- 公开 Clinical Trial 表在本分析候选中有重复 `IDC Row identifier`；流程不静默删除，而是使用来源行号构造唯一 `replication_row_key`，由作者分析行表决定最终保留口径。


## 复现差异定位阶段

9. 在固定代理完整案例 N=1,443 上运行确定性顺序敏感性分析：每个变量分别置于首位和末位，并保留论文推断顺序。
10. 运行完整模型逐项删减 likelihood-ratio 检验，提供不受变量进入顺序影响的条件贡献；该结果仍明确标记为公开数据代理。
11. 生成逐字段缺失率与 ADA 高低组分布，量化候选集到完整案例集的选择差异。
12. 新增 `order_sensitivity_summary.csv`、`order_sensitivity_runs.csv`、`drop_one_lrt.csv`、`proxy_missingness.csv`、`outcome_balance.csv` 和 `robustness_comparison.csv`，并纳入结果工作簿。


## 用户原始数据集接入

13. 接收用户提供的 `D:/DownLoads/IDC_DB_V1_All_Tables.xlsx`，复制为项目冻结源文件，不修改原始文件。
14. 二进制验证：用户文件与作者 GitHub V1.00 all-tables 文件大小和 SHA-256 完全一致。
15. 工作表级验证：Frontiers Table 2 虽容器哈希不同，但 Licensing、Therapeutic、Sequence、Clinical Trial、Variables Explained、Controlled Language 六表维度与全部单元格值一致，差异单元格数均为 0。
16. 将 all-tables 提取主输入切换为用户冻结副本；聚合表仍使用已冻结的 Frontiers Table 1。

## 原始数据接入最终验证

17. 核验切换前后 therapeutic、sequence、clinical_trial、variables_explained、controlled_language、aggregated_ada 六个处理 JSON 的 SHA-256 均保持一致。
18. 核验来源比较表共 12 行，全部 `exact_cell_values=TRUE`、`differing_cells=0`；用户文件与 GitHub 二进制一致，Frontiers 仅容器不同。
19. 重新导出并检查 20 张工作表；来源清单、来源比较、样本漏斗、README 和 QC 显示正常，导出前后公式错误扫描均为 0。
20. 再次测试严格模式：原始工作簿接入后仍因作者派生文件缺失而按设计阻断，说明“公开原始数据”与“Figure 6 作者设计矩阵”不是同一数据层。
21. Python 仍仅使用项目 `.venv`，未修改系统或全局 Python 环境。
