
# next_backend_workflow_patch

这一批补的是“前端页面化工作流”最缺的后端接口，不再继续围绕求解器细节打转。

## 主要新增/增强接口
- `GET /api/projects`
- `POST /api/projects`
- `DELETE /api/project/{project_id}`
- `POST /api/project/{project_id}/clone`
- `GET /api/project/{project_id}/dashboard`
- `PUT /api/topology/project/{project_id}`
- `GET /api/build/project/{project_id}/inference-table`
- `GET /api/solver/task/{task_id}/logs`

## 需要替换的文件
- `storage_fastapi_backend.py`
- `models/project_model.py`
- `services/project_model_service.py`
- `services/search_space_inference_service.py`
- `services/project_dashboard_service.py`
- `services/build_inference_service.py`
- `services/solver_execution_service.py`
- `routes/project.py`
- `routes/topology.py`
- `routes/build.py`
- `routes/solver.py`

## 建议的第一轮测试
1. 启动后端
2. 访问 `/docs`
3. 测试：
   - `GET /api/projects`
   - `POST /api/projects`
   - `GET /api/project/{project_id}/dashboard`
   - `PUT /api/topology/project/{project_id}`
   - `GET /api/assets/project/{project_id}`
   - `GET /api/build/project/{project_id}/inference-table`
   - `GET /api/build/project/{project_id}/preview`
4. 若以上通过，再从前端测试：
   - 项目列表页
   - 项目总览页
   - 拓扑页保存
   - 资产页显示
   - 构建页显示自动推导表
