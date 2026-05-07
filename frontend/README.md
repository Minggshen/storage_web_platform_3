# Frontend workflow patch

这是一版面向“项目创建 → 拓扑建模 → 资产绑定 → 构建校验 → 计算运行 → 结果展示”的前端工作流代码骨架。

## 适用环境
- React 18+
- TypeScript
- react-router-dom 6+
- 已接入 TailwindCSS 的 Vite 前端工程

## 建议放置方式
将 `src/` 下文件合并到你现有前端工程，对应替换或新增。

## 已对接的现有后端接口
- `GET /api/project/{project_id}`
- `GET /api/topology/project/{project_id}`
- `GET /api/build/project/{project_id}/preview`
- `POST /api/build/project/{project_id}/generate`
- `GET /api/build/project/{project_id}/manifest`
- `POST /api/assets/device-library/upload`
- `POST /api/solver/project/{project_id}/configure`
- `GET /api/solver/project/{project_id}/config`
- `POST /api/solver/project/{project_id}/run`
- `GET /api/solver/task/{task_id}`
- `GET /api/solver/project/{project_id}/latest`
- `GET /api/solver/project/{project_id}/results`
- `GET /api/solver/project/{project_id}/summary`

## 仍建议后端补齐的接口
- `GET /api/projects`
- `POST /api/projects`
- `PUT /api/topology/project/{project_id}`
- `GET /api/assets/project/{project_id}`
- `GET /api/build/project/{project_id}/inference-table`
- `GET /api/solver/task/{task_id}/logs`
- `POST /api/solver/task/{task_id}/cancel`

## 本版定位
这版重点是：
1. 把页面与主流程搭起来
2. 把现有接口接进页面
3. 为缺失接口预留清晰的 service 层入口

其中拓扑画布目前是“工程化骨架版”，适合先把流程打通。真正的专业配电网拓扑编辑器，下一轮可替换为 React Flow / Konva 等更强画布方案。
