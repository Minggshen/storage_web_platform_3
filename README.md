# 工商业储能优化平台

> Commercial & Industrial Energy Storage Optimization Platform

面向配电网的工商业电池储能系统优化平台。提供可视化拓扑建模、日前调度、遗传算法寻优、生命周期财务建模和 Web 图形化工作流。

## 环境要求

- **Python** 3.11.x
- **Node.js** 22+
- **pnpm** >= 10
- [OpenDSS](https://www.epri.com/pages/sa/opendss)（可选，仅 Windows，用于潮流计算校验）
- Git

## 快速开始

```bash
# 1. 克隆项目
git clone git@github.com:Minggshen/storage_web_platform_3.git
cd storage_web_platform_3

# 2. Python 环境
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS / Linux

pip install -e ".[full,dev]"

# 3. 前端环境
cd frontend
pnpm install

# 4. 配置环境变量
cp frontend/.env.example frontend/.env   # 前端
cp .env.example .env                     # 后端

# 5. 启动后端 API（另开终端）
cd backend
uvicorn storage_fastapi_backend:app --reload --host 127.0.0.1 --port 8000

# 6. 启动前端开发服务器
cd frontend
pnpm dev                              # → http://localhost:5173
```

API 文档自动生成于 `http://localhost:8000/docs`。

## 项目结构

```
├── backend/                    FastAPI 后端
│   ├── storage_fastapi_backend.py  API 入口
│   └── data/projects/          持久化项目数据
├── frontend/                   React + Vite + TypeScript 前端
│   └── src/
│       ├── app/                路由 + 布局
│       ├── pages/workspace/    6 步工作流页面
│       ├── components/         UI 组件 + 通用组件
│       ├── services/           API 调用封装
│       └── types/              TypeScript 类型定义
├── storage_engine_project/     核心优化引擎
│   ├── simulation/             日前调度 / 滚动调度 / 年度仿真
│   ├── optimization/           遗传算法优化器（Lemming）
│   ├── economics/              生命周期财务建模
│   ├── config/                 配置模型
│   └── main.py                 CLI 入口
├── pyproject.toml              Python 依赖声明
└── .github/workflows/          CI/CD 流水线
```

## 工作流

1. **项目创建** — 新建优化项目
2. **拓扑建模** — 可视化搭建配电网拓扑（变压器、母线、线路、负荷）
3. **资产绑定** — 上传电价表、设备策略库、运行时负荷数据
4. **构建校验** — 编译为 OpenDSS 兼容的求解器工作目录
5. **计算运行** — 选择求解精度（快速预览 / 标准求解 / 交付求解），启动多目标优化求解
6. **结果展示** — 查看 Pareto 前沿、NPV/IRR/回收期等财务指标，导出 HTML / PDF 分析报告

## 依赖管理

| 文件 | 用途 |
|------|------|
| `pyproject.toml` | Python 依赖（base / engine / web / dev / full 分组） |
| `frontend/package.json` | Node.js 依赖 |

常用安装命令：

```bash
pip install -e ".[full,dev]"       # 全部依赖
pip install -e ".[engine]"         # 仅引擎
pip install -e ".[web]"            # 仅后端 Web
```

## 引擎 CLI

优化引擎可脱离 Web 单独运行：

```bash
cd storage_engine_project
python main.py --registry inputs/registry/node_registry.xlsx --solver-tier standard
```

三档求解精度：

| 档位 | CLI 参数 | 种群 × 代数 | OpenDSS 策略 |
|------|----------|------------|-------------|
| 快速预览 | `--solver-tier fast` | 8 × 3 | GA 搜索阶段轻量代理，Top-3 OpenDSS 重校核 |
| 标准求解 | `--solver-tier standard` | 12 × 5 | GA 搜索阶段轻量代理，Top-3 OpenDSS 重校核 |
| 交付求解 | `--solver-tier delivery` | 16 × 8 | GA 全流程 OpenDSS 校核 |
| 自定义 | （不传 `--solver-tier`） | `--population-size` / `--generations` 手动指定 | `--opendss-only-for-full-recheck` 控制 |

## 注意事项

- OpenDSS 需在 Windows 上单独安装，引擎通过 COM 接口调用。未安装时引擎自动降级为标量约束校验。
- 前端开发时通过 `VITE_API_BASE_URL` 环境变量指向后端地址。
- 求解器 `main.py` 使用 `logging` 模块，日志级别通过 `LOG_LEVEL` 环境变量控制，默认 `INFO`。
- 前端 `pnpm build` 直接输出到 `backend/static/`，FastAPI 自动托管为 SPA。
- **调度模式（综合优化 / 电价套利 / 削峰填谷）** 为预留功能，求解器侧尚未区分实现，当前统一以电价套利为主、变压器越限被动惩罚的方式运行。

## 版本留存（2026-06-11）

本版重点改进 Web 建模到求解结果展示的闭环稳定性，并补充交付环境可直接使用的静态前端产物。

| 模块 | 更新内容 |
|------|----------|
| OpenDSS 构建校验 | 增加 build signature 校验，求解前会检查拓扑、资产和构建输入是否与当前项目一致，避免使用过期 Solver Workspace。 |
| 配电网拓扑与构建页 | 优化 Web 页面 OpenDSS 建模审查链路，补充拓扑构建契约测试，降低前端建模数据与求解器输入不一致的风险。 |
| 负荷建模 | 工商业负荷典型日建模输出统一改为 SVG，并按专利技术路线补充年度负荷水平五档、典型日组合图和相关测试。 |
| 结果评分与可视化 | 推荐方案与图表展示统一读取预计算评分，前端展示改为更直观的 0-100 综合得分；投资变化、回收期与目标函数等图表交互和样式同步修正。 |
| 求解任务管理 | 结果页支持删除指定求解任务，后端仅清理 `solver_runs/task_<task_id>`，保留项目拓扑、资产、构建工作区、负荷建模数据和其他任务。运行中、排队中或正在终止的任务会拒绝删除。 |
| 交付运行 | 前端生产构建产物同步到 `backend/static/`，`start.bat` 启动后可直接访问同源 Web 页面，无需单独启动前端开发服务器。 |

## 性能优化（2026-05）

### 第一轮：OpenDSS COM 调用精简

将 8 种群 × 1 代典型耗时从 4–5 小时降至约 1.5–2 小时：

| 优化项 | 涉及文件 | 说明 |
|--------|---------|------|
| 收紧全校验触发门槛 | `main.py` | 仅回收期 ≤10 年、NPV 回正、现金流为正的候选方案触发 365 天 OpenDSS 全仿真 |
| 合并日内滚动重复调用 | `simulation/rolling_dispatch.py` | `execute_day()` 中两轮逐小时 oracle 调用合并为一轮，小时 0–19 直接复用结果 |
| 每日单次电路编译 | `simulation/opendss_network_constraint_oracle.py` | 同一天的后续小时用 OpenDSS `Edit` 命令原地更新负荷与储能参数，无需每小时间从零 `Compile` 电路 |

### 第二轮：求解器架构优化

在保持仿真精度的前提下进一步缩短日常求解时间：

| 优化项 | 涉及文件 | 说明 |
|--------|---------|------|
| 求解档位 | `main.py`, `SolverPage.tsx` | 三档预设（快速预览 8×3 / 标准求解 12×5 / 交付求解 16×8），GA 搜索阶段默认使用轻量代理约束，OpenDSS 仅用于最终 Top-K 重校核 |
| 候选值量化 | `optimization/optimizer_bridge.py` | 功率按 50kW、时长按 0.25h 步长量化，提升缓存命中率与结果稳定性 |
| Top-K Pareto 重校核 | `main.py` | GA 完成后对 Pareto 前沿 Top-K 候选统一 OpenDSS 全年校核，最终 best 闭环保证通过校核 |
| Profiling 基础设施 | `storage_fitness_evaluator.py`, `lemming_optimizer.py` | 每代/每候选 wall-clock 计时、cache hit rate、OpenDSS trace 统计、Edit fallback 计数输出到 `engine_diagnostics.json` |
| PDF 报告导出 | `ResultsPage.tsx`, `reportBuilder.ts` | 新增 PDF 导出按钮，A4 打印优化（表格分页、orphans/widows 控制） |

## 快速部署（无需 Node.js）

在仅需运行（不开发前端）的机器上，使用 `start.bat` 一键启动：

```bash
start.bat    # 自动检测 Python → 创建 venv → 安装依赖 → 启动服务
```

该脚本无需预装 Node.js，仅依赖 Python 3.11。

## 许可证

All Rights Reserved.
