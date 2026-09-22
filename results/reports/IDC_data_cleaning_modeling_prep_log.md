# IDC 数据清洗与建模前准备工作日志

## 0. 项目目的

本日志记录 IDC 数据从原始清洗标注表到最终建模就绪表的处理过程，重点标注：

- 数据清洗和去重规则；
- 分子名称、靶点和 MOA 的人工审核决定；
- 记录主键和来源字段修正；
- 目标变量、样本量和潜在数据泄漏处理；
- 建模前必须遵守的质量控制要求。

最终数据用于 ADA 频率连续建模或 ADA≥10% 二分类建模，不将研究来源、医学判断和模型假设混在一起。

---

## 1. 输入文件与初始检查

### 输入

- 原始 Notebook：`IDC_Clean_cleaned_annotated.ipynb`
- 原始建模表：`IDC_modeling_table_cleaned_annotated (2).xlsx`

### 初始数据规模

- 输入记录：2631 行
- 字段：89 列
- 必要字段均存在：
  - `molecule_inn_name`
  - `therapeutic_id`
  - `trial_id`
  - `ada_frequency_percent`
  - `target`
  - `mechanism_of_action`

### 关键数据处理点

1. 先检查字段完整性，再执行任何映射或分类。
2. 保留原始字段，并新增修正字段、审核字段和建模控制字段。
3. 所有重要修正均写入审计表，不依赖颜色或人工记忆。

---

## 2. 通用文本和标识符清洗

### 处理内容

对列名、试验 ID、治疗 ID、来源 ID 和分子名称执行：

- 去除首尾空格；
- 统一 Unicode 兼容形式；
- 替换不可见空格；
- 统一不同类型的连字符；
- 将空字符串转为缺失值。

### 关键分析判断

只处理格式问题，不对没有明确依据的生物学名称进行模糊替换。例如，未列入显式映射表的靶点名称保持原值。

---

## 3. 重复记录处理

### 发现的问题

原始表中的部分重复不是整行完全相同，而是：

- 原始观察字段相同；
- 旧的 `cohort_*`、`trial_*`、`INN_*`、`PR_*` 聚合字段不同；
- 这些聚合字段还出现了跨药物或跨治疗 ID 错配。

例如，同一 `CT0725_A1_001` 下，Adalimumab 和 Etanercept 的聚合字段曾互相混入。

### 处理规则

以聚合字段之前的原始观察字段作为重复判断依据，而不是用整行所有字段：

```python
aggregate_start = df.columns.get_loc("cohort_group_id")
source_observation_columns = list(df.columns[:aggregate_start])
redundant_source_mask = df.duplicated(
    subset=source_observation_columns,
    keep="first",
)
```

### 结果

- 删除冗余源观察副本：20 行；
- 保留真实的剂量、合并用药和时间点亚组；
- 最终建模行数：2611 行。

### 关键分析点

- 不能简单按 `idc_row_id` 删除重复，因为很多重复 ID 实际代表真实亚组。
- 不能按完整行去重，因为错配的聚合字段会掩盖真实重复。
- 被排除的20行保存在 `Excluded_Duplicates` 工作表中。

---

## 4. 11组重复主键的审核与修复

### CT0719、CT0722

重复行的原始观察字段相同，差异主要来自旧聚合字段。折叠为单条源观察记录。

### CT0725

同一内部 ID 下混入两个不同研究对象：

- Adalimumab：DOI `10.1001/archdermatol.2009.347`
- Etanercept：DOI `10.1111/j.1365-2133.2005.06688.x`

处理方式：

- Adalimumab 保留为 `CT0725_A1_001` / `CT0725`；
- Etanercept 改为 `CT0725B_A1_001` / `CT0725B`；
- 原始 ID 保存在 `idc_row_id_original` 和 `trial_id_original`。

### CT0736

原始研究包含三个 Infliximab 剂量层级与有/无 Methotrexate 亚组，共六条真实观察：

- A1：1 mg/kg；
- A2：3 mg/kg；
- A3：10 mg/kg；
- 每个剂量分别保留 MTX 和非 MTX 观察。

重新生成 `CT0736_A1_001` 至 `CT0736_A3_002`，并补全原始研究 DOI。

### CT0737

