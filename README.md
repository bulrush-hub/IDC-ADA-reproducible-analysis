# IDC ADA reproducible analysis

本仓库整理了 IDC（Immunogenicity Database Collaborative）数据的清洗、人工审核、ADA 建模、TabPFN-3 比较、开发集 OOF 验证、论文 Figure 6 / Table S6 公开数据代理复现，以及两种分子去重场景。

> 本仓库用于研究复现与方法审计，不构成临床决策工具。ADA 结果为研究/治疗臂层面的汇总数据，不能解释为患者个体风险。

## 主要结论

- 主清洗建模表包含 2,611 条记录，其中 2,506 条可用于二项计数模型；95 条记录的报告频率与阳性/评估人数存在不一致，已标记而非静默删除。
- 一分子一行的清洗表包含 110 个唯一分子；完整代理 GLM 仅使用其中 66 个完整案例。其余 44 个分子仍保留在清洗表中。
- 一分子 × 疾病类别一行的清洗表包含 146 行、110 个分子；完整代理 GLM 使用 78 行。
- 公开数据代理 GLM 的 1,443 个完整案例不能视为论文的精确复现；论文残差自由度反推的完整案例数为 1,216，且作者逐行派生变量尚未公开。
- TabPFN-3 在当前封存测试集的连续 ADA 预测与部分概率指标上优于随机森林，但开发集分组交叉验证中的优势并不全面一致。
- 按分子分组的验证显示，新分子外推仍是主要瓶颈；特征重要性只用于预测解释，不代表因果关系。

## 仓库结构

```text
.
├─ code/
│  ├─ cleaning/                 # 清洗与人工审核 Notebook
│  ├─ modeling/                 # 基线、TabPFN、OOF 与后处理脚本
│  ├─ paper_replication/        # 论文复现、去重和 grouped nested CV
│  └─ workbook_builders/        # 结果工作簿生成与验证脚本
├─ config/                      # 论文模型合同与发布值
├─ data/
│  ├─ raw/                      # 冻结的公开 IDC/Frontiers 输入
│  ├─ processed/                # 论文复现使用的标准化 JSON
│  ├─ cleaned/                  # 已审核的主建模表
│  └─ deduplicated/             # 两种去重数据表
├─ notebooks/                   # 已执行或可复查的分析 Notebook
├─ results/
│  ├─ reports/                  # 报告与工作日志
│  ├─ workbooks/                # 汇总工作簿
│  ├─ tables/                   # 机器可读结果表
│  ├─ figures/                  # 主要图片
│  └─ models/                   # 已训练的基线模型
├─ docs/                        # SOP、代码地图、数据与许可说明
├─ ENVIRONMENT.md
├─ requirements-*.txt
├─ run_all.ps1
└─ run_all.sh
```

## 快速开始

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

推荐先阅读 [执行流程](docs/EXECUTION_WORKFLOW.md) 和 [代码地图](docs/CODE_MAP.md)，再按阶段运行。`run_all.ps1` / `run_all.sh` 是带注释的入口示例；涉及 TabPFN 的步骤需要使用者先接受 Prior Labs 的 TabPFN-3 非商业许可并在本地创建 `.env`。

主模型的29项输入已在 [三层特征设计](docs/FEATURE_LAYER_DESIGN.md) 中划分为 Molecular、Clinical 和 Measurement 三层。三层分别服务于新分子外推、临床情境解释和检测/报告机会解释；目前只改变特征组织与输出标签，不追溯修改已经查看过的封存测试结果。

## 数据清洗中固定的人工审核决定

- 将错误的 `Bevacizumab + CD22 + MMAE` 记录修正为 `Pinatuzumab Vedotin`，同时保留原值和审核说明。
- `Cetuximab`、`Necitumumab`：`Receptor blockade/antagonism`。
- `Reslizumab`：`Ligand neutralization`。
- `GSK3174998`、`Utomilumab`：保留 `Receptor agonism`。
- 补全 `Faricimab`、`Trebananib` 的机制描述。
- `Isatuximab`：`Immune-cell targeting/modulation`。

完整依据和 QC 断言见 `docs/EXECUTION_WORKFLOW.md` 与 `results/reports/`。

## 复现层级

论文分析明确区分：

- `published`：论文/补充材料中的已发表值；
- `proxy`：使用公开 IDC 表和透明代理规则得到的诊断结果；
- `exact`：只有取得作者逐行派生变量并通过样本数和字段校验后才能运行。

禁止把 proxy 结果写成论文精确复现，也不为追求数值一致而反向调整映射或排除规则。

## 测试集和解释限制

- 当前 374 行封存测试集已经被查看，不再用于新的特征、阈值或校准方法选择。
- 后续选择只能在开发集 OOF / 嵌套交叉验证中完成，并在新外部数据中确认。
- Feature importance、SHAP、GLM 系数和 p 值均不证明因果作用。
- 分子去重改变了统计权重与 estimand，不只是删除“重复行”。

## 数据与模型许可

- IDC-DB 原始数据许可为 CC BY 4.0，许可文本保存在 `docs/IDC_DB_LICENSE.md`；使用数据时应引用原始 IDC-DB 项目。
- Frontiers 论文及补充材料保留其原始出版与版权条款。
- TabPFN-3 模型权重未包含在本仓库中；下载和使用受 Prior Labs TabPFN-3 Non-Commercial License 约束。
- 本仓库没有包含 `.env`、API key、虚拟环境、TabPFN checkpoint、缓存或临时审计转储。
- 除第三方材料外，本仓库代码尚未另行指定开源许可证；如需公开再利用代码，请由仓库所有者补充明确的软件许可证。

## 来源

- IDC-DB: https://github.com/Immunogenicity-Database-Collaborative/IDC-DB
- Frontiers article: https://www.frontiersin.org/journals/immunology/articles/10.3389/fimmu.2026.1816949/full
- TabPFN: https://github.com/PriorLabs/TabPFN
