# 求解器性能优化（方案 A 止血方案）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除求解器中 OpenDSS COM 调用的三大浪费点，将 8×1 配置耗时从 4–5h 降至 ~1.5–2h，零精度损失。

**Architecture:** 三个独立改动：合并日内滚动的重复 oracle 调用（`rolling_dispatch.py`）、收紧 full_recheck 触发门槛（`main.py` 参数调整）、每日单次 DSS 编译 + Edit 替代 New（`opendss_network_constraint_oracle.py`）。三项改动互不依赖，可独立实现和测试。

**Tech Stack:** Python 3.11, OpenDSS COM API (win32com), NumPy

---

## 文件变更总览

| 文件 | 改动类型 | 负责 |
|------|---------|------|
| `storage_engine_project/simulation/rolling_dispatch.py` | 修改 | 改动 1：合并 oracle 调用 |
| `storage_engine_project/main.py` | 修改 | 改动 2：收紧 full_recheck 门槛 |
| `storage_engine_project/simulation/opendss_network_constraint_oracle.py` | 修改 | 改动 3：单次编译 + Edit |

---

### Task 1: 改动 2 — 提高 full_recheck 触发门槛（最简单，先做）

**Files:**
- Modify: `storage_engine_project/main.py:294-296`

改动 2 最独立、风险最低，仅改参数值，优先实施。

- [ ] **Step 1: 修改 `_build_evaluator()` 中的三个阈值参数**

在 `storage_engine_project/main.py:294-296`，将：

```python
full_recheck_max_payback_years=15.0,
full_recheck_min_npv_to_investment_ratio=-0.10,
full_recheck_require_non_negative_cashflow=False,
```

改为：

```python
full_recheck_max_payback_years=10.0,
full_recheck_min_npv_to_investment_ratio=0.0,
full_recheck_require_non_negative_cashflow=True,
```

- [ ] **Step 2: 验证语法**

```bash
cd D:/storage_web_platform_3
.venv/Scripts/python.exe -c "from storage_engine_project.main import _build_evaluator; print('OK')"
```

Expected: `OK`（需在能导入 win32com 的环境下运行）

- [ ] **Step 3: 确认配置生效**

```bash
cd D:/storage_web_platform_3
.venv/Scripts/python.exe -c "
import argparse
from storage_engine_project.main import _build_evaluator
args = argparse.Namespace(prefer_opendss_in_full_recheck=True)
e = _build_evaluator(args)
print(f'payback={e.config.full_recheck_max_payback_years}')
print(f'npv_ratio={e.config.full_recheck_min_npv_to_investment_ratio}')
print(f'cashflow={e.config.full_recheck_require_non_negative_cashflow}')
"
```

Expected:
```
payback=10.0
npv_ratio=0.0
cashflow=True
```

- [ ] **Step 4: Commit**

```bash
git add storage_engine_project/main.py
git commit -m "perf: tighten full_recheck trigger thresholds (payback 15→10yr, NPV ratio -10%→0%, enable cashflow gate)"
```

---

### Task 2: 改动 1 — 合并 execute_day 中两轮 oracle 调用

**Files:**
- Modify: `storage_engine_project/simulation/rolling_dispatch.py:89-308`

核心思路：主循环中收集带 `capture_network_trace` 的 constraint，`_recompute` 中仅日末修正触及的小时重新调用 oracle，其余复用。

- [ ] **Step 1: 主循环增加 trace 收集和 constraint 保存**

在 `rolling_dispatch.py` 的 `execute_day()` 方法中（L138-L139，notes 初始化之后），添加 constraint 缓存列表：

```python
notes: list[str] = []
saved_constraints: list[Any] = []  # 新增：缓存每小时的 oracle 结果
```

然后在主循环 L151-L164 的 oracle 调用处，修改 `extra` 参数增加 `capture_network_trace`，并在调用后将 constraint 存入列表：

将 L163 行：
```python
extra={"plan_summary": plan.summary_dict()},
```

改为：
```python
extra={"plan_summary": plan.summary_dict(), "capture_network_trace": True},
```

