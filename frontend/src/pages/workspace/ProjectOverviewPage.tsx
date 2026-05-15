import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getProjectDashboard } from '../../services/projects';
import type { DashboardPayload } from '../../types/api';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import StepBadge from '@/components/common/StepBadge';

function valueOf(summary: Record<string, unknown> | undefined, keys: string[], suffix = ''): string {
  if (!summary) return '--';
  for (const key of keys) {
    const v = summary[key];
    if (v !== null && v !== undefined && v !== '') {
      return `${String(v)}${suffix}`;
    }
  }
  return '--';
}

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
        ok
          ? 'border border-emerald-500/30 bg-emerald-500/10 text-emerald-600'
          : 'border border-amber-500/30 bg-amber-500/10 text-amber-600'
      }`}
    >
      {label} {ok ? '✓' : '✗'}
    </span>
  );
}

export default function ProjectOverviewPage() {
  const { projectId = '' } = useParams();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);

  async function loadDashboard() {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await getProjectDashboard(projectId);
      setDashboard(res.dashboard);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setDashboard(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDashboard();
  }, [projectId]);

  const latestSummary = dashboard?.latest_summary;
  const summaryRecord = latestSummary as Record<string, unknown> | undefined;

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto">

        {error && <ErrorBanner message={error} />}

        {/* Step 1: Project Overview */}
        <section className="mb-5 rounded-2xl border border-border bg-card p-5">
          <StepBadge step={1} label="项目概况" />
          <div className="flex items-center justify-between gap-6 flex-wrap">
            <div className="min-w-0">
              <h1 className="text-2xl font-extrabold tracking-tight text-foreground">
                {dashboard?.project_name || '项目总览'}
              </h1>
              <p className="mt-1 text-sm text-muted-foreground">
                {dashboard?.description || '查看项目状态、流程步骤和结果摘要。'}
                <span className="ml-3 text-xs text-muted-foreground/70">ID：{projectId}</span>
              </p>
              <Link to="/projects" className="mt-1 inline-block text-xs text-primary hover:underline">
                &larr; 返回项目列表
              </Link>
            </div>
            <div className="flex gap-5">
              <div className="text-center">
                <div className="text-2xl font-extrabold text-primary">{dashboard?.node_count ?? '--'}</div>
                <div className="text-xs text-muted-foreground">节点</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-extrabold text-primary">{dashboard?.edge_count ?? '--'}</div>
                <div className="text-xs text-muted-foreground">线路</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-extrabold text-primary">{dashboard?.load_node_count ?? '--'}</div>
                <div className="text-xs text-muted-foreground">负荷</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-extrabold text-emerald-500">{dashboard?.runtime_bound_load_count ?? '--'}</div>
                <div className="text-xs text-muted-foreground">已绑定</div>
              </div>
            </div>
          </div>
        </section>

        {/* Step 2: Status & Summary */}
        <section className="mb-5 rounded-2xl border border-border bg-card p-5">
          <StepBadge step={2} label="项目状态 & 最佳方案摘要" />

          {/* Config status badges row */}
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-muted-foreground">配置</span>
            <StatusBadge ok={Boolean(dashboard?.has_tariff)} label="电价表" />
            <StatusBadge ok={Boolean(dashboard?.has_device_library)} label="设备库" />
            <StatusBadge ok={Boolean(dashboard?.build_ready)} label="已构建" />
            <StatusBadge
              ok={dashboard?.latest_solver_status !== 'failed'}
              label={`任务 ${dashboard?.latest_solver_status || '--'}`}
            />
          </div>

          <div className="mb-3 border-t border-border" />

          {/* Result metrics row */}
          <div className="grid grid-cols-5 gap-4">
            <div>
              <div className="text-xs text-muted-foreground">NPV</div>
              <div className="text-xl font-extrabold text-primary">
                {valueOf(summaryRecord, ['npv_wan'], ' 万元')}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">回收期</div>
              <div className="text-xl font-extrabold text-foreground">
                {valueOf(summaryRecord, ['simple_payback_years', 'payback_years'], ' 年')}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">推荐功率</div>
              <div className="text-xl font-extrabold text-foreground">
                {valueOf(summaryRecord, ['rated_power_kw', 'power_kw'], ' kW')}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">推荐容量</div>
              <div className="text-xl font-extrabold text-foreground">
                {valueOf(summaryRecord, ['rated_energy_kwh', 'energy_kwh'], ' kWh')}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">推荐策略</div>
              <div className="text-lg font-bold text-foreground">
                {valueOf(summaryRecord, ['strategy_name', 'strategy_id'])}
              </div>
            </div>
          </div>
        </section>

        {/* Step 3: Workflow Progress */}
        <section className="rounded-2xl border border-border bg-card p-5">
          <StepBadge step={3} label="工程流程进度" />
          {!dashboard?.steps?.length ? (
            <div className="text-muted-foreground">暂无步骤信息。</div>
          ) : (
            <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(6, 1fr)' }}>
              {dashboard.steps.map((step) => {
                const completed = step.status === 'completed';
                const inProgress = step.status === 'in_progress';
                const failed = step.status === 'failed';
                const notStarted = step.status === 'not_started';

                return (
                  <Link
                    key={step.key}
                    to={step.route || '#'}
                    className={`rounded-xl border p-3.5 text-center no-underline transition-colors ${
                      completed
                        ? 'border-emerald-500/30 bg-emerald-500/5'
                        : inProgress
                          ? 'border-amber-500/30 bg-amber-500/5'
                          : failed
                            ? 'border-red-500/30 bg-red-500/5'
                            : 'border-border bg-muted/20'
                    }`}
                  >
                    <div
                      className={`text-sm font-bold ${
                        completed
                          ? 'text-emerald-600'
                          : inProgress
                            ? 'text-amber-600'
                            : failed
                              ? 'text-red-600'
                              : 'text-muted-foreground'
                      }`}
                    >
                      {completed ? '✓' : inProgress ? '●' : failed ? '!' : '--'}
                    </div>
                    <div
                      className={`mt-1 text-xs ${
                        notStarted ? 'text-muted-foreground' : 'text-foreground'
                      }`}
                    >
                      {step.label}
                    </div>
                    {step.detail && (
                      <div className="mt-1 text-[11px] text-muted-foreground">{step.detail}</div>
                    )}
                  </Link>
                );
              })}
            </div>
          )}
        </section>

        {/* Refresh button */}
        <div className="mt-4 text-center">
          <button
            onClick={loadDashboard}
            disabled={loading}
            className="rounded-xl border border-border bg-card px-4 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
          >
            {loading ? '刷新中...' : '刷新总览'}
          </button>
        </div>
      </div>
    </div>
  );
}
