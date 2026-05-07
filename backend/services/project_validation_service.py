from __future__ import annotations

from typing import Any


class ProjectValidationService:
    """
    Minimal validation service for the visual-topology workflow.
    """

    def __init__(self, project_service: Any = None) -> None:
        self.project_service = project_service

    def validate_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        network = payload.get("network") if isinstance(payload.get("network"), dict) else {}
        nodes = network.get("nodes") if isinstance(network.get("nodes"), list) else []
        edges = network.get("edges") if isinstance(network.get("edges"), list) else []

        node_ids = {str(node.get("id")) for node in nodes}
        errors: list[str] = []
        warnings: list[str] = []

        if not nodes:
            warnings.append("项目中暂无节点。")
        if not any(str(node.get("type")) == "transformer" for node in nodes):
            warnings.append("建议至少配置一个主变节点。")

        for edge in edges:
            edge_id = str(edge.get("id", ""))
            if str(edge.get("from_node_id", "")) not in node_ids:
                errors.append(f"线路 {edge_id} 起点无效。")
            if str(edge.get("to_node_id", "")) not in node_ids:
                errors.append(f"线路 {edge_id} 终点无效。")

        return {
            "success": True,
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def validate_saved_project(self, project_id: str) -> dict[str, Any]:
        if self.project_service is None or not hasattr(self.project_service, "load_project"):
            return {
                "success": True,
                "valid": True,
                "errors": [],
                "warnings": ["未挂接 project_service，返回轻量校验结果。"],
            }
        project = self.project_service.load_project(project_id)
        if not isinstance(project, dict):
            return {
                "success": True,
                "valid": False,
                "errors": ["项目读取失败。"],
                "warnings": [],
            }
        return self.validate_project(project)