并在 L164 行 `)` 之后添加：
```python
# line 164 后
            saved_constraints.append(constraint)
```

- [ ] **Step 2: _recompute 增加 saved_constraints 参数并分支复用**

修改 `_recompute()` 方法签名（L384-399），在参数列表末尾增加：

```python
# L388 处，oracle 参数之后
    saved_constraints: list[Any] | None = None,
```

在 `_recompute()` 的逐小时循环（L418-L519）中，将 oracle 调用替换为条件分支。L420-L433 原有代码块：

```python
            constraint = oracle.get_hour_constraint(
                ctx=ctx,
                day_index=plan.day_index,
                hour_index=t,
                actual_net_load_kw=float(actual_net[t]),
                planned_charge_kw=float(pch_exec[t]),
                planned_discharge_kw=float(pdis_exec[t]),
                planned_service_kw=float(psrv_exec[t]),
                rated_power_kw=float(plan.rated_power_kw),
                rated_energy_kwh=float(plan.rated_energy_kwh),
                effective_power_cap_kw=float(plan.effective_power_cap_kw),
                current_soc=float(soc[t]),
                extra={"plan_summary": plan.summary_dict(), "capture_network_trace": True},
            )
```

改为：

```python
            # 若执行值与计划值一致（非修正小时），复用主循环中已获取的 constraint
            planned_charge = float(pch_plan[t]) if t < len(pch_plan) else 0.0
            planned_discharge = float(pdis_plan[t]) if t < len(pdis_plan) else 0.0
            exec_differs = (
                abs(float(pch_exec[t]) - planned_charge) > 1e-6
                or abs(float(pdis_exec[t]) - planned_discharge) > 1e-6
            )
            if saved_constraints is not None and t < len(saved_constraints) and not exec_differs:
                constraint = saved_constraints[t]
            else:
                constraint = oracle.get_hour_constraint(
                    ctx=ctx,
                    day_index=plan.day_index,
                    hour_index=t,
                    actual_net_load_kw=float(actual_net[t]),
                    planned_charge_kw=float(pch_exec[t]),
                    planned_discharge_kw=float(pdis_exec[t]),
                    planned_service_kw=float(psrv_exec[t]),
                    rated_power_kw=float(plan.rated_power_kw),
                    rated_energy_kwh=float(plan.rated_energy_kwh),
                    effective_power_cap_kw=float(plan.effective_power_cap_kw),
                    current_soc=float(soc[t]),
                    extra={"plan_summary": plan.summary_dict(), "capture_network_trace": True},
                )
```

- [ ] **Step 3: 更新 execute_day 中 _recompute 的调用传参**

在 L230-L256（`_recompute` 调用处），增加 `saved_constraints` 参数：

将：
```python
        ) = self._recompute(
            ctx=ctx,
            plan=plan,
            oracle=oracle,
            actual_net=actual_net,
```

改为：
```python
        ) = self._recompute(
            ctx=ctx,
            plan=plan,
            oracle=oracle,
            saved_constraints=saved_constraints,
            actual_net=actual_net,
```

- [ ] **Step 4: 验证语法**

```bash
cd D:/storage_web_platform_3
.venv/Scripts/python.exe -c "from storage_engine_project.simulation.rolling_dispatch import RollingDispatchController; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add storage_engine_project/simulation/rolling_dispatch.py
git commit -m "perf: merge duplicate oracle calls in execute_day — reuse constraints from main loop in _recompute"
```

---

### Task 3: 改动 3 — 每日编译一次 + Edit 代替 New

**Files:**
- Modify: `storage_engine_project/simulation/opendss_network_constraint_oracle.py`

改动 3 最复杂。需要在 `_ComBackend` 类中添加 Edit 方法，在 `get_hour_constraint()` 中按小时分支 compile/Edit。

- [ ] **Step 1: 在 _ComBackend 类中添加 `edit_storage_dispatch` 方法**

在 `_ComBackend` 类的 `add_storage_dispatch()` 方法（L122-149）之后，添加新方法：

