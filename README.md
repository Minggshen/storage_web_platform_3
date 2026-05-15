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
├── OpenDSS/                    IEEE 测试馈线模型（34/123/8500 节点）
├── pyproject.toml              Python 依赖声明
└── .github/workflows/          CI/CD 流水线
```

## 工作流

1. **项目创建** — 新建优化项目
2. **拓扑建模** — 可视化搭建配电网拓扑（变压器、母线、线路、负荷）
3. **资产绑定** — 上传电价表、设备策略库、运行时负荷数据
4. **构建校验** — 编译为 OpenDSS 兼容的求解器工作目录
5. **计算运行** — 配置遗传算法参数，启动多目标优化求解
6. **结果展示** — 查看 Pareto 前沿、NPV/IRR/回收期等财务指标、导出分析报告

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
python main.py --registry inputs/registry/node_registry.xlsx --generations 8 --population-size 16
```

## 注意事项

- OpenDSS 需在 Windows 上单独安装，引擎通过 COM 接口调用。未安装时引擎自动降级为标量约束校验。
- 前端开发时通过 `VITE_API_BASE_URL` 环境变量指向后端地址。
- 求解器 `main.py` 使用 `logging` 模块，日志级别通过 `LOG_LEVEL` 环境变量控制，默认 `INFO`。
- 前端 `pnpm build` 直接输出到 `backend/static/`，FastAPI 自动托管为 SPA。

## 快速部署（无需 Node.js）

在仅需运行（不开发前端）的机器上，使用 `start.bat` 一键启动：

```bash
start.bat    # 自动检测 Python → 创建 venv → 安装依赖 → 启动服务
```

该脚本无需预装 Node.js，仅依赖 Python 3.11。

## 许可证

All Rights Reserved.
