import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getProjectDashboard } from '../../services/projects';
import type { DashboardPayload } from '../../types/api';

function line(label: string, value: React.ReactNode) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, marginBottom: 8 }}>
      <span style={{ color: '#6b7280' }}>{label}</span>
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
    <div style={{ padding: 24, background: '#f8fafc', minHeight: '100vh' }}>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        <div style={{ marginBottom: 16 }}>
          <Link to="/projects" style={{ color: '#2563eb', textDecoration: 'none', fontWeight: 600 }}>
            ← 返回项目列表
          </Link>
        </div>

        <div style={heroStyle}>
          <div style={{ fontSize: 13, color: '#64748b', marginBottom: 8 }}>项目工作台</div>
          <h1 style={{ margin: 0, fontSize: 32 }}>{dashboard?.project_name || '项目总览'}</h1>
          <div style={{ color: '#6b7280', marginTop: 8 }}>
            {dashboard?.description || '查看项目状态、流程步骤和结果摘要。'}
          </div>
          <div style={{ marginTop: 12, fontSize: 13, color: '#6b7280' }}>项目 ID：{projectId}</div>
        </div>

        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16 }}>
          <Link to={`/projects/${projectId}/topology`} style={btnStyle}>拓扑建模</Link>
          <Link to={`/projects/${projectId}/assets`} style={btnStyle}>资产绑定</Link>
          <Link to={`/projects/${projectId}/build`} style={btnStyle}>构建校验</Link>
          <Link to={`/projects/${projectId}/solver`} style={btnStyle}>计算运行</Link>
          <Link to={`/projects/${projectId}/results`} style={btnStyle}>结果展示</Link>
          <button onClick={loadDashboard} disabled={loading} style={primaryBtnStyle}>
            {loading ? '刷新中...' : '刷新总览'}
          </button>
        </div>

        {error ? <div style={errorStyle}>加载失败：{error}</div> : null}

        <div style={grid4Style}>
          <Card title="节点数" value={dashboard?.node_count ?? '--'} />
          <Card title="线路数" value={dashboard?.edge_count ?? '--'} />
          <Card title="负荷节点数" value={dashboard?.load_node_count ?? '--'} />
          <Card title="已绑定 runtime 负荷数" value={dashboard?.runtime_bound_load_count ?? '--'} />
        </div>

        <div style={grid2Style}>
          <section style={sectionStyle}>
            <h2 style={sectionTitleStyle}>项目状态</h2>
            {line('电价表', dashboard?.has_tariff ? '已配置' : '未配置')}
            {line('设备库', dashboard?.has_device_library ? '已配置' : '未配置')}
            {line('构建条件', dashboard?.build_ready ? '已满足' : '未满足')}
            {line('最近任务', dashboard?.latest_solver_status || '--')}
          </section>

          <section style={sectionStyle}>
            <h2 style={sectionTitleStyle}>最近结果摘要</h2>
            {line('推荐策略', valueOf(latestSummary, ['strategy_name', 'strategy_id']))}
            {line('推荐功率', valueOf(latestSummary, ['rated_power_kw', 'power_kw'], ' kW'))}
            {line('推荐容量', valueOf(latestSummary, ['rated_energy_kwh', 'energy_kwh'], ' kWh'))}
            {line('NPV', valueOf(latestSummary, ['npv_wan'], ' 万元'))}
            {line('回收期', valueOf(latestSummary, ['simple_payback_years', 'payback_years'], ' 年'))}
          </section>
        </div>

        <section style={sectionStyle}>
          <h2 style={sectionTitleStyle}>流程步骤</h2>
          {!dashboard?.steps?.length ? (
            <div style={{ color: '#6b7280' }}>暂无步骤信息。</div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
              {dashboard.steps.map((step) => (
                <div key={step.key} style={stepCardStyle}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                    <strong>{step.label}</strong>
                    <span>{step.status}</span>
                  </div>
                  {step.detail ? <div style={{ color: '#6b7280', fontSize: 13, marginBottom: 10 }}>{step.detail}</div> : null}
                  {step.counts && Object.keys(step.counts).length > 0 ? (
                    <div style={{ marginBottom: 10 }}>
                      {Object.entries(step.counts).map(([k, v]) => (
                        <div key={k} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 13, marginBottom: 6 }}>
                          <span style={{ color: '#6b7280' }}>{k}</span>
                          <span>{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {step.route ? (
                    <Link to={step.route} style={{ color: '#2563eb', textDecoration: 'none', fontWeight: 600 }}>
                      进入页面 →
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

function Card(props: { title: string; value: React.ReactNode }) {
  return (
    <div style={metricCardStyle}>
      <div style={{ color: '#6b7280', fontSize: 13, marginBottom: 8 }}>{props.title}</div>
      <div style={{ fontSize: 28, fontWeight: 700 }}>{props.value}</div>
    </div>
  );
}

const heroStyle: React.CSSProperties = { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 16, padding: 20, marginBottom: 16 };
const grid4Style: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16, marginBottom: 16 };
const grid2Style: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16, marginBottom: 16 };
const sectionStyle: React.CSSProperties = { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 16, padding: 20 };
const sectionTitleStyle: React.CSSProperties = { margin: '0 0 14px 0', fontSize: 24 };
const btnStyle: React.CSSProperties = { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '10px 14px', background: '#fff', color: '#111827', textDecoration: 'none', border: '1px solid #d1d5db', borderRadius: 12, fontWeight: 600 };
const primaryBtnStyle: React.CSSProperties = { padding: '10px 14px', borderRadius: 12, border: '1px solid #111827', background: '#111827', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const errorStyle: React.CSSProperties = { background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c', borderRadius: 12, padding: 14, marginBottom: 16 };
const metricCardStyle: React.CSSProperties = { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 14, padding: 16 };
const stepCardStyle: React.CSSProperties = { border: '1px solid #e5e7eb', borderRadius: 12, padding: 14, background: '#fff' };