保留有/无免疫抑制治疗的两个亚组；将过窄的 `Methotrexate` 描述修正为 `Immunosuppressive therapy`。

### CT0742

同时存在总体队列和合并用药亚组。两者存在嵌套关系，均保留，但在 `record_dependency_note` 中标记：

> 不能在不分组的普通分析中把两行当作完全独立样本。

### CT0745

12% 和 38% 是同一原始研究中的 Methotrexate/非 Methotrexate 亚组：

- 恢复主研究 DOI `10.1136/ard.2006.065615`；
- 两个亚组重新编号为 A1/A2；
- 将错误的综述 DOI 从主要来源字段中移除。

### CT0751

一条记录的 `trial_id` 错写为 `CT0685`，但来源 DOI、行 ID 和研究内容均属于 `CT0751`。

处理方式：

- 两条记录统一为 `trial_id = CT0751`；
- 按有/无免疫调节治疗重新编号。

### CT0752

28天记录属于 CLASSIC I 诱导期；392天记录属于 CLASSIC II 维持期。

处理方式：

- 392天记录的来源 DOI 改为 `10.1136/gut.2006.106781`；
- 修正为维持期给药描述；
- 保留两个时间阶段，但设置相同的 `model_split_group`，防止训练集和测试集发生研究内泄漏。

### 主键审核结果

- 最终 `idc_row_id`：2611 个；
- 重复主键：0；
- 4 行存在纵向或嵌套依赖提示，需要分组/聚类分析。

---

## 5. Bevacizumab–CD22 分子身份错误

### 原始错误

一行记录同时具有：

- 分子名：Bevacizumab；
- `therapeutic_id = PR_0454`；
- 商品/开发代号：RG-7593；
- 靶点：CD22；
- MOA：CD22 内化并释放 MMAE。

### 审核结论

该行应为 Pinatuzumab Vedotin，而不是 Bevacizumab。

### 处理方式

- `molecule_inn_name` 改为 `Pinatuzumab Vedotin`；
- 原名称保存在 `molecule_inn_name_original`；
- 设置 `target_correction_flag = True`；
- 写入具体修正原因和来源。

### 最终检查

```python
assert not (
    df["molecule_inn_name"].eq("Bevacizumab")
    & df["target_clean"].eq("CD22")
).any()
```

该断言通过，残留错误映射为0行。

---

## 6. 靶点名称标准化

### 代表性映射

| 原始值 | 标准值 |
|---|---|
| `TNFa` | `TNF-α` |
| `PDL1` | `PD-L1` |
| `4-1BB` | `4-1BB/CD137` |
| `VEGF, Ang2` | `VEGF-A + Angiopoietin-2` |
| `Ang1/2` | `Angiopoietin-1/2` |

### 输出字段

- `target_clean`
- `target_group`
- `target_correction_flag`
- `target_correction_note`

### 结果

- `Other target`：0 行；
- 统一名称后未发现无法归类的靶点。

---

## 7. MOA 人工审核与分类决定

### Cetuximab

修正为：`Receptor blockade/antagonism`

原因：阻断 EGFR 配体结合和下游信号。

### Necitumumab

修正为：`Receptor blockade/antagonism`

原因：结合 EGFR 配体结合位点并阻断配体诱导的 EGFR 激活。

### Reslizumab

最终归类为：`Ligand neutralization`

原因：它结合并中和 IL-5 配体，阻止 IL-5 与受体结合。药品标签中的“antagonist”描述作用结果，不代表其直接结合 IL-5 receptor。

### GSK3174998

保持：`Receptor agonism`

原因：OX40 激动性抗体。

### Utomilumab

保持：`Receptor agonism`

原因：4-1BB/CD137 共刺激受体激动性抗体。

### Faricimab

补全 MOA：同时抑制 VEGF-A 和 Angiopoietin-2 两条血管生成通路。

### Trebananib

补全 MOA：结合 Angiopoietin-1/2，阻止其与 Tie2 受体相互作用，从而抑制血管生成。

### Isatuximab

最终归类为：`Immune-cell targeting/modulation`

原因：其作用包括 ADCC、ADCP、CDC、直接细胞死亡以及 CD38 酶活性调节，不能只归入补体抑制。

### 其他人工复核分子

以下分子的描述和分类也已写入人工审核日志：

