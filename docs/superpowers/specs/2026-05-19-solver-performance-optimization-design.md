# 求解器性能优化 — 设计方案

> **状态：设计已确认，待进入实现计划。** 2026-05-19 商讨方案，2026-05-20 确认技术细节。

## 问题背景

8 种群 × 1 代配置下，求解器运行耗时 4–5 小时。根因是每个候选方案触发约 18,768 次 OpenDSS COM 调用（26 代表日 × 48 次/天 + 365 天 × 48 次/天），每次调用通过 COM 接口完整编译 Master.dss 并运行两次潮流求解。OpenDSS 调用占总运行时间的 85–95%。

### 储能运行的概念模型（已对齐）

- **日前计划**（`DayAheadScheduler.schedule_day()`）：用 CVXPY 凸优化，基于预测负荷/电价算次日 24h 计划。不涉及 OpenDSS。
- **日内滚动**（`RollingDispatchController.execute_day()`）：逐小时将计划功率注入真实配电网 OpenDSS 模型跑潮流校验，越限时裁剪功率。每小时间调一次 OpenDSS。
- **最终 SOC 轨迹**以日内滚动计算结果为准。

### 关键发现

1. **每小时间 oracle 被调用 2 次**：`execute_day()` 主循环（L151）和 `_recompute()`（L420）对同一小时间几乎相同的参数调用 oracle。区别仅在于日末 4 小时的 SOC 修正可能改变充放电值，以及第二轮要求 `capture_network_trace`。
2. **full_recheck 触发门槛过低**：payback ≤ 15yr、NPV/Invest ≥ -20%、cashflow 要求已关闭，导致几乎所有可行候选都触发 365 天全仿真。
3. **compile_each_call=True**：每小时间从零编译整条馈线，注释说明是为规避 OpenDSS Delete 命令的模态警告框。

## 用户约束与偏好

- **仿真质量**：Pareto 解集必须 OpenDSS 全年逐小时验证；GA 筛选可用代表日估算
- **目标速度**：~2 小时（8×1 配置），保守优化，仅消除浪费
- **改动范围**：最小改动，现有架构内

## 选定方案：方案 A — 止血方案

三个改动，零精度损失，预期从 4–5h → ~1.5–2h。

### 改动 1：合并 execute_day 中两轮重复的 oracle 调用

**位置**：`rolling_dispatch.py` `execute_day()` L140-256

**现状**：`execute_day()` 内有两个逐小时循环：
- 主循环（L140-205）：用日前计划值调用 oracle → 裁剪功率 → 更新 SOC
- `_recompute()`（L384-519）：日末修正后用执行值再次调用 oracle → 重算财务和网络指标

两轮调用在小时 0-19 传参完全一致（日末修正仅影响最后 4 小时，`terminal_soc_correction_hours=4`）。唯一区别是 `_recompute` 多传 `capture_network_trace: True`。

**方案**：
1. 主循环中增加 `capture_network_trace: True`，保存每小时的 constraint 对象
2. `_recompute()` 中：小时 0-19 直接复用已保存的 constraint；小时 20-23 若 exec 值与 plan 值有差异才重新调用 oracle

**效果**：每天 48 → 24-28 次 oracle 调用（-42~50%）

### 改动 2：提高 full_recheck 触发门槛

**位置**：`main.py` `_build_evaluator()` 的 `FitnessEvaluatorConfig`

| 参数 | 当前值 | 改为 | 理由 |
|------|--------|------|------|
| `full_recheck_max_payback_years` | 15.0 | **10.0** | >10 年回本不具备投资吸引力 |
| `full_recheck_min_npv_to_investment_ratio` | -0.20 | **0.0** | NPV 为负的方案不值得全年校验 |
| `full_recheck_require_non_negative_cashflow` | False | **True** | 年度现金流为负不可行 |

**精度论证**：26 代表日 fast_proxy 和 365 天 full_recheck 的排序相关性高。fast_proxy 阶段经济性明显不达标的方案在 full_recheck 下几无翻盘可能。

**效果**：触发 full_recheck 的候选从 ~6-8 降至 ~2-4（-50~70%）

### 改动 3：每日编译一次 + 小时间 Edit 更新

**位置**：`opendss_network_constraint_oracle.py` `_ComBackend` 类 + `get_hour_constraint()`

**现状**：每小时间 `compile(Master.dss)` 从零构建电路 → `New Storage.__GPT_STORAGE` → 两次 `Solve()`。编译是为了回避 OpenDSS Delete 命令可能弹模态警告框的问题。

**方案**：
- 第 0 小时：`compile` + `New Storage.__GPT_STORAGE`（不变）
- 第 1–23 小时：跳过 compile，用 `Edit` 原地更新
  - 负荷：`Edit Load.xxx kW=... kvar=...`
  - 储能：`Edit Storage.__GPT_STORAGE kW=... %stored=... State=...`
  - 临时发电机（反向潮流）：`Edit` 将 kW 设为 0 禁用，下小时按需唤醒
- 若 Edit 后 Solve 不收敛，单次回退到 compile 模式（添加 `_edit_fallback_count` 监控计数器）

**效果**：每天从 48 次电路编译降至 1 次（-98%）

### 改动边界说明

以下内容**不在本次改动范围**：
- **不**将 `opendss_only_for_full_recheck` 暴露给后端 API（即 GA 阶段保持当前 OpenDSS 参与方式不变）
- **不**修改 `DayAheadScheduler`（日前计划本身不调用 OpenDSS，无需优化）
- **不**引入并行化评估

## 合计预期效果

| 改动 | 影响 | 备注 |
|------|------|------|
| 合并重复调用 | 每日 oracle 调用 -42~50% | 48→24-28 次/天 |
| 提高 full_recheck 门槛 | full_recheck 候选 -50~70% | 仅经济性达标方案触发 |
| 每日单次编译 | 编译次数 -98% | 48→1 次/天 |
| **综合** | **从 ~4-5h → ~1.5-2h** | 保守估计 |

## 讨论记录

- 2026-05-19：瓶颈分析完成，确认 OpenDSS COM 调用占 85-95%
- 2026-05-19：用户确认约束（Pareto 全验证、保守优化、~2h 目标）
- 2026-05-19：选定方案 A，确认第 2 点门槛值，讨论第 3 点储能 Edit 可行性
- 2026-05-20：确认日前计划与日内滚动的概念模型
- 2026-05-20：确认改动 1 中 _apply_correction 仅影响最后 4 小时，小时 0-19 可安全复用
- 2026-05-20：确认改动 3 用 Edit + 禁用代替 Delete + New 以规避 OpenDSS 模态框问题
- 2026-05-20：设计文档定稿，进入 spec 自审
