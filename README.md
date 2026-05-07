# 工商业储能优化平台

面向配电网的工商业电池储能系统优化平台。提供日前调度、遗传算法寻优、生命周期财务建模和 Web 图形化建模工作流。

## 环境要求

- Python 3.11.x
- Node.js 20+
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
npm install
npm run dev             # 启动前端开发服务器 → http://localhost:5173

# 4. 启动后端（另开终端）
cd backend
uvicorn storage_fastapi_backend:app --host 0.0.0.0 --port 8000 --reload
```

浏览器打开 `http://localhost:5173` 即可进入建模工作流。

## 项目结构

```
├── backend/                    FastAPI 后端（REST API + 求解器任务管理）
│   ├── routes/                 新版按领域划分的路由
│   ├── services/               业务逻辑层
│   ├── models/                 Pydantic 数据模型
│   └── data/projects/          持久化项目数据
├── frontend/                   React + Vite + TypeScript 前端
│   └── src/
│       ├── pages/workspace/    6 步工作流页面（总览→拓扑→资产→构建→求解→结果）
│       ├── components/         UI 组件
│       └── services/           API 调用封装
├── storage_engine_project/     核心优化引擎
│   ├── simulation/             日前调度 / 滚动调度 / 年度仿真
│   ├── optimization/           遗传算法优化器
│   ├── economics/              生命周期财务建模
│   └── inputs/                 场景输入数据
├── OpenDSS/                    IEEE 测试馈线模型（34/123 节点）
├── pyproject.toml              Python 依赖声明
├── constraints.txt             Python 精确版本锁
└── .gitignore
```

## 依赖管理

| 文件 | 用途 |
|------|------|
| `pyproject.toml` | Python 依赖（base / engine / web / dev / full 分组） |
| `constraints.txt` | Python 精确版本锁，用于可复现构建 |
| `frontend/package.json` | Node.js 依赖 |

常用安装命令：

```bash
pip install -e ".[full,dev]"           # 全部依赖（开发/打包用）
pip install -e ".[engine]"             # 仅引擎
pip install -e ".[web]"                # 仅后端 Web
pip install -c constraints.txt -e ".[full,dev]"  # 精确版本锁定安装
```

## 引擎 CLI

优化引擎可脱离 Web 单独运行：

```bash
cd storage_engine_project
python main.py --registry inputs/registry/node_registry.xlsx --generations 8 --population-size 16
```

## 注意事项

- OpenDSS 需在 Windows 上单独安装，引擎通过 COM 接口调用。未安装时引擎自动降级为标量约束校验。
- 前端开发时通过 `http://127.0.0.1:8000` 直连后端，需确保后端先启动。