- Moxetumomab pasudotox；
- Bimekizumab；
- Itepekimab；
- Oleclumab。

所有人工覆盖均记录在：

- `mechanism_of_action_reviewed`；
- `moa_review_flag`；
- `moa_review_note`；
- `moa_classification_source`。

最终结果：

- `Other/unclear` MOA：0 行；
- `Missing` MOA：0 行。

---

## 8. ADA 结局和数值质量控制

### ADA 数值

`ada_frequency_percent` 被转换为数值，并检查是否位于0–100范围。

结果：

- 超出范围：0 行。

### 二分类标签

重新计算：

```python
df["ada_high_10"] = (
    df["ada_frequency_percent"] >= 10
).astype("Int64")
```

同时保留原标签 `ada_high_10_original` 供审计。

结果：

- 标签不一致：0 行。

### ADA 百分比与计数一致性

对有完整计数的记录计算：

```python
ada_count_rate_percent = (
    n_ada_positive / n_ada_assessed * 100
)
```

如果与 `ada_frequency_percent` 相差超过1个百分点，则标记：

```text
ada_count_consistency_status = REVIEW_COUNT_MISMATCH
```

结果：

- 计数信息可用且一致：2506 行；
- 计数与频率不一致：95 行。

### 建模影响

- 频率连续模型：可使用全部2611行，但应进行敏感性分析；
- ADA≥10%二分类模型：可使用全部2611行；
- 二项计数模型：只使用 `binomial_count_model_eligible = TRUE` 的2506行，或先回查这95行的原始计数。

---

## 9. 目标泄漏处理

以下字段不进入最终 `Modeling_Data`，因为它们是目标变量或目标变量的聚合衍生量：

- `ada_fraction`；
- `n_ada_positive`；
- `cohort_ADA`；
- `trial_ADA`；
- `INN_ADA`；
- `PRID_ADA`；
- 对应的聚合 ID 和计数列；
- `ada_high_10_original`。

这些字段不是被删除，而是从建模数据表中排除，原始信息仍保留在输入文件和审计记录中。

---

## 10. 建模前最终检查

最终质量检查全部通过：

| 检查项 | 结果 |
|---|---:|
| 最终建模行数 | 2611 |
| 唯一 `idc_row_id` | 2611 |
| 重复主键 | 0 |
| 必要字段缺失 | 0 |
| ADA 超出0–100 | 0 |
| `ada_high_10` 不一致 | 0 |
| Bevacizumab–CD22残留 | 0 |
| 未归类靶点 | 0 |
| 未归类 MOA | 0 |
| 二项计数模型可用行 | 2506 |
| 嵌套/纵向依赖提示 | 4 |

---

## 11. 建模使用规则

### 目标变量

- 连续目标：`ada_frequency_percent`
- 二分类目标：`ada_high_10`

### 数据切分

使用 `model_split_group` 做分组切分。不能把同一研究的不同记录随机分到训练集和测试集，否则会产生研究级信息泄漏。

### 权重和计数

只有 `binomial_count_model_eligible = TRUE` 的记录才用于二项计数模型。

### 嵌套记录

`record_dependency_note` 非空的记录存在总体队列/亚组或不同随访阶段关系，应使用：

- GroupKFold；
- cluster-robust standard errors；
- mixed-effects model；
- 或敏感性分析中只保留一个代表性记录。

### 字段使用

详细字段角色见 `Feature_Guide` 工作表。ID、来源、审核字段和目标衍生字段不应直接作为生物学预测变量。

---

## 12. 最终交付文件

- `IDC_Clean_final_model_ready.ipynb`：可重复执行的清洗、审核和建模前处理代码；
- `IDC_modeling_table_final_model_ready.xlsx`：最终建模数据、排除记录、人工审核日志、QC汇总和字段说明；
- `IDC_data_cleaning_modeling_prep_log.md`：本工作日志。

---

## 13. 结论

分子身份、靶点、MOA、重复主键、数据泄漏和基本数值质量问题均已完成处理。当前数据可用于连续 ADA 频率和 ADA≥10% 二分类建模；若要进行基于阳性数/评估数的二项计数模型，应先处理或排除标记为 `REVIEW_COUNT_MISMATCH` 的95行。
