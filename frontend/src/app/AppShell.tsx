import { useEffect, useMemo, useState } from 'react';
import { Link, Outlet, useLocation, useParams } from 'react-router-dom';
import { getProjectDashboard } from '../services/projects';
import type { DashboardPayload, StepPayload } from '../types/api';

const navItems = [
  { key: 'overview', label: '项目总览', path: 'overview' },
  { key: 'topology', label: '拓扑建模', path: 'topology' },
  { key: 'assets', label: '资产绑定', path: 'assets' },
  { key: 'build', label: '构建校验', path: 'build' },
  { key: 'solver', label: '计算运行', path: 'solver' },
  { key: 'results', label: '结果展示', path: 'results' },
];

export default function AppShell() {
  const location = useLocation();
  const { projectId = '' } = useParams();
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadDashboard() {
      if (!projectId) return;
      try {
        const data = await getProjectDashboard(projectId);
        if (!cancelled) setDashboard(data.dashboard);
      } catch {
        if (!cancelled) setDashboard(null);
      }
    }
    void loadDashboard();
    return () => {
      cancelled = true;
    };
  }, [projectId, location.pathname]);

  const steps = useMemo<StepPayload[]>(() => {
    if (dashboard?.steps?.length) return dashboard.steps;
    return navItems.map((item) => ({
      key: item.key,
      label: item.label,
      status: item.key === 'overview' ? 'completed' : 'not_started',
      route: `/projects/${projectId}/${item.path}`,
    }));
  }, [dashboard, projectId]);

  const completedCount = steps.filter((step) => step.status === 'completed').length;
  const progressPct = steps.length ? Math.round((completedCount / steps.length) * 100) : 0;
  const topologyStep = steps.find((step) => step.key === 'topology');
  const topologyCounts = topologyStep?.counts ?? {};

  return (
    <div style={{ minHeight: '100vh', background: '#f8fafc' }}>
      <div style={{ maxWidth: 1440, margin: '0 auto', display: 'grid', gridTemplateColumns: '240px 1fr', gap: 20, padding: 20 }}>
        <aside
          style={{
            background: '#ffffff',
            border: '1px solid #e5e7eb',
            borderRadius: 18,
            padding: 18,
            alignSelf: 'start',
            position: 'sticky',
            top: 20,
          }}
        >
          <div style={{ fontSize: 13, color: '#64748b', marginBottom: 8 }}>项目工作台</div>
          <div style={{ fontSize: 20, fontWeight: 800, color: '#0f172a', marginBottom: 14 }}>导航</div>
          <div style={navProjectCardStyle}>
            <div style={{ fontWeight: 800, color: '#0f172a', marginBottom: 8 }}>
              {dashboard?.project_name || '当前项目'}
            </div>
            <div style={{ color: '#64748b', fontSize: 13 }}>
              节点：{String(topologyCounts.nodes ?? dashboard?.node_count ?? 0)} ｜ 负荷：{String(topologyCounts.load_nodes ?? dashboard?.load_node_count ?? 0)}
            </div>
          </div>
          <div style={{ display: 'grid', gap: 8 }}>
            {steps.map((step, index) => {
              const item = navItems.find((nav) => nav.key === step.key);
              const href = step.route || `/projects/${projectId}/${item?.path ?? step.key}`;
              const active = location.pathname === href;
              const status = String(step.status || 'not_started');
              const completed = status === 'completed';
              const inProgress = status === 'in_progress' || active;
              const failed = status === 'failed';
              const locked = !completed && !inProgress && status === 'not_started';
              return (
                <Link
                  key={step.key}
                  to={href}
                  style={{
                    textDecoration: 'none',
                    borderRadius: 12,
                    padding: '10px 12px',
                    fontWeight: 700,
                    color: active ? '#1d4ed8' : locked ? '#9ca3af' : '#0f172a',
                    background: active ? '#dbeafe' : '#ffffff',
                    border: `1px solid ${active ? '#93c5fd' : '#ffffff'}`,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                  }}
                >
                  <span
                    style={{
                      width: 26,
                      height: 26,
                      borderRadius: 999,
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flex: '0 0 auto',
                      fontSize: 13,
                      color: completed || failed || inProgress ? '#ffffff' : '#9ca3af',
                      background: failed ? '#dc2626' : completed ? '#22c55e' : inProgress ? '#7aa2f7' : '#f1f5f9',
                    }}
                  >
                    {completed ? '✓' : failed ? '!' : inProgress ? '›' : index + 1}
                  </span>
                  <span style={{ flex: 1 }}>{step.label}</span>
                  {locked ? <span style={{ color: '#9ca3af', fontSize: 12 }}>锁</span> : null}
                </Link>
              );
            })}
          </div>
          <div style={progressBlockStyle}>
            <div style={{ color: '#64748b', fontWeight: 700, fontSize: 13, marginBottom: 10 }}>完成进度</div>
            <div style={progressTrackStyle}>
              <div style={{ ...progressFillStyle, width: `${progressPct}%` }} />
            </div>
            <div style={{ color: '#64748b', textAlign: 'right', marginTop: 8 }}>{completedCount} / {steps.length} 步</div>
          </div>
        </aside>

        <main>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

const navProjectCardStyle: React.CSSProperties = {
  background: '#f8fafc',
  borderRadius: 12,
  padding: 14,
  marginBottom: 18,
};

const progressBlockStyle: React.CSSProperties = {
  borderTop: '1px solid #e5e7eb',
  marginTop: 20,
  paddingTop: 16,
};

const progressTrackStyle: React.CSSProperties = {
  height: 8,
  borderRadius: 999,
  background: '#e5e7eb',
  overflow: 'hidden',
};

const progressFillStyle: React.CSSProperties = {
  height: '100%',
  borderRadius: 999,
  background: '#22c55e',
};
