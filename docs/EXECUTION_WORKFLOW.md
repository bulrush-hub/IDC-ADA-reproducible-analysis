# IDC 数据清洗、建模与论文复现：可复现执行流程原则

版本日期：2026-08-09  
适用范围：IDC 数据清洗、人工审核、基线模型、TabPFN-3 比较、开发集 OOF 验证、论文 Figure 6/Table S6 复现、两种去重场景及按分子分组的嵌套交叉验证。

## 1. 目的与复现边界

本流程的目标不是只生成一次结果，而是保证另一位分析者在取得相同输入、代码、依赖版本、随机种子和许可后，可以：

1. 重建同一份清洗与建模数据；
2. 追踪每项人工修正和每条记录的保留/排除原因；
3. 重现基线模型、TabPFN-3、论文公开数据代理分析和去重敏感性分析；
4. 区分“数据清洗后保留行”“模型完整案例”和“独立统计单位”；
5. 在结果不一致时定位到输入、映射、缺失值、抽样、模型顺序或软件环境，而不是反向调整结果。

必须区分三种复现层级：

- **数据复现**：相同原始输入经相同规则得到相同清洗表和样本漏斗。
- **分析复现**：相同设计矩阵、分组、模型、随机种子和软件版本得到一致或数值容差内一致的结果。
- **论文精确复现**：除公开原始数据外，还必须获得作者逐行派生变量和最终分析代码。当前公开数据代理分析不能标记为精确复现。

## 2. 总体原则

### 2.1 原始数据只读、派生结果分层保存

- 不直接修改用户原始 Excel、论文附件或作者仓库文件。
- 原始文件进入项目后保存冻结副本，记录文件大小、SHA-256、来源、下载/接收日期和用途。
- 清洗表、建模表、模型结果、图片、审计表和报告分别保存；不得用最终结果覆盖原始文件。
- 新分析使用新的输出目录。例如：
  - `outputs/`：主清洗、基线模型、TabPFN 和 OOF 验证；
  - `outputs/paper_replication/`：论文公开数据代理/严格复现；
  - `outputs/paper_replication_dedup_scenarios/`：两种去重场景；
  - `outputs/paper_replication_grouped_cv/`：按分子分组的嵌套交叉验证。

### 2.2 原始值、清洗值和人工审核值并存

关键字段不得原地静默覆盖。至少保留：

- 原始字段，如 `molecule_inn_name_original`；
- 标准化字段，如 `target_clean`、`moa_group`；
- 修正标志，如 `target_correction_flag`、`moa_review_flag`；
- 修正说明、证据、来源、审核者和审核日期；
- 建模可用性字段及排除原因。

自动规则只处理明确的格式、单位、词典映射和预先定义的分类。涉及分子身份、靶点、MOA 或研究设计含义的冲突必须进入显式人工审核表。

### 2.3 每次运行必须可审计

每次完整运行至少记录：

- UTC 时间戳；
- 输入文件路径和 SHA-256；
- Git 提交或代码版本；
- Python、关键包和模型权重版本；
- 随机种子；
- 各阶段样本数、事件数、独立分组数；
- 缺失值处理、排除规则和实际排除数量；
- 训练/验证/测试或内外层折的分组重叠检查；
- 运行状态、异常、修正和最终 QC 结论。

### 2.4 不允许静默回退

出现以下情况时应停止运行并报告，而不是自动换输入、换模型或降低标准：

- 输入哈希、工作表名称、字段或字段类型不符；
- 主键重复超出已审核规则；
- 训练组与验证/测试组发生禁止的分组重叠；
- 论文严格复现的逐行派生变量缺失或完整案例数不符；
- TabPFN 版本、权重或许可状态不符；
- 预测概率超出 `[0,1]`、回归预测非有限值或 OOF 预测不完整；
- 关键 QC 断言失败。

## 3. 环境与迁移原则

### 3.1 项目本地虚拟环境

所有 Python 依赖只能安装在项目目录内，不修改系统或全局 Python。

