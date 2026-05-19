# 工程项目目录结构优化 · 设计方案

> **目标：** 理清文件边界、消除空目录残留、分离原始数据与建模产物、自动清理中间文件。

---

## 一、目标目录结构

```
{project_id}/
├── project.json
│
├── assets/                               ← 步骤①②③ 产出，求解器输入源
│   ├── tariff/                           ← ① 电价表（工程级，全局唯一）
│   │   └── asset_xxx_tariff_annual.xlsx
│   ├── device_library/                   ← ② 设备策略库（工程级，全局唯一）
│   │   └── asset_xxx_device_library.xlsx
│   └── runtime/{node_id}/                ← ③ 最终 runtime CSV（节点级）
│       ├── runtime_year_model_map.csv
│       └── runtime_model_library.csv
│
├── raw_load_data/{node_id}/              ← ③ 原始上传数据（节点级，仅 xlsx）
│   └── raw_load_data.xlsx
│
├── modeling_output/{node_id}/            ← ③ 建模产物（节点级，仅 PNG）
│   ├── 01_居民典型日曲线.png
│   ├── 02_全年逐日模型映射.png
│   └── 03_模型月度分布.png
│
├── build/                                ← ④ 构建产物（工程级模板）
│   ├── inputs/dss/visual_model/          ←    OpenDSS 电路（从拓扑编译）
│   ├── solver_handoff/dss/               ←    DSS 交接副本（流程保留）
│   ├── solver_workspace/inputs/          ←    求解器输入模板
│   │   ├── dss/visual_model/             ←    DSS 工作副本
│   │   ├── node_loads/{category}/{id}/   ←    runtime CSV 副本
│   │   ├── tariff/                       ←    电价表副本
│   │   ├── storage/                      ←    设备库副本
│   │   └── registry/                     ←    节点注册表
│   ├── manifest/build_manifest.json
│   ├── solver_command.json
│   └── workspace_summary.json
│
└── solver_runs/task_{id}/                ← ⑤ 求解任务（任务级快照）
    ├── stdout.log / stderr.log
    ├── task_meta.json
    └── solver_workspace/                 ←    build 模板完整快照 + outputs
```

---

## 二、改动清单

### 2.1 新增 `modeling_output/` 目录

将建模产物从 `raw_load_data/{node}/` 移出，独立存放。建模脚本输出已展平（见 2.2），因此 `build_runtime` 直接从 `modeling_output/{node_id}/` 读取，无需处理子目录。

**`process_all_nodes()` 路径变更：**

```python
raw_dir     = project_dir / "raw_load_data" / node_id          # 原始 xlsx 从此读取
model_dir   = project_dir / "modeling_output" / node_id        # 建模产物写到这里
runtime_dir = project_dir / "assets" / "runtime" / node_id      # 最终 CSV 写到这里

# 1. 建模：输出到 model_dir
result = model_residential(raw_file, str(model_dir))

# 2. 转换：从 model_dir 读取中间 Excel（展平后直接在这里）
build_result = build_residential(str(model_dir), str(runtime_dir))

# 3. 清理：删掉 model_dir 中的 .xlsx / .txt，保留 .png
for f in model_dir.glob("*.xlsx"): f.unlink()
for f in model_dir.glob("*.txt"):  f.unlink()
```

| 改动 | 位置 | 说明 |
|------|------|------|
| 建模输出路径 | `process_all_nodes()` | `output_dir` → `modeling_output/{node_id}/` |
| build 输入路径 | 同上 | 直接用 `modeling_output/{node_id}/`，不再需要子目录推断 |
| 中间产物清理 | 同上 | 成功后删除 .xlsx/.txt，保留 .png |
| 预览文件搜索 | `list_preview_files()` | `[modeling_dir, runtime_dir]` 替代 `[raw_dir, runtime_dir]` |
| 预览文件路径 | `get_preview_file_path()` | 同上 |
| 删除时联动 | `delete_raw_load_data()` | 同时删除 `modeling_output/{node_id}/` |

