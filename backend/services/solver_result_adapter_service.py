from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


class SolverResultAdapterService:
    """Adapt solver artifacts into frontend-friendly API payloads."""

    def __init__(self, project_service: Any = None, data_root: str | Path | None = None) -> None:
        backend_root = Path(__file__).resolve().parent.parent
        self.project_service = project_service
        self.data_root = Path(data_root) if data_root is not None else backend_root / "data" / "projects"

    def get_latest_task(self, project_id: str) -> dict[str, Any] | None:
        tasks = self._load_tasks(project_id)
        if tasks:
            return sorted(tasks, key=self._task_sort_key, reverse=True)[0]

        latest_task_dir = self._find_latest_task_dir(project_id)
        if latest_task_dir is None:
            return None

        task_id = latest_task_dir.name.replace("task_", "", 1)
        task = {
            "task_id": task_id,
            "project_id": project_id,
            "status": "unknown",
            "run_root": str(latest_task_dir),
            "stdout_log": str(latest_task_dir / "logs" / "stdout.log"),
            "stderr_log": str(latest_task_dir / "logs" / "stderr.log"),
            "outputs_dir": str(latest_task_dir / "outputs"),
        }
        if (latest_task_dir / "logs" / "stdout.log").exists():
            task["status"] = "completed"
        return task

    def get_task(self, task_id: str, project_id: str | None = None) -> dict[str, Any] | None:
        if project_id:
            for task in self._load_tasks(project_id):
                if str(task.get("task_id")) == str(task_id):
                    return task

        task_dir = self._find_task_dir(task_id, project_id)
        if task_dir is None:
            return None

        return {
            "task_id": task_id,
            "project_id": project_id,
            "status": "unknown",
            "run_root": str(task_dir),
            "stdout_log": str(task_dir / "logs" / "stdout.log"),
            "stderr_log": str(task_dir / "logs" / "stderr.log"),
            "outputs_dir": str(task_dir / "outputs"),
        }

    def get_task_logs(self, task_id: str, project_id: str | None = None) -> dict[str, Any] | None:
        task = self.get_task(task_id, project_id)
        if task is None:
            return None

        stdout_path = Path(task.get("stdout_log", ""))
        stderr_path = Path(task.get("stderr_log", ""))

        task["stdout_text"] = self._read_text(stdout_path) if stdout_path.exists() else ""
        task["stderr_text"] = self._read_text(stderr_path) if stderr_path.exists() else ""
        task["stdout_encoding"] = "utf-8/gb18030 fallback"
        task["stderr_encoding"] = "utf-8/gb18030 fallback"
        return task

    def get_project_solver_summary(self, project_id: str) -> dict[str, Any]:
        task = self.get_latest_task(project_id)
        if task is None:
            return {"project_id": project_id, "summary_rows": [], "best_result_summary": {}, "overall_best_schemes": []}

        outputs_dir = self._resolve_outputs_dir(task)
        summary_rows = self._read_summary_rows(outputs_dir)
        best_result_summary = self._read_best_result_summary(outputs_dir)
        overall_best_schemes = self._read_overall_best_schemes(outputs_dir)
        engine_diagnostics = self._read_engine_diagnostics(outputs_dir)

        if not best_result_summary and overall_best_schemes:
            first = overall_best_schemes[0]
            if isinstance(first, dict):
                best_result_summary = first
        if not overall_best_schemes and best_result_summary:
            overall_best_schemes = [best_result_summary]
        if not summary_rows and best_result_summary:
            summary_rows = [best_result_summary]

        return {
            "project_id": project_id,
            "summary_rows": summary_rows,
            "best_result_summary": best_result_summary,
            "overall_best_schemes": overall_best_schemes,
            "engine_diagnostics": engine_diagnostics,
        }

    def list_project_result_files(self, project_id: str) -> dict[str, Any]:
        task = self.get_latest_task(project_id)
        if task is None:
            return {"project_id": project_id, "groups": {}, "files": [], "counts": {}}

        outputs_dir = self._resolve_outputs_dir(task)
        if outputs_dir is None or not outputs_dir.exists():
            return {"project_id": project_id, "groups": {}, "files": [], "counts": {}}

        files: list[dict[str, Any]] = []
        groups: dict[str, list[dict[str, Any]]] = {}
        counts: dict[str, int] = {}

        for path in sorted(outputs_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(outputs_dir).as_posix()
            group = rel.split("/", 1)[0] if "/" in rel else "root"
            item = {
                "name": path.name,
                "relative_path": rel,
                "group": group,
                "size_bytes": path.stat().st_size,
                "suffix": path.suffix.lower(),
                "absolute_path": str(path),
            }
            files.append(item)
            groups.setdefault(group, []).append(item)
            counts[group] = counts.get(group, 0) + 1

        return {"project_id": project_id, "groups": groups, "files": files, "counts": counts}

    def preview_project_result_file(self, project_id: str, relative_path: str, group: str | None = None) -> dict[str, Any]:
        task = self.get_latest_task(project_id)
        if task is None:
            return {"success": False, "project_id": project_id, "group": group, "relative_path": relative_path, "content": "未找到最近任务。", "type": "text"}

        outputs_dir = self._resolve_outputs_dir(task)
        if outputs_dir is None:
            return {"success": False, "project_id": project_id, "group": group, "relative_path": relative_path, "content": "未找到输出目录。", "type": "text"}

        path = outputs_dir / relative_path
        if not path.exists():
            return {"success": False, "project_id": project_id, "group": group, "relative_path": relative_path, "content": "文件不存在。", "type": "text"}

        suffix = path.suffix.lower()
        if suffix == ".csv":
            preview = self._preview_csv(path)
            return {
                "success": True,
                "project_id": project_id,
                "group": group,
                "relative_path": relative_path,
                "file_name": path.name,
                "type": "table",
                "columns": preview["columns"],
                "rows": preview["rows"],
                "row_count": preview["row_count"],
                "preview_row_count": preview["preview_row_count"],
            }

        text = self._read_text(path)
        return {
            "success": True,
            "project_id": project_id,
            "group": group,
            "relative_path": relative_path,
            "file_name": path.name,
            "type": "text",
            "content": text[:20000],
        }

    def get_project_solver_results(self, project_id: str) -> dict[str, Any]:
        return {
            "success": True,
            "project_id": project_id,
            "latest_task": self.get_latest_task(project_id),
            "result_files": self.list_project_result_files(project_id),
            "summary": self.get_project_solver_summary(project_id),
        }

    def _project_root(self, project_id: str) -> Path:
        if self.project_service is not None and hasattr(self.project_service, "get_project_root"):
            return self.project_service.get_project_root(project_id)
        return self.data_root / project_id

    def _tasks_file(self, project_id: str) -> Path:
        return self._project_root(project_id) / "tasks.json"

    def _load_tasks(self, project_id: str) -> list[dict[str, Any]]:
        path = self._tasks_file(project_id)
        if not path.exists():
            return []
        payload = self._read_json(path)
        if isinstance(payload, list):
            return [t for t in payload if isinstance(t, dict)]
        if isinstance(payload, dict):
            if isinstance(payload.get("tasks"), list):
                return [t for t in payload["tasks"] if isinstance(t, dict)]
            if all(isinstance(v, dict) for v in payload.values()):
                return list(payload.values())
        return []

    def _task_sort_key(self, task: dict[str, Any]) -> tuple:
        return (
            str(task.get("completed_at") or ""),
            str(task.get("started_at") or ""),
            str(task.get("created_at") or ""),
            str(task.get("task_id") or ""),
        )

    def _find_latest_task_dir(self, project_id: str) -> Path | None:
        solver_runs = self._project_root(project_id) / "solver_runs"
        if not solver_runs.exists():
            return None
        task_dirs = [p for p in solver_runs.iterdir() if p.is_dir() and p.name.startswith("task_")]
        if not task_dirs:
            return None
        return sorted(task_dirs, key=lambda p: p.stat().st_mtime, reverse=True)[0]

    def _find_task_dir(self, task_id: str, project_id: str | None = None) -> Path | None:
        candidate_roots: list[Path] = []
        if project_id:
            candidate_roots.append(self._project_root(project_id) / "solver_runs")
        else:
            if self.data_root.exists():
                candidate_roots.extend([p / "solver_runs" for p in self.data_root.iterdir() if p.is_dir()])

        for root in candidate_roots:
            candidate = root / f"task_{task_id}"
            if candidate.exists():
                return candidate
        return None

    def _resolve_outputs_dir(self, task: dict[str, Any]) -> Path | None:
        outputs_dir = task.get("outputs_dir")
        if isinstance(outputs_dir, str) and outputs_dir:
            path = Path(outputs_dir)
            if path.exists():
                return path

        run_root = task.get("run_root")
        if isinstance(run_root, str) and run_root:
            candidate = Path(run_root) / "outputs"
            if candidate.exists():
                return candidate

        task_id = task.get("task_id")
        project_id = task.get("project_id")
        if task_id and project_id:
            task_dir = self._find_task_dir(str(task_id), str(project_id))
            if task_dir is not None:
                candidate = task_dir / "outputs"
                if candidate.exists():
                    return candidate
        return None

    def _read_summary_rows(self, outputs_dir: Path | None) -> list[dict[str, Any]]:
        if outputs_dir is None:
            return []
        for pattern in ("**/summary_rows.json", "**/summary_rows.csv", "**/archive_results.csv"):
            matches = list(outputs_dir.glob(pattern))
            if not matches:
                continue
            path = matches[0]
            if path.suffix.lower() == ".json":
                data = self._read_json(path)
                if isinstance(data, list):
                    return [row for row in data if isinstance(row, dict)]
            elif path.suffix.lower() == ".csv":
                rows = self._read_csv_rows(path, limit=200)
                if rows:
                    return rows
        return []

    def _read_best_result_summary(self, outputs_dir: Path | None) -> dict[str, Any]:
        if outputs_dir is None:
            return {}
        for pattern in ("**/best_result_summary.json", "**/best_financial_summary.csv", "**/best_annual_summary.csv"):
            matches = list(outputs_dir.glob(pattern))
            if not matches:
                continue
            path = matches[0]
            if path.suffix.lower() == ".json":
                data = self._read_json(path)
                return data if isinstance(data, dict) else {}
            rows = self._read_csv_rows(path, limit=1)
            if rows:
                return rows[0]
        return {}

    def _read_engine_diagnostics(self, outputs_dir: Path | None) -> Any:
        if outputs_dir is None:
            return None
        root_file = outputs_dir / "engine_diagnostics.json"
        if root_file.exists():
            try:
                data = self._read_json(root_file)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        matches = sorted(outputs_dir.glob("**/engine_diagnostics.json"))
        scenarios: list[dict[str, Any]] = []
        for path in matches:
            if path.parent == outputs_dir:
                continue
            try:
                data = self._read_json(path)
            except Exception:
                continue
            if isinstance(data, dict):
                scenarios.append(data)
        if not scenarios:
            return None
        return {"scenarios": scenarios, "scenario_count": len(scenarios)}

    def _read_overall_best_schemes(self, outputs_dir: Path | None) -> list[dict[str, Any]]:
        if outputs_dir is None:
            return []
        matches = list(outputs_dir.glob("**/overall_best_schemes.json"))
        if not matches:
            return []
        data = self._read_json(matches[0])
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        return []

    def _read_json(self, path: Path) -> Any:
        text = self._read_text(path)
        return json.loads(text)

    def _read_text(self, path: Path) -> str:
        for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
            try:
                return path.read_text(encoding=encoding)
            except Exception:
                continue
        return path.read_text(errors="ignore")

    def _read_csv_rows(self, path: Path, limit: int = 200) -> list[dict[str, Any]]:
        text = self._read_text(path)
        reader = csv.DictReader(text.splitlines())
        rows: list[dict[str, Any]] = []
        for idx, row in enumerate(reader):
            rows.append(dict(row))
            if idx + 1 >= limit:
                break
        return rows

    def _preview_csv(self, path: Path, limit: int = 50) -> dict[str, Any]:
        text = self._read_text(path)
        reader = csv.DictReader(text.splitlines())
        rows: list[dict[str, Any]] = []
        columns = reader.fieldnames or []
        row_count = 0
        for row in reader:
            row_count += 1
            if len(rows) < limit:
                rows.append(dict(row))
        return {"columns": columns, "rows": rows, "row_count": row_count, "preview_row_count": len(rows)}
