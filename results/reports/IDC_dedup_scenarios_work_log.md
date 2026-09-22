# IDC 去重场景工作日志

## 2026-08-08T23:10:49.856175+00:00 — 新建独立结果分支

1. 读取用户确认的 IDC DB V1 原始 all-tables 数据，不修改原始工作簿。
2. 复用现有公开数据清洗和代理变量规则，候选集为 Therapeutic Exposed 且 ADA frequency 非缺失的 2,666 行。
3. 场景 1 按标准化药物 INN 名称分组，每种药物保留一条真实来源记录。
4. 场景 2 按标准化药物 INN 名称与原始 `Disease Indication Category` 分组，每个药物-疾病大类保留一条真实来源记录。
5. 代表行选择优先级为：人工审核且字段完整 > 字段完整 > 人工审核 > 其他；同层级按 ADA 最接近组内中位数、患者数较大、来源行号较小排序。
6. 验证场景 1 分组键唯一，输出 110 行；场景 2 组合键唯一，输出 146 行。
7. 在两个场景上分别运行与 paper_replication 相同的八因素顺序 logistic GLM、drop-one LRT 和顺序敏感性分析。
8. 所有文件写入 `outputs/paper_replication_dedup_scenarios/`；原始 `outputs/paper_replication/` 未写入。
9. Python 依赖仅使用项目 `.venv`，未修改系统或全局 Python。

## 2026-08-08T23:17:59Z — 最终校验与交付整理

1. 场景 1 数据表复核为 110 行、110 个唯一 `molecule_key`，重复分组数为 0。
2. 场景 2 数据表复核为 146 行、146 个唯一 `molecule_key + disease_category_key` 组合，重复分组数为 0。
3. 两份选择审计各覆盖完整的 2,666 行候选集；场景 1 有 110 条、场景 2 有 146 条 `selection_rank_within_group = 1`，所有入选行均为本组第 1 名。
4. 完整代理 GLM 样本量复核为 66 与 78；两种场景均生成 8 个顺序 deviance 项，最终残差自由度分别为 49 与 61。
5. 生成 17 个工作表的独立结果工作簿，包含两张去重数据表、S6 对照、系数、顺序敏感性、drop-one LRT、结局分布与 QC。
6. 工作簿导出前、导出后公式错误扫描均为 0；17 个工作表均已逐页渲染并完成视觉检查。
7. 修正宽数据表标题在首屏不可见及 README 时间戳显示问题后重新导出并复核。
8. 最终工作簿 SHA-256：`3ACE8AAA5249B6498F1501E9FC239288AC92AC664E5F90F6F4A4648047F436AF`。
9. 原 `outputs/paper_replication/artifacts/replication_metadata.json` 仍保持生成时间 `2026-08-08T22:41:07.568124+00:00`，本流程未写入原结果目录。