- `.venv`：清洗、基线模型、GLM、论文复现和常规统计；
- `.venv-tabpfn`：TabPFN/PyTorch 及相关验证，避免改变基线环境。

Windows：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-modeling.lock.txt

py -3.12 -m venv .venv-tabpfn
.\.venv-tabpfn\Scripts\python.exe -m pip install -r requirements-tabpfn.lock.txt
```

Linux：

```bash
python3.12 -m venv .venv
./.venv/bin/python -m pip install -r requirements-modeling.lock.txt

python3.12 -m venv .venv-tabpfn
./.venv-tabpfn/bin/python -m pip install -r requirements-tabpfn.lock.txt
```

迁移到 Linux 时：

- 迁移代码、锁文件、冻结数据、配置、日志和结果；
- 不复制 Windows 的 `.venv` 或 `.venv-tabpfn`，应在 Linux 重新创建；
- `.env` 中的访问令牌不得进入 Git、压缩包或报告；
- TabPFN 权重及其输出继续受非商业许可约束；
- 所有脚本从项目根目录运行，路径使用项目相对路径。

## 4. 数据分支与样本口径

以下数字来自不同数据分支，复现时必须分别核对：

| 数据分支/阶段 | 行数 | 含义 |
|---|---:|---|
| 主建模最终清洗表 | 2,611 | 去除 20 条冗余源观察副本后的研究/治疗臂记录 |
| 二项计数模型可用 | 2,506 | ADA 阳性计数与评估人数完整且通过一致性规则 |
| 计数-频率需复核 | 95 | 报告 ADA 百分比与计数计算值差异超过 1 个百分点 |
| 论文公开数据候选 | 2,666 | `Therapeutic Exposed` 且 ADA frequency 非缺失 |
| 公开数据代理完整案例 | 1,443 | 八个代理 GLM 字段全部完整 |
| 论文推断精确完整案例 | 1,216 | 根据论文 Table S6 残差自由度反推；当前缺作者逐行变量 |
| 每个分子一行 | 110 | 清洗后唯一分子数，允许模型字段缺失 |
| 上述场景完整代理 GLM | 66 | 110 个分子中的完整案例；44 个分子仍保留在清洗表中 |
| 每个分子×疾病一行 | 146 | 110 个分子形成 146 个分子-疾病组合 |
| 上述场景完整代理 GLM | 78 | 146 行中的完整案例 |

原则：**清洗后保留行数不等于模型样本量；行数不等于独立分子数；重复研究记录也不能被当作独立患者。**

## 5. 数据清洗与人工审核流程

### 5.1 冻结输入并检查结构

1. 将外部输入复制到项目内冻结目录，不依赖 `Temp` 或下载目录中的临时路径。
2. 记录 SHA-256，并检查必需工作表、字段、行数和字段类型。
3. 先输出原始缺失率、唯一值、主键重复和数值范围，再执行映射。
4. 当前论文复现原始 all-tables 已冻结在 `paper_replication/data/raw/`。
5. 当前主建模清洗最初使用的建模表来源于外部临时路径；若要从最初输入完整重建该分支，应先把该原始建模表也冻结到项目相对路径并记录哈希。现有 `outputs/IDC_modeling_table_cleaned_annotated_corrected.xlsx` 是已修正派生表，不应伪装成未处理原始文件。

### 5.2 通用格式清洗

- 统一 Unicode、首尾空格、不可见空格和连字符；
- 空字符串转换为缺失值；
- ID 保持文本类型，不进行可能丢失前导零的数值转换；
- 单位解析和文本分类必须保留原始文本及解析说明；
- 未进入显式词典的生物学名称不做模糊替换。

### 5.3 重复记录和依赖关系

- 不能简单按完整行去重，也不能仅按 `idc_row_id` 去重。
- 判断冗余副本时使用源观察字段，不让错误的旧聚合字段掩盖重复。
- 同一研究的真实剂量、合并用药、时间点或治疗臂均保留。
- 总体队列与亚组、不同随访阶段等依赖关系写入 `record_dependency_note`，并统一设置 `model_split_group`，避免跨分区泄漏。
- 被排除的 20 条冗余副本保留在审计工作表，不从证据链中消失。

### 5.4 分子、靶点与 MOA 人工审核闸门

已确认并应在规则表和断言中固定的关键决定：

- 将错误的 `Bevacizumab + CD22 + MMAE` 记录识别为 `Pinatuzumab Vedotin`，保留原名称和修正原因；
- `Cetuximab`、`Necitumumab` 归为 `Receptor blockade/antagonism`；
- `Reslizumab` 直接中和 IL-5 配体，归为 `Ligand neutralization`；
- `GSK3174998` 与 `Utomilumab` 保持 `Receptor agonism`；
- 补全 `Faricimab` 对 VEGF-A/Angiopoietin-2 的双通路抑制描述；
- 补全 `Trebananib` 阻断 Angiopoietin-1/2 与 Tie2 相互作用的描述；
- `Isatuximab` 归为 `Immune-cell targeting/modulation`，而不是仅按补体作用分类。

每项人工覆盖必须包含“原值、修正值、原因、证据来源、审核者、日期”。修改后必须运行反向断言，例如确认不存在 `Bevacizumab + CD22` 残留。

### 5.5 ADA 结局与计数检查

- `ada_frequency_percent` 必须是数值并位于 `[0,100]`；
- 二分类结局统一由 `ada_frequency_percent >= 10` 重新计算；
- 原二分类标签保留供审计，不直接信任；
- 若同时有 `n_ada_positive` 和 `n_ada_assessed`，重新计算百分比；差异超过 1 个百分点标记为 `REVIEW_COUNT_MISMATCH`；
- 连续模型和 `ADA >= 10%` 分类模型可保留 2,611 行；二项计数模型只使用 2,506 条合格记录，95 条不一致记录进入敏感性分析或回查。

### 5.6 目标泄漏控制

以下类型字段不得作为主分析预测变量：

- 目标本身及直接变换；
- 基于 ADA 结局聚合得到的 cohort/trial/INN/PR 统计；
- 阳性人数、ADA fraction、原始阈值标签；
- 记录 ID、DOI、来源和人工审核备注；
- 在预测时不可获得或由未来信息生成的字段。

## 6. 清洗完成的硬性 QC

主建模分支只有在以下检查全部通过后才能进入建模：

- 最终行数 2,611；
- `idc_row_id` 唯一值 2,611，重复主键 0；
- 必要字段缺失 0；
- ADA 超出 `[0,100]` 为 0；
- 重算 `ada_high_10` 与保留原标签不一致为 0；
- `Bevacizumab + CD22` 残留为 0；
- 未归类 target 和 MOA 为 0；
- `binomial_count_model_eligible=True` 为 2,506；
- 已标记嵌套/纵向依赖记录 4 条；
- 所有排除和人工覆盖均有审计记录。

可使用现有冒烟检查验证清洗 Notebook 的关键断言：

```powershell
Set-Location work
..\.venv\Scripts\python.exe verify_final_notebook.py
Set-Location ..
```

该脚本是关键逻辑冒烟检查，不替代对原始输入、工作簿格式和全部输出的完整复核。

## 7. 基线建模流程

### 7.1 固定问题、特征和拆分

- 连续结局：`ada_frequency_percent`；
- 二分类结局：`ada_high_10`；
- 二项计数模型：仅合格的阳性数/评估人数记录；
- 主分析使用 29 项预先固定特征，不使用分子名称和研究标识符；
- 按 `model_split_group` 隔离研究，禁止同一研究跨训练、验证和测试；
- 当前固定分区为训练 1,864、验证 373、测试 374；开发集为 2,237 行；
- 随机种子固定为 `20260802`；
- 所有填补、标准化和编码都在模型 Pipeline 内，仅在训练折拟合。

运行：

```powershell
.\.venv\Scripts\python.exe outputs\IDC_modeling_pipeline.py
```

Linux：

```bash
./.venv/bin/python outputs/IDC_modeling_pipeline.py
```

### 7.2 测试集使用原则

- 模型和超参数只能在开发集内部选择；
- 封存测试集只做一次最终评价；
- 测试结果被查看后，不再用该测试集选阈值、校准方法、特征或亚组规则；
- 后续新选择必须在开发集 OOF/嵌套 CV 内完成，并等待真正独立外部数据确认。

### 7.3 指标和解释

- 连续任务至少报告 MAE、RMSE、R²、均值偏差及误差分层；
- 二分类至少报告 ROC-AUC、PR-AUC、Brier、Log Loss、校准截距/斜率；
- F1 和 balanced accuracy 必须同时报告阈值，不能把测试集最优阈值作为无偏结果；
- 类别不平衡时，PR-AUC 必须与事件率比较；
- Feature importance、SHAP 和系数只解释预测贡献，不证明因果关系；
- 高相关变量会分摊重要性，不能仅凭单次排名删除特征。

## 8. TabPFN-3 公平比较流程

### 8.1 环境、许可和版本

- 使用独立 `.venv-tabpfn`；
- 固定 `tabpfn==8.2.0` 及其默认 TabPFN-3 checkpoint；
- 使用者本人接受 TabPFN-3 Non-Commercial License，并把令牌仅保存在未提交的 `.env`；
- 权重缓存位于 `work/tabpfn_model_cache`；
- 脚本启动时核对软件包版本，不允许自动回退到其他权重。

### 8.2 公平比较合同

- 使用与基线相同的 29 项信息、相同 2,237 行开发集、相同 374 行测试集和相同研究分组；
- TabPFN 使用原生数值/类别输入，不 one-hot、不缩放；基线随机森林保留其既有 Pipeline；
- 分类器和回归器均使用 8 个估计器，随机种子 `20260802`；
- 开发集使用 5 折 `GroupKFold(model_split_group)`；
- 测试集固定 0.5 分类阈值，不为 TabPFN 单独调阈值；
- 模型差异的不确定性按研究组进行 2,000 次配对 bootstrap。

运行顺序：

```powershell
.\.venv-tabpfn\Scripts\python.exe outputs\IDC_TabPFN_pipeline.py
.\.venv-tabpfn\Scripts\python.exe outputs\IDC_TabPFN_postprocess.py
```

Linux：

```bash
./.venv-tabpfn/bin/python outputs/IDC_TabPFN_pipeline.py
./.venv-tabpfn/bin/python outputs/IDC_TabPFN_postprocess.py
```

当前结论应表述为：TabPFN-3 在当前封存测试集的连续预测和部分概率指标上更好，但开发集分组 CV 优势并不全面一致，因此保留随机森林基线，并继续做跨研究、跨分子和外部验证。

## 9. 开发集 OOF、校准和全新分子压力测试

先运行只读的验证就绪度审计，再生成 OOF 预测和后处理结果：

```powershell
.\.venv-tabpfn\Scripts\python.exe outputs\IDC_validation_readiness.py
.\.venv-tabpfn\Scripts\python.exe outputs\IDC_oof_validation.py --schemes study,molecule
.\.venv-tabpfn\Scripts\python.exe outputs\IDC_oof_postprocess.py
```

原则：

- `study` 分组回答新研究记录泛化；
- `molecule` 分组回答全新分子压力测试；
- 两个问题分开报告，不能互相替代；
- 每行必须恰有一条 OOF 预测，每折禁止目标分组重叠；
- 校准、阈值敏感性和亚组分析只使用 2,237 行开发集；
- bootstrap 单位与验证任务一致，保留组内相关性；
- 当前测试集只有 3 个开发集中完全未见分子，不能被称为充分的外部分子验证。

## 10. 论文复现流程

### 10.1 明确区分 published、proxy 和 exact

- `published`：从论文/补充材料机械录入并核对的结果；
- `proxy`：由公开 IDC 表、透明映射和序列长度代理构成的诊断模型；
- `exact`：只有取得作者逐行派生变量并通过样本及字段校验后才能运行。

不得用 proxy 结果判断论文“错误”，也不得为了靠近论文结果修改代理映射或删除记录。

### 10.2 固定分析合同

- 模型类型：logistic GLM；
- 结局：ADA frequency `<10%` 与 `>=10%`；
- 八个因素的进入顺序固定为：T-cell epitope、disease、therapeutic MOA、comedication、dose、dose interval、trial year、route；
- Type-I deviance 会受进入顺序影响，因此同时报告顺序敏感性；
- 使用 drop-one likelihood-ratio test 提供固定完整模型中的条件贡献；
- 公开代理中序列长度不等于论文 NetMHCIIpan/OAS 筛选后的 T-cell epitope count；
- 严格复现预期完整案例为 1,216、最终 residual df 为 1,199。

运行公开代理：

```powershell
.\.venv\Scripts\python.exe paper_replication\run_replication.py --mode proxy
```

取得作者逐行数据后，填入 `paper_replication/data/manual/paper_derived_variables.csv`，再运行：

```powershell
.\.venv\Scripts\python.exe paper_replication\run_replication.py --mode exact
```

`--allow-sample-mismatch` 仅用于诊断，使用后不得声称精确复现。

## 11. 两种去重场景

候选集固定为 2,666 条 `Therapeutic Exposed` 且 ADA frequency 非缺失的公开数据记录。

### 11.1 场景定义

- 场景 1：每个标准化分子 INN 保留一条，输出 110 行；
- 场景 2：每个标准化分子 INN × 原始疾病大类保留一条，输出 146 行。

代表行选择顺序固定为：

1. 人工审核且八个代理字段完整；
2. 八个代理字段完整；
3. 已人工审核；
4. 其他；
5. 同层级内依次选择 ADA 最接近组内中位数、评估人数较大、源 Excel 行号较小的真实记录。

禁止拼接不同研究的字段来构造“更完整”的合成记录。

运行：

```powershell
.\.venv\Scripts\python.exe paper_replication\run_dedup_scenarios.py
```

复现检查点：

- 110 个唯一分子，组合键重复 0；完整代理 GLM 为 66，不是 110；
- 146 个分子-疾病组合，组合键重复 0；完整代理 GLM 为 78，不是 146；
- 选择审计覆盖全部 2,666 条候选记录；每组仅 `selection_rank_within_group=1` 入选；
- 44 和 68 条字段不完整记录仍保留在清洗输出中，只是不进入完整案例 GLM。

## 12. 去重对预测的影响：按分子分组的嵌套 CV

运行：

```powershell
.\.venv\Scripts\python.exe paper_replication\run_grouped_nested_cv.py
```

固定设计：

- 外层：5 折、10 次重复，按标准化分子分组；
- 内层：4 折按分子分组，用于选择 L2 正则化；
- L2 网格：`[0.001, 0.01, 0.1, 1.0, 10.0]`；
- 随机种子：`20260809`；
- 数值缩放和类别编码只在当前训练折拟合；
- 95% 区间采用 2,000 次分子聚类 bootstrap；
- Feature importance 在外层测试折置换，每变量每折 3 次，以 log loss 增量衡量。

同时报告 row-weighted 和 molecule-balanced 指标。前者受记录较多的分子影响，后者让每个分子总权重相同；二者回答不同问题。

当前结果的解释边界：去重改善了独立性和验证设计，但 66/78 个完整案例中只有 13 个 High ADA 事件，不能因为训练内拟合更好就断言新分子预测能力提高。

## 13. 缺失值图与其他图形的统计口径

缺失值图只展示对建模或数据获取真正有意义的源字段。以下字段不得混入普通缺失率排名：

- 以 `_note` 结尾的审核说明字段；空值通常表示“无问题”，不是数据缺失；
- correction/review flag、内部 QC、行号和辅助键；
- 从其他字段派生、可重新计算的 helper 列；
- 只适用于特定药物或分子类型的结构性不适用字段；
- 目标变量及其聚合衍生字段。

图形必须标明：

- 分母及纳入数据范围；
- 行数、独立研究数或独立分子数；
- 是否为完整案例、加权结果或分组结果；
- 重要性指标的方向和单位；
- 不确定性区间及其重采样单位。

任何图形修改后都应核对其底层 CSV/JSON 数值，并确认图片没有截断标签、重复标题、内部变量名或误导性的 `_note` 字段。

## 14. Feature importance 的使用原则

Feature importance 必须做，但用途限定为模型解释和数据质量排查：

- 基线模型可报告 permutation importance、SHAP 和线性/GLM 系数；
- 论文去重预测比较优先使用外层测试折 permutation importance；
- 不在同一批数据上同时选择特征并报告最终性能，除非选择过程完整嵌入内层 CV；
- 置信区间跨 0、不同折方向变化或高度相关变量排名交换时，应报告“不稳定”；
- 不把预测重要性解释为药物机制的因果效应；
- 不因单次 importance 较低就自动删除特征。

## 15. 输出、日志和验收

每个分析分支至少产生：

- 机器可读的 CSV/JSON；
- 人工可读的 Markdown 报告和工作日志；
- 逐行选择/预测/排除审计；
- 样本漏斗、性能、校准和必要的敏感性结果；
- 环境与输入元数据；
- 若生成 Excel，需扫描公式错误并逐工作表渲染检查。

验收时按以下顺序核对：

1. 输入哈希和来源一致；
2. 字段、类型、主键和样本漏斗一致；
3. 人工修正和排除审计齐全；
4. 分组重叠为 0；
5. 预处理只在训练折拟合；
6. OOF/测试预测完整且数值合法；
7. 指标、置信区间、事件率和权重口径一致；
8. 图表分母、标签和底层表一致；
9. 结果目录没有覆盖其他分析分支；
10. 日志记录运行异常、修复及最终 PASS/FAIL。

## 16. 推荐执行顺序

1. 冻结原始输入并生成哈希清单；
2. 建立/重建 `.venv` 和 `.venv-tabpfn`；
3. 执行数据清洗 Notebook，完成人工审核闸门和清洗 QC；
4. 运行基线建模并冻结拆分和基线模型；
5. 运行 TabPFN 公平比较；
6. 锁定已查看的测试集，不再用于新选择；
7. 运行验证就绪度、研究组 OOF 和分子 OOF；
8. 独立运行论文 proxy/exact 复现流程；
9. 生成两种去重数据表和代理 GLM 敏感性结果；
10. 使用按分子分组的嵌套 CV 比较三种数据口径；
11. 核对 Feature importance、校准、阈值和 ADA 特异性误差；
12. 完成报告、工作日志、机器可读结果和最终 QC。

## 17. 结论性原则

- 先保证数据身份、来源链和独立性，再比较模型性能。
- 样本量必须同时报告行数、完整案例数、独立研究数、独立分子数和事件数。
- 论文结果、公开数据代理结果和预测验证结果是不同证据层级，不能相互替代。
- 去重是一种 estimand 和权重改变，不只是技术性删除重复行。
- 测试集只能评价一次；后续选择必须回到开发集 OOF/嵌套 CV。
- Feature importance 必须带验证设计和不确定性，且不作因果解释。
- 任何无法解释的数字差异都应保留并定位原因，不以“调到一致”为目标。

## 18. 现有关键入口与记录

- 环境说明：`ENVIRONMENT.md`
- 清洗执行 Notebook：`outputs/IDC_Clean_final_model_ready.ipynb`
- 清洗与建模前日志：`outputs/IDC_data_cleaning_modeling_prep_log.md`
- 基线建模：`outputs/IDC_modeling_pipeline.py`
- TabPFN：`outputs/IDC_TabPFN_pipeline.py`
- 验证就绪度：`outputs/IDC_validation_readiness.py`
- 开发集 OOF：`outputs/IDC_oof_validation.py`
- OOF 后处理：`outputs/IDC_oof_postprocess.py`
- 论文复现说明：`paper_replication/README.md`
- 论文复现：`paper_replication/run_replication.py`
- 两种去重：`paper_replication/run_dedup_scenarios.py`
- 按分子分组嵌套 CV：`paper_replication/run_grouped_nested_cv.py`

