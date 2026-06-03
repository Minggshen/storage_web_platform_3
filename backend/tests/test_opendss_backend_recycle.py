from __future__ import annotations

from types import SimpleNamespace

from storage_engine_project.simulation.opendss_network_constraint_oracle import (
    OpenDSSConstraintOracle,
    OpenDSSOracleConfig,
)


class _FakeBackend:
    def __init__(self, *, fail_first_solve: bool = False) -> None:
        self.fail_first_solve = fail_first_solve
        self.compile_calls = 0
        self.solve_calls = 0
        self.closed = False

    def compile(self, master_path: str) -> None:
        assert master_path
        self.compile_calls += 1

    def close(self) -> None:
        self.closed = True

    def clear_temp(self) -> None:
        return None

    def disable_temp_generators(self) -> None:
        return None

    def set_load_power(self, **kwargs) -> None:
        return None

    def set_or_add_target_load(self, **kwargs) -> None:
        return None

    def add_storage_dispatch(self, **kwargs) -> None:
        return None

    def edit_storage_dispatch(self, **kwargs) -> None:
        return None

    def solve(self) -> bool:
        self.solve_calls += 1
        if self.fail_first_solve and self.solve_calls == 1:
            raise RuntimeError("(482) OpenDSS Error Encountered in Solve: Out of memory.")
        return True

    def total_losses_kw_kvar(self) -> tuple[float, float]:
        return 1.0, 0.0

    def all_bus_vmag_pu(self) -> list[float]:
        return [1.0]

    def target_bus_vmag_pu(self, bus_name: str) -> list[float]:
        assert bus_name
        return [1.0]

    def target_line_current_summaries(self, target_bus_name: str) -> list[dict]:
        assert target_bus_name
        return []

    def bus_voltage_summaries(self) -> list[dict]:
        return []

    def line_current_summaries(self) -> list[dict]:
        return []


def _make_oracle(
    tmp_path,
    backend: _FakeBackend,
    *,
    replacement_backends: list[_FakeBackend] | None = None,
    solve_interval: int = 480,
    compile_interval: int = 240,
    retry_count: int = 1,
) -> OpenDSSConstraintOracle:
    master_path = tmp_path / "Master.dss"
    master_path.write_text("Clear\n", encoding="utf-8")

    oracle = OpenDSSConstraintOracle.__new__(OpenDSSConstraintOracle)
    oracle.config = OpenDSSOracleConfig(
        master_dss_path=str(master_path),
        target_bus_name="bus1",
        allow_engine_fallback=False,
        engine_recycle_solve_interval=solve_interval,
        engine_recycle_compile_interval=compile_interval,
        engine_error_retry_count=retry_count,
    )
    oracle.master_dss_path = str(master_path)
    oracle._backend = backend
    oracle._runtime_manifest_cache = {}
    oracle._current_dss_day = None
    oracle._edit_fallback_count = 0
    oracle._backend_solve_calls = 0
    oracle._backend_compile_calls = 0
    oracle._backend_recycle_count = 0

    replacements = iter(replacement_backends or [])

    def _init_backend():
        return next(replacements)

    oracle._init_backend = _init_backend
    return oracle


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(
        meta={},
        transformer_active_power_limit_kw=None,
        q_to_p_ratio=0.25,
        node_id=1,
        internal_model_id="case",
        node_dir="",
    )


def _evaluate(oracle: OpenDSSConstraintOracle, *, day: int = 0, hour: int = 0):
    return oracle.get_hour_constraint(
        ctx=_ctx(),
        day_index=day,
        hour_index=hour,
        actual_net_load_kw=100.0,
        planned_charge_kw=10.0,
        planned_discharge_kw=0.0,
        planned_service_kw=0.0,
        rated_power_kw=100.0,
        rated_energy_kwh=200.0,
        effective_power_cap_kw=100.0,
        current_soc=0.5,
        extra=None,
    )


def test_recycles_backend_on_hour_boundary_after_solve_interval(tmp_path) -> None:
    first_backend = _FakeBackend()
    second_backend = _FakeBackend()
    oracle = _make_oracle(
        tmp_path,
        first_backend,
        replacement_backends=[second_backend],
        solve_interval=2,
        compile_interval=100,
    )

    first = _evaluate(oracle, day=0, hour=0)
    second = _evaluate(oracle, day=0, hour=1)

    assert first_backend.solve_calls == 2
    assert first_backend.closed is True
    assert second_backend.compile_calls == 1
    assert second_backend.solve_calls == 2
    assert first.metadata["opendss_backend_recycle_count"] == 0
    assert second.metadata["opendss_backend_recycle_count"] == 1
    assert second.metadata["opendss_backend_solve_calls_since_recycle"] == 2


def test_recycles_backend_and_retries_current_hour_on_oom(tmp_path) -> None:
    first_backend = _FakeBackend(fail_first_solve=True)
    second_backend = _FakeBackend()
    oracle = _make_oracle(
        tmp_path,
        first_backend,
        replacement_backends=[second_backend],
        solve_interval=100,
        compile_interval=100,
        retry_count=1,
    )

    result = _evaluate(oracle, day=0, hour=0)

    assert first_backend.solve_calls == 1
    assert first_backend.closed is True
    assert second_backend.compile_calls == 1
    assert second_backend.solve_calls == 2
    assert result.metadata["opendss_backend_retry_attempt"] == 1
    assert result.metadata["opendss_backend_recycle_count"] == 1
