import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getProjectDashboard } from '../../services/projects';
import type { DashboardPayload } from '../../types/api';
import { Button } from '@/components/ui/button';

function line(label: string, value: React.ReactNode) {
  return (
    <div className="flex items-center justify-between gap-4 mb-2">
      <span className="text-muted-foreground">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

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

function MetricCard(props: { title: string; value: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4">
      <div className="mb-2 text-[13px] text-muted-foreground">{props.title}</div>
      <div className="text-[28px] font-bold text-foreground">{props.value}</div>
    </div>
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

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-[1200px]">
        <div className="mb-4">
          <Link to="/projects" className="font-semibold text-primary no-underline hover:underline">
            &larr; 返回项目列表
          </Link>
        </div>

        {/* Hero */}
        <div className="mb-4 rounded-2xl border border-border bg-card p-5">
          <div className="mb-2 text-[13px] text-muted-foreground">项目工作台</div>
          <h1 className="m-0 text-[32px] font-extrabold tracking-tight text-foreground">
            {dashboard?.project_name || '项目总览'}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {dashboard?.description || '查看项目状态、流程步骤和结果摘要。'}
          </p>
          <div className="mt-3 text-[13px] text-muted-foreground">项目 ID：{projectId}</div>
        </div>

        {/* Quick nav buttons */}
        <div className="mb-4 flex gap-2.5 flex-wrap">
          <Button variant="outline" size="sm" asChild>
            <Link to={`/projects/${projectId}/topology`}>拓扑建模</Link>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link to={`/projects/${projectId}/assets`}>资产绑定</Link>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link to={`/projects/${projectId}/build`}>构建校验</Link>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link to={`/projects/${projectId}/solver`}>计算运行</Link>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link to={`/projects/${projectId}/results`}>结果展示</Link>
          </Button>
          <Button size="sm" onClick={loadDashboard} disabled={loading}>
            {loading ? '刷新中...' : '刷新总览'}
          </Button>
        </div>

        {error ? (
          <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3.5 text-sm text-red-600">
            加载失败：{error}
          </div>
        ) : null}

        {/* Metric cards */}
        <div className="mb-4 grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
          <MetricCard title="节点数" value={dashboard?.node_count ?? '--'} />
          <MetricCard title="线路数" value={dashboard?.edge_count ?? '--'} />
          <MetricCard title="负荷节点数" value={dashboard?.load_node_count ?? '--'} />
          <MetricCard title="已绑定 runtime 负荷数" value={dashboard?.runtime_bound_load_count ?? '--'} />
        </div>

        {/* Status + Latest Results */}
        <div className="mb-4 grid grid-cols-[repeat(auto-fit,minmax(320px,1fr))] gap-4">
          <section className="rounded-2xl border border-border bg-card p-5">
            <h2 className="mb-3.5 mt-0 text-2xl font-bold text-foreground">项目状态</h2>
            {line('电价表', dashboard?.has_tariff ? '已配置' : '未配置')}
            {line('设备库', dashboard?.has_device_library ? '已配置' : '未配置')}
            {line('构建条件', dashboard?.build_ready ? '已满足' : '未满足')}
            {line('最近任务', dashboard?.latest_solver_status || '--')}
          </section>

          <section className="rounded-2xl border border-border bg-card p-5">
            <h2 className="mb-3.5 mt-0 text-2xl font-bold text-foreground">最近结果摘要</h2>
            {line('推荐策略', valueOf(latestSummary, ['strategy_name', 'strategy_id']))}
            {line('推荐功率', valueOf(latestSummary, ['rated_power_kw', 'power_kw'], ' kW'))}
            {line('推荐容量', valueOf(latestSummary, ['rated_energy_kwh', 'energy_kwh'], ' kWh'))}
            {line('NPV', valueOf(latestSummary, ['npv_wan'], ' 万元'))}
            {line('回收期', valueOf(latestSummary, ['simple_payback_years', 'payback_years'], ' 年'))}
          </section>
        </div>

        {/* Steps */}
        <section className="rounded-2xl border border-border bg-card p-5">
          <h2 className="mb-3.5 mt-0 text-2xl font-bold text-foreground">流程步骤</h2>
          {!dashboard?.steps?.length ? (
            <div className="text-muted-foreground">暂无步骤信息。</div>
          ) : (
            <div className="grid gap-3.5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
              {dashboard.steps.map((step) => (
                <div key={step.key} className="rounded-xl border border-border bg-background p-3.5">
                  <div className="mb-2.5 flex justify-between gap-2">
                    <strong>{step.label}</strong>
                    <span className="text-sm text-muted-foreground">{step.status}</span>
                  </div>
                  {step.detail ? <div className="mb-2.5 text-[13px] text-muted-foreground">{step.detail}</div> : null}
                  {step.counts && Object.keys(step.counts).length > 0 ? (
                    <div className="mb-2.5">
                      {Object.entries(step.counts).map(([k, v]) => (
                        <div key={k} className="flex justify-between gap-3 mb-1.5 text-[13px]">
                          <span className="text-muted-foreground">{k}</span>
                          <span>{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {step.route ? (
                    <Link to={step.route} className="font-semibold text-primary no-underline hover:underline">
                      进入页面 &rarr;
                    </Link>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