### 2.2 建模脚本：平铺输出

**不修改 `process_one_company()`**（该函数被 `main()` CLI 入口使用，不应破坏兼容性）。

在 `process_raw_data()` 末尾增加一步"展平"：将 `output_root / file_path.stem /` 下所有文件搬移到 `output_root /`，然后删除空的子目录。

**文件：** `backend/services/load_modeling_residential.py` — `process_raw_data()` 
**文件：** `backend/services/load_modeling_industrial.py` — `process_raw_data()`

```python
def process_raw_data(raw_excel_path, output_dir):
    file_path = Path(raw_excel_path)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    process_one_company(file_path, output_root)

    # process_one_company 会创建 output_root / file_path.stem / 子目录
    # 我们把文件全部搬移到 output_root / 下，消除多余层级
    nested_dir = output_root / file_path.stem
    if nested_dir.is_dir():
        for f in nested_dir.iterdir():
            shutil.move(str(f), str(output_root / f.name))
        nested_dir.rmdir()

    charts = sorted([p.name for p in output_root.glob("*.png")])
    excel_files = sorted([p.name for p in output_root.glob("*.xlsx")])
    return {"charts": charts, "excel_files": excel_files, "error": None}
```

（两个建模脚本各自加 `import shutil` 和上述展平逻辑。）

### 2.3 处理后自动清理中间 Excel

在 `process_all_nodes()` 中，`build_runtime` 成功后：

```python
# 删除 modeling_output/{node_id}/ 下所有 .xlsx 和 .txt（保留 .png）
for f in model_dir.glob("*.xlsx"):
    f.unlink()
for f in model_dir.glob("*.txt"):
    f.unlink()
```

### 2.4 更新 `listUploadedNodes` 响应

`GET /raw-load-data/uploaded/{project_id}` 返回的 `uploaded_nodes` 当前基于目录存在性判断。需要改为检查目录内是否有 xlsx 文件（而非仅目录存在），避免空目录被当作"已上传"。

### 2.5 现有工程清理脚本

提供一次性清理逻辑，可手动调用或嵌入启动时执行：

| 清理项 | 操作 |
|--------|------|
| `raw_load_data/*/raw_load_data/` (空子目录) | 删除 |
| `assets/runtime/*/` (空目录) | 删除 |
| `build/solver_workspace/inputs/node_loads/*/` (空目录) | 删除 |
| `build/solver_workspace/inputs/tariff/` (空) | 删除 |
| `build/solver_workspace/inputs/storage/` (空) | 删除 |
| `build/solver_workspace/outputs/` (空) | 删除 |

### 2.6 不改动的部分

- `build/` 下 DSS 文件的三份副本 — 构建管道内部实现，不修改
- `solver_runs/` 下的任务快照 — 求解器隔离需要，不修改
- `project.json` 结构 — 已有 Schema，不修改
- 前端 UI — 本次纯后端优化，不修改

---

## 三、改动文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `backend/services/load_data_processing_service.py` | 新增 `modeling_output/` 路径、中间产物清理、预览/删除适配 |
| 修改 | `backend/services/load_modeling_residential.py` | `process_raw_data()` 平铺输出 |
| 修改 | `backend/services/load_modeling_industrial.py` | `process_raw_data()` 平铺输出 |

---

## 四、验证方案

1. Python 语法检查：`python -m py_compile` 3 个改动文件
2. 端到端测试：对一个节点执行 `upload → process`，确认：
   - `raw_load_data/{node}/raw_load_data.xlsx` 存在
   - `modeling_output/{node}/` 下只有 PNG 文件
   - `assets/runtime/{node}/` 下有 `runtime_year_model_map.csv` 和 `runtime_model_library.csv`
   - 前端预览可看到 PNG 图表
3. 删除测试：点击 × 删除节点，确认 `raw_load_data/{node}/` 和 `modeling_output/{node}/` 均被删除