```python
    def edit_storage_dispatch(
        self,
        charge_kw: float,
        discharge_kw: float,
        rated_power_kw: float,
        rated_energy_kwh: float,
        current_soc: float,
    ) -> None:
        """更新已有的 Storage.__GPT_STORAGE 元件参数，不创建新元件。"""
        net_kw = float(discharge_kw) - float(charge_kw)
        state = "IDLING"
        if net_kw > 1e-6:
            state = "DISCHARGING"
        elif net_kw < -1e-6:
            state = "CHARGING"
        stored = min(max(float(current_soc), 0.0), 1.0) * 100.0
        self.text.Command = (
            f"Edit Storage.__GPT_STORAGE kW={net_kw:.6f} %stored={stored:.6f} State={state}"
        )
```

- [ ] **Step 2: 在 _ComBackend 类中添加 `disable_temp_generators` 方法**

在 `edit_storage_dispatch` 之后添加：

```python
    def disable_temp_generators(self) -> None:
        """将上一小时创建的临时发电机 kW 置零以禁用，避免 Delete 弹窗。"""
        for gen_name in list(self._temp_generators):
            try:
                self.text.Command = f"Edit Generator.{gen_name} kW=0"
            except Exception:
                pass
        self._temp_generators.clear()
```

- [ ] **Step 3: 在 OpenDSSConstraintOracle 中添加 `_hour_in_current_day` 状态**

修改 `OpenDSSConstraintOracle.__init__()`（L377 附近），在初始化末尾添加：

```python
self._current_dss_day: int | None = None
self._edit_fallback_count: int = 0
```

- [ ] **Step 4: 修改 `get_hour_constraint()` — 按小时分支 compile vs Edit**

在 `get_hour_constraint()` 方法中（L677-L679，try 块内的 `self._backend.compile` 调用处），将：

```python
try:
    runtime_entries = self._load_network_runtime_entries(ctx) if runtime_manifest_path else []
    self._backend.compile(self.master_dss_path)
    self._backend.clear_temp()
```

改为：

```python
try:
    runtime_entries = self._load_network_runtime_entries(ctx) if runtime_manifest_path else []
    is_first_hour_of_day = (self._current_dss_day != int(day_index))
    if is_first_hour_of_day:
        self._backend.compile(self.master_dss_path)
        self._current_dss_day = int(day_index)
    else:
        self._backend.disable_temp_generators()
    self._backend.clear_temp()
```

然后将储能 dispatch 部分（L769-L778），从始终 `add_storage_dispatch` 改为按是否首小时间分支：

将：
```python
self._backend.add_storage_dispatch(
    target_bus_name=target_bus,
    phases=3,
    kv_ln=kv_ln,
    charge_kw=float(planned_charge_kw),
    discharge_kw=float(planned_discharge_kw),
    rated_power_kw=float(rated_power_kw),
    rated_energy_kwh=float(rated_energy_kwh),
    current_soc=float(current_soc),
)
```

改为：
```python
if is_first_hour_of_day:
    self._backend.add_storage_dispatch(
        target_bus_name=target_bus,
        phases=3,
        kv_ln=kv_ln,
        charge_kw=float(planned_charge_kw),
        discharge_kw=float(planned_discharge_kw),
        rated_power_kw=float(rated_power_kw),
        rated_energy_kwh=float(rated_energy_kwh),
        current_soc=float(current_soc),
    )
else:
    self._backend.edit_storage_dispatch(
        charge_kw=float(planned_charge_kw),
        discharge_kw=float(planned_discharge_kw),
        rated_power_kw=float(rated_power_kw),
        rated_energy_kwh=float(rated_energy_kwh),
        current_soc=float(current_soc),
    )
```

- [ ] **Step 5: 添加 Edit fallback 机制**

在 `get_hour_constraint()` 的 except 块之前（L887 行 `except Exception as exc:`），添加对第一次 solve（baseline）失败的 fallback：

在 L679（compile/disable 之后，baseline solve 之前），如果 baseline solve 失败且非首小时间，回退到 compile 模式。将 L712 行：

```python
baseline_converged = self._backend.solve()
```

改为：

