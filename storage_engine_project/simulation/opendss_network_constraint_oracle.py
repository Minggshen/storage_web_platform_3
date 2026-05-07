from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from storage_engine_project.data.runtime_loader import load_runtime_bundle
from storage_engine_project.simulation.network_constraint_oracle import HourlyNetworkConstraint, NetworkConstraintOracle


@dataclass(slots=True)
class OpenDSSOracleConfig:
    master_dss_path: str
    target_bus_name: str | None = None
    target_load_name: str | None = None
    target_kv_ln: float = 10.0
    engine_preference: str = "auto"
    voltage_min_pu: float = 0.93
    voltage_max_pu: float = 1.07
    voltage_penalty_coeff_yuan_per_pu: float = 0.0
    compile_each_call: bool = True
    allow_engine_fallback: bool = True
    log_failures: bool = True


class _ComBackend:
    def __init__(self) -> None:
        import win32com.client  # type: ignore

        self._dss = win32com.client.Dispatch("OpenDSSEngine.DSS")
        ok = self._dss.Start(0)
        if not ok:
            raise RuntimeError("OpenDSS COM 引擎启动失败。")
        self.text = self._dss.Text
        self.circuit = self._dss.ActiveCircuit
        self.solution = self.circuit.Solution
        self._temp_generators: set[str] = set()

    def compile(self, master_path: str) -> None:
        self.text.Command = f'Compile [{master_path}]'
        self.circuit = self._dss.ActiveCircuit
        self.solution = self.circuit.Solution

    def clear_temp(self) -> None:
        # Each hour recompiles Master.dss, whose circuit starts from Clear. Some OpenDSS COM
        # builds show modal warnings for the Delete command, so avoid issuing it here.
        self._temp_generators.clear()

    def load_exists(self, load_name: str) -> bool:
        try:
            names = {str(name).lower() for name in list(self.circuit.Loads.AllNames)}
        except Exception:
            return False
        return str(load_name).lower() in names

    def set_load_power(
        self,
        load_name: str,
        bus_name: str,
        phases: int,
        kv_ln: float,
        net_load_kw: float,
        q_to_p_ratio: float,
    ) -> None:
        load_name = str(load_name or "").strip()
        bus_name = str(bus_name or "").strip()
        if not load_name or not bus_name:
            return

        phase_count = 3
        phase_suffix = ".1.2.3"
        bus_ref = bus_name if "." in bus_name else f"{bus_name}{phase_suffix}"
        kv_value = max(0.0, float(kv_ln))
        q_ratio = max(0.0, float(q_to_p_ratio))
        net_kw = float(net_load_kw)
        load_kw = max(0.0, net_kw)
        load_kvar = load_kw * q_ratio

        action = "Edit" if self.load_exists(load_name) else "New"
        self.text.Command = (
            f"{action} Load.{load_name} bus1={bus_ref} phases={phase_count} conn=wye "
            f"model=1 kV={kv_value:.4f} kW={load_kw:.6f} kvar={load_kvar:.6f} Status=variable"
        )

        if net_kw < -1e-6:
            gen_name = "__GPT_TMP_BG_GEN_" + self._safe_temp_name(load_name)
            gen_kw = abs(net_kw)
            self.text.Command = (
                f"New Generator.{gen_name} bus1={bus_ref} phases={phase_count} "
                f"kV={kv_value:.4f} kW={gen_kw:.6f} PF=1 model=1"
            )
            self._temp_generators.add(gen_name)

    def set_or_add_target_load(
        self,
        target_load_name: str | None,
        target_bus_name: str,
        phases: int,
        kv_ln: float,
        actual_net_load_kw: float,
        q_to_p_ratio: float,
        reference_kw: float | None = None,
    ) -> None:
        if reference_kw is None:
            reference_kw = 0.0
        delta_kw = float(actual_net_load_kw) - float(reference_kw)
        kvar = abs(delta_kw) * max(0.0, float(q_to_p_ratio))
        phase_count = 3
        bus_ref = self._bus_ref(target_bus_name, phase_count)
        if delta_kw >= 0:
            if abs(delta_kw) > 1e-6:
                self.text.Command = f"New Load.__GPT_TMP_DELTA_LOAD bus1={bus_ref} phases={phase_count} conn=wye model=1 kV={kv_ln:.4f} kW={delta_kw:.6f} kvar={kvar:.6f}"
        else:
            delta_gen = abs(delta_kw)
            self.text.Command = f"New Generator.__GPT_TMP_DELTA_GEN bus1={bus_ref} phases={phase_count} kV={kv_ln:.4f} kW={delta_gen:.6f} PF=1 model=1"

    def add_storage_dispatch(
        self,
        target_bus_name: str,
        phases: int,
        kv_ln: float,
        charge_kw: float,
        discharge_kw: float,
        rated_power_kw: float,
        rated_energy_kwh: float,
        current_soc: float,
    ) -> None:
        phase_count = 3
        bus_ref = self._bus_ref(target_bus_name, phase_count)
        net_kw = float(discharge_kw) - float(charge_kw)
        state = "IDLING"
        if net_kw > 1e-6:
            state = "DISCHARGING"
        elif net_kw < -1e-6:
            state = "CHARGING"
        kwrated = max(abs(float(rated_power_kw)), abs(net_kw), 1.0)
        kwhrated = max(abs(float(rated_energy_kwh)), 1.0)
        kva = max(kwrated, abs(net_kw), 1.0)
        stored = min(max(float(current_soc), 0.0), 1.0) * 100.0
        self.text.Command = (
            f"New Storage.__GPT_STORAGE bus1={bus_ref} phases={phase_count} conn=wye kV={kv_ln:.4f} "
            f"kWRated={kwrated:.6f} kWhRated={kwhrated:.6f} kVA={kva:.6f} "
            f"kW={net_kw:.6f} kvar=0 %stored={stored:.6f} %reserve=0 State={state} dispmode=external"
        )

    @staticmethod
    def _bus_ref(bus_name: str, phases: int) -> str:
        if "." in str(bus_name):
            return str(bus_name)
        return f"{bus_name}.1.2.3"

    @staticmethod
    def _safe_temp_name(raw: str) -> str:
        out = []
        for ch in str(raw):
            if ch.isalnum() or ch == "_":
                out.append(ch)
            else:
                out.append("_")
        return "".join(out).strip("_") or "load"

    def solve(self) -> bool:
        self.text.Command = "set mode=snap"
        self.solution.Solve()
        try:
            return bool(self.solution.Converged)
        except Exception:
            return True

    def total_losses_kw_kvar(self) -> tuple[float | None, float | None]:
        try:
            raw = list(self.circuit.Losses)
            if len(raw) < 2:
                return None, None
            p_kw = float(raw[0]) / 1000.0
            q_kvar = float(raw[1]) / 1000.0
            if not math.isfinite(p_kw) or not math.isfinite(q_kvar):
                return None, None
            return p_kw, q_kvar
        except Exception:
            return None, None

    def all_bus_vmag_pu(self) -> list[float]:
        values: list[float] = []
        for row in self.bus_voltage_summaries():
            v_min = row.get("voltage_pu_min")
            v_max = row.get("voltage_pu_max")
            if v_min is not None:
                values.append(float(v_min))
            if v_max is not None and v_max != v_min:
                values.append(float(v_max))
        return values

    def target_bus_vmag_pu(self, bus_name: str) -> list[float]:
        try:
            self.circuit.SetActiveBus(bus_name)
            return self._active_bus_voltage_pu()
        except Exception:
            return []

    def bus_voltage_summaries(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        try:
            bus_names = list(self.circuit.AllBusNames)
        except Exception:
            return rows
        for bus_name in bus_names:
            try:
                self.circuit.SetActiveBus(str(bus_name))
                mags = self._active_bus_voltage_pu()
                if not mags:
                    continue
                rows.append(
                    {
                        "bus": str(bus_name),
                        "voltage_pu_min": float(min(mags)),
                        "voltage_pu_max": float(max(mags)),
                    }
                )
            except Exception:
                continue
        return rows

    def _active_bus_voltage_pu(self) -> list[float]:
        try:
            bus = self.circuit.ActiveBus
        except Exception:
            return []

        try:
            raw_pu = list(bus.puVmagAngle)
            pu_values = [
                float(value)
                for value in raw_pu[0::2]
                if value is not None and math.isfinite(float(value))
            ]
        except Exception:
            pu_values = []

        if pu_values and all(0.0 <= abs(value) <= 2.0 for value in pu_values) and max(abs(value) for value in pu_values) > 1e-9:
            return pu_values

        actual_volts: list[float] = []
        try:
            raw_volts = list(bus.VMagAngle)
            actual_volts = [
                float(value)
                for value in raw_volts[0::2]
                if value is not None and math.isfinite(float(value))
            ]
        except Exception:
            actual_volts = []

        kv_base = self._read_float(bus, "kVBase", 0.0)
        normalized = self._normalize_voltage_magnitudes(actual_volts, kv_base)
        if normalized:
            return normalized

        return self._normalize_voltage_magnitudes(pu_values, kv_base)

    @staticmethod
    def _normalize_voltage_magnitudes(values: list[float], kv_base: float) -> list[float]:
        if not values or kv_base <= 0:
            return []
        candidates = []
        for base in (kv_base, kv_base * math.sqrt(3.0), kv_base / math.sqrt(3.0)):
            if base > 0:
                normalized = [value / (base * 1000.0) for value in values]
                if normalized and all(math.isfinite(value) and 0.0 <= abs(value) <= 2.0 for value in normalized):
                    score = sum(abs(abs(value) - 1.0) for value in normalized) / len(normalized)
                    candidates.append((score, normalized))
        if not candidates:
            return []
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def line_current_summaries(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        try:
            lines = self.circuit.Lines
            line_names = list(lines.AllNames)
        except Exception:
            return rows
        for line_name in line_names:
            try:
                lines.Name = str(line_name)
                element = self.circuit.ActiveCktElement
                raw = list(element.CurrentsMagAng)
                magnitudes = [float(v) for v in raw[0::2] if v is not None]
                current_a = float(max(magnitudes)) if magnitudes else 0.0
                terminal1_power_kw = self._element_terminal1_power_kw(element)
                normamps = self._read_float(lines, "NormAmps", self._read_float(element, "NormalAmps", 0.0))
                emergamps = self._read_float(lines, "EmergAmps", self._read_float(element, "EmergAmps", 0.0))
                loading_pct = (current_a / normamps * 100.0) if normamps > 0 else None
                bus1 = self._read_str(lines, "Bus1")
                bus2 = self._read_str(lines, "Bus2")
                rows.append(
                    {
                        "line": str(line_name),
                        "bus1": bus1,
                        "bus2": bus2,
                        "current_a": current_a,
                        "loading_pct": loading_pct,
                        "normamps": normamps,
                        "emergamps": emergamps,
                        "terminal1_power_kw": terminal1_power_kw,
                        "flow_direction": "reverse" if terminal1_power_kw is not None and terminal1_power_kw < -1e-9 else "forward",
                    }
                )
            except Exception:
                continue
        return rows

    def target_line_current_summaries(self, target_bus_name: str) -> list[dict[str, Any]]:
        target = self._bus_base_name(target_bus_name)
        if not target:
            return []
        rows: list[dict[str, Any]] = []
        for row in self.line_current_summaries():
            if self._bus_base_name(row.get("bus1")) == target or self._bus_base_name(row.get("bus2")) == target:
                rows.append(row)
        return rows

    @staticmethod
    def _element_terminal1_power_kw(element: Any) -> float | None:
        try:
            powers = [float(value) for value in list(element.Powers)]
            if len(powers) < 2:
                return None
            terminal1 = powers[: max(2, len(powers) // 2)]
            p_values = terminal1[0::2]
            total_kw = float(sum(p_values))
            return total_kw if math.isfinite(total_kw) else None
        except Exception:
            return None

    @staticmethod
    def _read_str(obj: Any, attr: str) -> str:
        try:
            value = getattr(obj, attr)
        except Exception:
            return ""
        return str(value or "").strip()

    @staticmethod
    def _bus_base_name(value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        return text.split(".", 1)[0]

    @staticmethod
    def _read_float(obj: Any, attr: str, default: float = 0.0) -> float:
        try:
            value = getattr(obj, attr)
            number = float(value)
        except Exception:
            return float(default)
        return number if number == number else float(default)


class OpenDSSConstraintOracle(NetworkConstraintOracle):
    """
    一个可落地的 OpenDSS 网侧约束 oracle。

    设计目标不是把年度内核整体改写成潮流仿真器，而是在不推翻现有主求解链的前提下：
    1. 在 full_recheck 或指定阶段，用真实 DSS 网络对当前小时的计划动作做一次网侧校核；
    2. 返回 HourlyNetworkConstraint 接口需要的充/放电上限、服务功率上限、变压器限值和电压罚金；
    3. 在 OpenDSS 不可用时，允许退回轻量代理，而不是让主求解器直接中断。
    """

    def __init__(self, config: OpenDSSOracleConfig) -> None:
        self.config = config
        self.master_dss_path = str(Path(config.master_dss_path).expanduser().resolve())
        if not Path(self.master_dss_path).exists():
            raise FileNotFoundError(f"找不到 Master.dss：{self.master_dss_path}")
        self._backend = self._init_backend()
        self._runtime_manifest_cache: dict[str, list[dict[str, Any]]] = {}

    def _init_backend(self):
        pref = str(self.config.engine_preference).strip().lower()
        last_error: Exception | None = None
        if pref in {"auto", "com"}:
            try:
                return _ComBackend()
            except Exception as exc:  # pragma: no cover
                last_error = exc
        if self.config.allow_engine_fallback:
            return None
        raise RuntimeError(f"OpenDSS 引擎初始化失败：{last_error}")

    def _resolve_target_bus(self, ctx) -> str:
        return (
            self.config.target_bus_name
            or str(ctx.meta.get("target_bus_name", "")).strip()
            or str(ctx.meta.get("target_element_bus", "")).strip()
            or (f"n{int(ctx.node_id)}" if getattr(ctx, "node_id", None) is not None else "")
        )

    def _resolve_target_load(self, ctx) -> str | None:
        cand = (
            self.config.target_load_name
            or str(ctx.meta.get("target_load_name", "")).strip()
        )
        return cand or None

    def _resolve_network_runtime_manifest_path(self, ctx) -> Path | None:
        text = str(ctx.meta.get("network_runtime_manifest_path", "") or "").strip()
        if not text:
            return None

        raw = Path(text)
        if raw.is_absolute():
            return raw.resolve() if raw.exists() else None

        for root in self._workspace_root_candidates(ctx):
            candidate = (root / raw).resolve()
            if candidate.exists():
                return candidate
        return None

    def _workspace_root_candidates(self, ctx) -> list[Path]:
        candidates: list[Path] = []
        master_path = Path(self.master_dss_path)
        if (
            len(master_path.parents) >= 4
            and master_path.parent.name == "visual_model"
            and master_path.parents[1].name == "dss"
            and master_path.parents[2].name == "inputs"
        ):
            candidates.append(master_path.parents[3])

        node_dir_text = str(getattr(ctx, "node_dir", "") or "").strip()
        if node_dir_text:
            node_dir = Path(node_dir_text)
            if node_dir.is_absolute() and len(node_dir.parents) >= 4:
                if node_dir.parents[1].name == "node_loads" and node_dir.parents[2].name == "inputs":
                    candidates.append(node_dir.parents[3])

        out: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate.resolve())
            if key not in seen:
                out.append(candidate.resolve())
                seen.add(key)
        return out

    @staticmethod
    def _workspace_root_from_manifest(manifest_path: Path) -> Path:
        if (
            len(manifest_path.parents) >= 3
            and manifest_path.parent.name == "registry"
            and manifest_path.parents[1].name == "inputs"
        ):
            return manifest_path.parents[2]
        return manifest_path.parent

    def _load_network_runtime_entries(self, ctx) -> list[dict[str, Any]]:
        manifest_path = self._resolve_network_runtime_manifest_path(ctx)
        if manifest_path is None:
            return []

        cache_key = str(manifest_path)
        cached = self._runtime_manifest_cache.get(cache_key)
        if cached is not None:
            return cached

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw_loads = manifest.get("loads") if isinstance(manifest, dict) else None
        if not isinstance(raw_loads, list):
            raise ValueError(f"network runtime manifest 格式错误：{manifest_path}")

        workspace_root = self._workspace_root_from_manifest(manifest_path)
        entries: list[dict[str, Any]] = []
        for raw in raw_loads:
            if not isinstance(raw, dict) or not self._to_bool(raw.get("enabled"), True):
                continue

            node_dir = Path(str(raw.get("node_dir") or ""))
            if not node_dir.is_absolute():
                node_dir = (workspace_root / node_dir).resolve()

            payload = load_runtime_bundle(
                {
                    "node_dir": str(node_dir),
                    "year_model_map_file": str(raw.get("year_model_map_file") or "runtime_year_model_map.csv"),
                    "model_library_file": str(raw.get("model_library_file") or "runtime_model_library.csv"),
                },
                project_root=None,
                expected_days=365,
            )
            entries.append(
                {
                    "internal_model_id": str(raw.get("internal_model_id") or ""),
                    "node_id": self._to_int(raw.get("node_id"), 0),
                    "load_name": str(raw.get("dss_load_name") or raw.get("target_load_name") or ""),
                    "bus_name": str(raw.get("dss_bus_name") or raw.get("target_bus_name") or ""),
                    "phases": 3,
                    "kv_ln": self._to_float(raw.get("target_kv_ln"), self.config.target_kv_ln),
                    "q_to_p_ratio": self._to_float(raw.get("q_to_p_ratio"), 0.25),
                    "pv_capacity_kw": self._to_float(raw.get("pv_capacity_kw"), 0.0),
                    "year_model_map": payload["year_model_map"],
                    "model_library": payload["model_library"],
                }
            )

        self._runtime_manifest_cache[cache_key] = entries
        return entries

    def _runtime_kw_for_hour(self, entry: dict[str, Any], day_index: int, hour_index: int) -> float:
        year_model_map = entry["year_model_map"]
        if day_index < 0 or day_index >= len(year_model_map):
            raise IndexError(f"day_index 超出 runtime 范围：{day_index}")
        if hour_index < 0 or hour_index >= 24:
            raise IndexError(f"hour_index 超出 runtime 范围：{hour_index}")

        model_id = int(year_model_map[int(day_index)])
        profile = entry["model_library"][model_id]
        load_kw = float(profile[int(hour_index)])
        pv_kw = self._pv_kw_for_hour(float(entry.get("pv_capacity_kw") or 0.0), int(hour_index))
        return load_kw - pv_kw

    @staticmethod
    def _pv_kw_for_hour(pv_capacity_kw: float, hour_index: int) -> float:
        if pv_capacity_kw <= 1e-9:
            return 0.0
        shape = max(0.0, math.sin((int(hour_index) - 6) / 12.0 * math.pi))
        return float(pv_capacity_kw) * shape

    @staticmethod
    def _to_bool(value: Any, default: bool) -> bool:
        if value in (None, ""):
            return bool(default)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(int(value))
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "on", "是", "启用"}:
            return True
        if text in {"0", "false", "no", "n", "off", "否", "停用"}:
            return False
        return bool(default)

    @staticmethod
    def _to_float(value: Any, default: float) -> float:
        try:
            if value in (None, ""):
                return float(default)
            parsed = float(value)
        except Exception:
            return float(default)
        return parsed if math.isfinite(parsed) else float(default)

    @staticmethod
    def _to_int(value: Any, default: int) -> int:
        try:
            if value in (None, ""):
                return int(default)
            return int(float(value))
        except Exception:
            return int(default)

    @staticmethod
    def _normalize_distribution_base_kv(value: Any) -> float:
        try:
            kv = float(value)
        except Exception:
            return 10.0
        if not math.isfinite(kv):
            return 10.0
        legacy_ln = 10.0 / math.sqrt(3.0)
        if kv > 0 and abs(kv - legacy_ln) <= max(0.02, legacy_ln * 0.03):
            return 10.0
        return kv

    def _build_proxy_constraint(self, ctx, actual_net_load_kw: float, effective_power_cap_kw: float) -> HourlyNetworkConstraint:
        transformer_limit = ctx.transformer_active_power_limit_kw
        max_charge_kw = float(effective_power_cap_kw)
        max_discharge_kw = float(effective_power_cap_kw)
        if transformer_limit is not None:
            max_charge_kw = min(max_charge_kw, max(0.0, float(transformer_limit) - float(actual_net_load_kw)))
        return HourlyNetworkConstraint(
            max_charge_kw=max_charge_kw,
            max_discharge_kw=max_discharge_kw,
            service_power_cap_kw=float(effective_power_cap_kw),
            transformer_limit_kw=transformer_limit,
            voltage_penalty_yuan=0.0,
            notes=["OpenDSS 不可用，已回退到轻量代理约束。"],
            metadata={"opendss_used": False},
        )

    def _voltage_violation_pu(self, voltage_min_pu: float, voltage_max_pu: float) -> float:
        underv = max(0.0, float(self.config.voltage_min_pu) - float(voltage_min_pu))
        overv = max(0.0, float(voltage_max_pu) - float(self.config.voltage_max_pu))
        return float(underv + overv)

    @staticmethod
    def _line_loading_max_pct(rows: list[dict[str, Any]]) -> float | None:
        values: list[float] = []
        for row in rows:
            value = row.get("loading_pct")
            if value is None:
                continue
            try:
                parsed = float(value)
            except Exception:
                continue
            if math.isfinite(parsed):
                values.append(parsed)
        return float(max(values)) if values else None

    @staticmethod
    def _line_current_max_a(rows: list[dict[str, Any]]) -> float | None:
        values: list[float] = []
        for row in rows:
            try:
                parsed = float(row.get("current_a") or 0.0)
            except Exception:
                continue
            if math.isfinite(parsed):
                values.append(parsed)
        return float(max(values)) if values else None

    def get_hour_constraint(
        self,
        ctx,
        day_index: int,
        hour_index: int,
        actual_net_load_kw: float,
        planned_charge_kw: float,
        planned_discharge_kw: float,
        planned_service_kw: float,
        rated_power_kw: float,
        rated_energy_kwh: float,
        effective_power_cap_kw: float,
        current_soc: float,
        extra: dict[str, Any] | None = None,
    ) -> HourlyNetworkConstraint:
        if self._backend is None:
            if not self.config.allow_engine_fallback:
                raise RuntimeError("OpenDSS oracle 已启用，但 OpenDSS 后端不可用。")
            return self._build_proxy_constraint(ctx, actual_net_load_kw, effective_power_cap_kw)

        transformer_limit = ctx.transformer_active_power_limit_kw
        max_charge_kw = float(effective_power_cap_kw)
        max_discharge_kw = float(effective_power_cap_kw)
        if transformer_limit is not None:
            max_charge_kw = min(max_charge_kw, max(0.0, float(transformer_limit) - float(actual_net_load_kw)))

        target_bus = self._resolve_target_bus(ctx)
        if not target_bus:
            if not self.config.allow_engine_fallback:
                raise RuntimeError(f"场景 {getattr(ctx, 'internal_model_id', '')} 缺少 OpenDSS 目标母线。")
            return self._build_proxy_constraint(ctx, actual_net_load_kw, effective_power_cap_kw)
        target_load = self._resolve_target_load(ctx)
        kv_ln = self._normalize_distribution_base_kv(ctx.meta.get("target_kv_ln", self.config.target_kv_ln))
        q_to_p_ratio = float(getattr(ctx, "q_to_p_ratio", 0.25))
        reference_kw = ctx.meta.get("static_load_reference_kw", ctx.meta.get("inference_peak_kw", None))
        runtime_manifest_path = self._resolve_network_runtime_manifest_path(ctx)

        notes: list[str] = []
        metadata: dict[str, Any] = {
            "opendss_used": True,
            "target_bus": target_bus,
            "target_load": target_load,
            "reference_kw": reference_kw,
            "network_runtime_manifest_path": str(runtime_manifest_path) if runtime_manifest_path else None,
        }

        try:
            runtime_entries = self._load_network_runtime_entries(ctx) if runtime_manifest_path else []
            self._backend.compile(self.master_dss_path)
            self._backend.clear_temp()
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
                metadata["network_runtime_loads_applied"] = len(runtime_entries)
                metadata["reference_kw"] = None
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
            metadata["opendss_baseline_converged"] = bool(baseline_converged)
            loss_base_kw, loss_base_kvar = self._backend.total_losses_kw_kvar()
            if loss_base_kw is not None:
                metadata["opendss_loss_baseline_kw"] = float(loss_base_kw)
            if loss_base_kvar is not None:
                metadata["opendss_loss_baseline_kvar"] = float(loss_base_kvar)
            v_base_all = self._backend.all_bus_vmag_pu()
            if not v_base_all:
                v_base_all = self._backend.target_bus_vmag_pu(target_bus)
            baseline_violation_pu = 0.0
            if v_base_all:
                v_base_min = min(v_base_all)
                v_base_max = max(v_base_all)
                baseline_violation_pu = self._voltage_violation_pu(v_base_min, v_base_max)
                metadata["baseline_voltage_min_pu"] = float(v_base_min)
                metadata["baseline_voltage_max_pu"] = float(v_base_max)
                metadata["baseline_voltage_violation_pu"] = float(baseline_violation_pu)
                if bool((extra or {}).get("capture_network_trace", False)):
                    metadata["baseline_bus_voltages"] = self._backend.bus_voltage_summaries()
                    baseline_line_currents = self._backend.line_current_summaries()
                    metadata["baseline_line_currents"] = baseline_line_currents
                    if baseline_line_currents:
                        metadata["baseline_line_current_max_a"] = float(
                            max(float(row.get("current_a") or 0.0) for row in baseline_line_currents)
                        )
                        baseline_loading_values = [
                            float(row["loading_pct"])
                            for row in baseline_line_currents
                            if row.get("loading_pct") is not None
                        ]
                        if baseline_loading_values:
                            metadata["baseline_line_loading_max_pct"] = float(max(baseline_loading_values))

            v_base_target = self._backend.target_bus_vmag_pu(target_bus)
            baseline_target_violation_pu = 0.0
            if v_base_target:
                target_base_min = min(v_base_target)
                target_base_max = max(v_base_target)
                baseline_target_violation_pu = self._voltage_violation_pu(target_base_min, target_base_max)
                metadata["baseline_target_voltage_min_pu"] = float(target_base_min)
                metadata["baseline_target_voltage_max_pu"] = float(target_base_max)
                metadata["baseline_target_voltage_violation_pu"] = float(baseline_target_violation_pu)
            elif v_base_all:
                baseline_target_violation_pu = baseline_violation_pu
                metadata["baseline_target_voltage_min_pu"] = float(min(v_base_all))
                metadata["baseline_target_voltage_max_pu"] = float(max(v_base_all))
                metadata["baseline_target_voltage_violation_pu"] = float(baseline_target_violation_pu)

            baseline_target_line_currents = self._backend.target_line_current_summaries(target_bus)
            baseline_target_current_max = self._line_current_max_a(baseline_target_line_currents)
            baseline_target_loading_max = self._line_loading_max_pct(baseline_target_line_currents)
            metadata["baseline_target_line_currents"] = baseline_target_line_currents
            metadata["baseline_target_line_current_max_a"] = float(baseline_target_current_max or 0.0)
            metadata["baseline_target_line_loading_max_pct"] = float(baseline_target_loading_max or 0.0)
            metadata["baseline_target_line_overload_pct"] = float(max(0.0, (baseline_target_loading_max or 0.0) - 100.0))

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
            storage_converged = self._backend.solve()
            metadata["opendss_storage_converged"] = bool(storage_converged)
            metadata["opendss_solve_converged"] = bool(baseline_converged and storage_converged)
            loss_with_storage_kw, loss_with_storage_kvar = self._backend.total_losses_kw_kvar()
            if loss_with_storage_kw is not None:
                metadata["opendss_loss_with_storage_kw"] = float(loss_with_storage_kw)
            if loss_with_storage_kvar is not None:
                metadata["opendss_loss_with_storage_kvar"] = float(loss_with_storage_kvar)
            if loss_base_kw is not None and loss_with_storage_kw is not None:
                loss_reduction_kw = float(loss_base_kw) - float(loss_with_storage_kw)
                metadata["opendss_loss_reduction_kw"] = loss_reduction_kw
                metadata["opendss_loss_reduction_kwh"] = loss_reduction_kw
                metadata["opendss_loss_reduction_positive_kwh"] = max(0.0, loss_reduction_kw)
                metadata["opendss_loss_source"] = "opendss_system_losses"

            v_all = self._backend.all_bus_vmag_pu()
            if not v_all:
                v_all = self._backend.target_bus_vmag_pu(target_bus)
            if not v_all:
                if not self.config.allow_engine_fallback:
                    raise RuntimeError(
                        f"OpenDSS 潮流完成但未返回电压结果：day={int(day_index) + 1}, hour={int(hour_index)}。"
                    )
                return self._build_proxy_constraint(ctx, actual_net_load_kw, effective_power_cap_kw)

            v_min = min(v_all)
            v_max = max(v_all)
            metadata["voltage_min_pu"] = float(v_min)
            metadata["voltage_max_pu"] = float(v_max)
            v_target = self._backend.target_bus_vmag_pu(target_bus)
            control_v_min = float(v_min)
            control_v_max = float(v_max)
            if v_target:
                target_v_min = min(v_target)
                target_v_max = max(v_target)
                target_violation_pu = self._voltage_violation_pu(target_v_min, target_v_max)
                target_incremental_violation_pu = max(0.0, target_violation_pu - baseline_target_violation_pu)
                control_v_min = float(target_v_min)
                control_v_max = float(target_v_max)
                metadata["target_voltage_min_pu"] = float(target_v_min)
                metadata["target_voltage_max_pu"] = float(target_v_max)
                metadata["target_voltage_violation_pu"] = float(target_violation_pu)
                metadata["storage_target_voltage_violation_increment_pu"] = float(target_incremental_violation_pu)
            else:
                target_violation_pu = self._voltage_violation_pu(v_min, v_max)
                target_incremental_violation_pu = max(0.0, target_violation_pu - baseline_target_violation_pu)
                metadata["target_voltage_min_pu"] = float(v_min)
                metadata["target_voltage_max_pu"] = float(v_max)
                metadata["target_voltage_violation_pu"] = float(target_violation_pu)
                metadata["storage_target_voltage_violation_increment_pu"] = float(target_incremental_violation_pu)

            target_line_currents = self._backend.target_line_current_summaries(target_bus)
            target_current_max = self._line_current_max_a(target_line_currents)
            target_loading_max = self._line_loading_max_pct(target_line_currents)
            target_line_overload_pct = max(0.0, (target_loading_max or 0.0) - 100.0)
            baseline_target_line_overload_pct = float(metadata.get("baseline_target_line_overload_pct") or 0.0)
            metadata["target_line_currents"] = target_line_currents
            metadata["target_line_current_max_a"] = float(target_current_max or 0.0)
            metadata["target_line_loading_max_pct"] = float(target_loading_max or 0.0)
            metadata["target_line_overload_pct"] = float(target_line_overload_pct)
            metadata["storage_target_line_overload_increment_pct"] = float(
                max(0.0, target_line_overload_pct - baseline_target_line_overload_pct)
            )
            if bool((extra or {}).get("capture_network_trace", False)):
                bus_voltages = self._backend.bus_voltage_summaries()
                line_currents = self._backend.line_current_summaries()
                metadata["bus_voltages"] = bus_voltages
                metadata["line_currents"] = line_currents
                if line_currents:
                    metadata["line_current_max_a"] = float(max(float(row.get("current_a") or 0.0) for row in line_currents))
                    loading_values = [
                        float(row["loading_pct"])
                        for row in line_currents
                        if row.get("loading_pct") is not None
                    ]
                    if loading_values:
                        metadata["line_loading_max_pct"] = float(max(loading_values))

            underv = max(0.0, float(self.config.voltage_min_pu) - control_v_min)
            overv = max(0.0, control_v_max - float(self.config.voltage_max_pu))
            storage_violation_pu = self._voltage_violation_pu(v_min, v_max)
            storage_incremental_violation_pu = max(0.0, storage_violation_pu - baseline_violation_pu)
            metadata["voltage_violation_pu"] = float(storage_violation_pu)
            metadata["storage_voltage_violation_increment_pu"] = float(storage_incremental_violation_pu)
            voltage_penalty_yuan = (
                float(self.config.voltage_penalty_coeff_yuan_per_pu)
                * float(storage_incremental_violation_pu)
            )
            if baseline_violation_pu > 0.0:
                notes.append("OpenDSS 基准潮流已存在电压越限，罚金仅按储能新增越限计入。")

            if underv > 0.0:
                max_charge_kw = 0.0
                notes.append(f"OpenDSS 检测到目标接入点欠压，最小电压 {control_v_min:.4f} pu，已将充电上限收紧为 0。")
            if overv > 0.0:
                max_discharge_kw = min(max_discharge_kw, max(0.0, float(planned_discharge_kw) * 0.25))
                notes.append(f"OpenDSS 检测到目标接入点过压，最大电压 {control_v_max:.4f} pu，已显著收紧放电上限。")

            service_cap = min(float(effective_power_cap_kw), max_charge_kw if planned_charge_kw > planned_discharge_kw else max_discharge_kw)
            return HourlyNetworkConstraint(
                max_charge_kw=max_charge_kw,
                max_discharge_kw=max_discharge_kw,
                service_power_cap_kw=max(0.0, service_cap),
                transformer_limit_kw=transformer_limit,
                voltage_penalty_yuan=voltage_penalty_yuan,
                notes=notes,
                metadata=metadata,
            )
        except Exception as exc:  # pragma: no cover
            if not self.config.allow_engine_fallback:
                raise
            if self.config.log_failures:
                print(f"[OpenDSS] 小时约束评估失败，回退轻量代理：{exc}")
            proxy = self._build_proxy_constraint(ctx, actual_net_load_kw, effective_power_cap_kw)
            proxy.notes.append(f"OpenDSS 小时约束失败：{type(exc).__name__}: {exc}")
            proxy.metadata.update(metadata)
            proxy.metadata["opendss_used"] = False
            return proxy
