# IDC TabPFN-3 与当前模型性能比较

## 结论摘要

TabPFN-3 在封存测试集上显著改善连续 ADA 频率预测：MAE 从 10.585 降至 7.601 个百分点，R² 从 0.461 提高到 0.617。二分类的 ROC-AUC、PR-AUC、Brier 和 Log Loss 也优于当前随机森林；但使用未经调优的固定 0.5 阈值时，F1 与平衡准确率略低。

开发集 5 折分组交叉验证的优势没有测试集那么一致：TabPFN 连续 MAE 更低，但连续 R²、二分类 ROC-AUC 等若干指标与随机森林接近或略差。因此应把 TabPFN 视为值得保留的候选模型，而不是仅凭一次测试集全面替换当前模型。

## 独立测试集

| 结局 | 指标 | 当前随机森林 | TabPFN-3 | 点估计更优者 |
|---|---|---:|---:|---|
| continuous | MAE | 10.5846 | 7.6006 | TabPFN |
| continuous | RMSE | 15.1422 | 12.7748 | TabPFN |
| continuous | R2 | 0.4613 | 0.6166 | TabPFN |
| binary | ROC_AUC | 0.8551 | 0.8871 | TabPFN |
| binary | PR_AUC | 0.7680 | 0.7903 | TabPFN |
| binary | F1 | 0.7013 | 0.6728 | Random forest |
| binary | Balanced_Accuracy | 0.7755 | 0.7549 | Random forest |
| binary | Brier | 0.1587 | 0.1282 | TabPFN |
| binary | Log_Loss | 0.4936 | 0.4079 | TabPFN |

## 开发集 5 折 GroupKFold

| 结局 | 指标 | 当前随机森林 | TabPFN-3 | 均值更优者 |
|---|---|---:|---:|---|
| continuous | MAE | 12.2875 ± 1.1039 | 11.6579 ± 0.9979 | TabPFN |
| continuous | RMSE | 19.3780 ± 2.2962 | 19.3956 ± 1.9689 | Random forest |
| continuous | R2 | 0.2702 ± 0.1316 | 0.2580 ± 0.1822 | Random forest |
| binary | ROC_AUC | 0.8046 ± 0.0550 | 0.7935 ± 0.0172 | Random forest |
| binary | PR_AUC | 0.6949 ± 0.1052 | 0.6751 ± 0.0754 | Random forest |
| binary | F1 | 0.5960 ± 0.0968 | 0.5797 ± 0.0539 | Random forest |
| binary | Balanced_Accuracy | 0.7006 ± 0.0640 | 0.6964 ± 0.0342 | Random forest |
| binary | Brier | 0.1703 ± 0.0216 | 0.1680 ± 0.0157 | TabPFN |

## 按研究组配对 bootstrap

`TabPFN improvement` 已统一指标方向：正值表示 TabPFN 更好。重采样单位为 `model_split_group`，重复 2000 次。

| 结局 | 指标 | TabPFN improvement | 95% CI | 判断 |
|---|---|---:|---:|---|
| continuous | MAE | 2.9840 | [1.4495, 4.5666] | TabPFN improvement supported |
| continuous | RMSE | 2.3675 | [0.3632, 4.5222] | TabPFN improvement supported |
| continuous | R2 | 0.1553 | [0.0211, 0.4309] | TabPFN improvement supported |
| binary | ROC_AUC | 0.0320 | [-0.0067, 0.0821] | Difference uncertain |
| binary | PR_AUC | 0.0223 | [-0.0327, 0.0776] | Difference uncertain |
| binary | F1 | -0.0285 | [-0.0878, 0.0192] | Difference uncertain |
| binary | Balanced_Accuracy | -0.0206 | [-0.0565, 0.0112] | Difference uncertain |
| binary | Brier | 0.0305 | [0.0092, 0.0504] | TabPFN improvement supported |
| binary | Log_Loss | 0.0858 | [0.0301, 0.1379] | TabPFN improvement supported |

## 方法与限制

- 比较使用相同 29 个特征、相同研究组拆分和相同 374 行封存测试集。
- TabPFN 使用官方推荐的原生类别处理，不做 one-hot 或缩放；随机森林保留既有预处理。
- 二分类 F1 与平衡准确率按固定 0.5 阈值计算，没有在测试集调阈值。
- Feature importance 为测试集置换重要性，只表示预测贡献，不表示因果关系。
- 本次环境为 CPU 版 PyTorch；完整流水线约 20.6 分钟。速度不能代表 GPU 部署性能。
- TabPFN-3 权重和输出受非商业许可约束；生产或商业使用需另行确认授权。
- 测试集仍属于当前数据库的内部独立拆分，不能替代外部验证；对全新分子的外推风险仍需单独评估。