```python
baseline_converged = self._backend.solve()
if not baseline_converged and not is_first_hour_of_day:
    self._backend.compile(self.master_dss_path)
    self._current_dss_day = int(day_index)
    self._edit_fallback_count += 1
    # 重新注入负荷和储能（compile 后电路已清空）
    if runtime_entries:
        for entry in runtime_entries:
            self._backend.set_load_power(
                load_name=str(entry.get("load_name") or ""),
                bus_name=str(entry.get("bus_name") or ""),
                phases=3,
                kv_ln=self._normalize_distribution_base_kv(entry.get("kv_ln") or kv_ln),
                net_load_kw=self._runtime_kw_for_hour(entry, int(day_index), int(hour_index)),
                q_to_p_ratio=float(entry.get("q_to_p_ratio") or 0.25),
            )
        if target_load:
            self._backend.set_load_power(
                load_name=target_load,
                bus_name=target_bus,
                phases=self._to_int(ctx.meta.get("dss_phases"), 1),
                kv_ln=kv_ln,
                net_load_kw=float(actual_net_load_kw),
                q_to_p_ratio=q_to_p_ratio,
            )
    else:
        self._backend.set_or_add_target_load(
            target_load_name=target_load,
            target_bus_name=target_bus,
            phases=3,
            kv_ln=kv_ln,
            actual_net_load_kw=float(actual_net_load_kw),
            q_to_p_ratio=q_to_p_ratio,
            reference_kw=None if reference_kw in {None, ""} else float(reference_kw),
        )
    baseline_converged = self._backend.solve()
    metadata["edit_fallback"] = True
```

- [ ] **Step 6: 在最终返回的 metadata 中包含 fallback 计数**

在 `get_hour_constraint()` 的返回之前（构建 `HourlyNetworkConstraint` 处），添加：

```python
metadata["edit_fallback_count"] = self._edit_fallback_count
```

- [ ] **Step 7: 验证语法**

```bash
cd D:/storage_web_platform_3
.venv/Scripts/python.exe -c "from storage_engine_project.simulation.opendss_network_constraint_oracle import OpenDSSConstraintOracle; print('OK')"
```

Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add storage_engine_project/simulation/opendss_network_constraint_oracle.py
git commit -m "perf: single DSS compile per day with Edit for hourly storage/load updates"
```

---

### Task 4: 整体验证

- [ ] **Step 1: 验证三个文件可正常导入**

```bash
cd D:/storage_web_platform_3
.venv/Scripts/python.exe -c "
from storage_engine_project.simulation.rolling_dispatch import RollingDispatchController
from storage_engine_project.simulation.opendss_network_constraint_oracle import OpenDSSConstraintOracle
from storage_engine_project.main import _build_evaluator
print('All imports OK')
"
```

Expected: `All imports OK`

- [ ] **Step 2: 试运行一次求解（小参数）**

```bash
cd D:/storage_web_platform_3/storage_engine_project
.venv/Scripts/python.exe main.py --population-size 2 --generations 1 --target-id node09_联合汽车电子有限公司芜湖分公司5362030782-SCB9-10005 --output-dir outputs/perf_test 2>&1
```

验证要点：
- 求解器正常完成（返回码 0）
- `stdout.log` 中包含正常的求解日志
- 输出目录中生成了 result 文件
- 检查日志中是否有 `edit_fallback` 记录（预期极少）

- [ ] **Step 3: 对比优化前后耗时**

对比 `perf_test` 输出与历史同类参数运行耗时。预期：2 种群 × 1 代耗时明显低于优化前同等参数。

- [ ] **Step 4: Commit 测试输出检查结果**

```bash
git add -A
git commit -m "perf: verify optimization combined effect — all three changes working together"
```

---

## 实施顺序建议

```
Task 1 (改动2 参数调整) → Task 2 (改动1 合并调用) → Task 3 (改动3 Edit) → Task 4 (整体验证)
```

改动 2 最简单且独立，先做；改动 1 和 3 有轻微耦合（都涉及 `get_hour_constraint()` 的行为），按顺序做避免冲突。

## 回退策略

每项改动独立 commit，如有问题可逐个 revert：
```bash
git revert <commit-hash>
```
