import { useEffect, useMemo, useState } from 'react';
import { Link, Outlet, useLocation, useParams } from 'react-router-dom';
import { getProjectDashboard } from '../services/projects';
import type { DashboardPayload, StepPayload } from '../types/api';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { ThemeToggle } from '@/components/common/ThemeToggle';

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
    <div className="min-h-screen bg-background">
      <div className="mx-auto grid max-w-[1440px] grid-cols-[260px_1fr] gap-5 p-5">
        {/* Sidebar */}
        <aside className="sticky top-5 self-start rounded-2xl border border-sidebar-border bg-sidebar p-5 shadow-sm">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div className="text-[11px] font-semibold tracking-wider text-sidebar-foreground/50 uppercase">
              项目工作台
            </div>
            <ThemeToggle />
          </div>
          <div className="mb-4 text-xl font-extrabold tracking-tight text-sidebar-foreground">
            导航
          </div>

          {/* Project info card */}
          <div className="mb-5 rounded-xl bg-sidebar-accent/30 px-3.5 py-3">
            <div className="mb-1 text-sm font-bold text-sidebar-foreground">
              {dashboard?.project_name || '当前项目'}
            </div>
            <div className="text-xs text-sidebar-foreground/55">
              节点：{String(topologyCounts.nodes ?? dashboard?.node_count ?? 0)}
              {' ｜ '}
              负荷：{String(topologyCounts.load_nodes ?? dashboard?.load_node_count ?? 0)}
            </div>
          </div>

          {/* Step navigation */}
          <nav className="flex flex-col gap-1.5">
            {steps.map((step, index) => {
              const item = navItems.find((nav) => nav.key === step.key);
              const href = step.route || `/projects/${projectId}/${item?.path ?? step.key}`;
              const active = location.pathname === href;
              const status = String(step.status || 'not_started');
              const completed = status === 'completed';
              const inProgress = status === 'in_progress' || active;
              const failed = status === 'failed';
              const locked = !completed && !inProgress && status === 'not_started';

              const linkClass = cn(
                'flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-semibold transition-colors duration-150 no-underline',
                active && 'bg-sidebar-accent text-sidebar-foreground border border-sidebar-border shadow-sm',
                !active && !locked && 'text-sidebar-foreground/80 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground',
                locked && 'text-sidebar-foreground/35 cursor-not-allowed',
              );

              const circleClass = cn(
                'flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full text-xs font-bold',
                failed && 'bg-red-600 text-white',
                completed && 'bg-emerald-500 text-white',
                inProgress && !failed && !completed && 'bg-sidebar-primary text-sidebar-primary-foreground shadow-sm shadow-primary/30',
                locked && !failed && 'bg-sidebar-accent/60 text-sidebar-foreground/50',
              );

              return (
                <Link key={step.key} to={href} className={linkClass}>
                  <span className={circleClass}>
                    {completed ? '\u2713' : failed ? '!' : inProgress ? '\u203A' : index + 1}
                  </span>
                  <span className="flex-1">{step.label}</span>
                  {locked && (
                    <span className="text-xs text-sidebar-foreground/30">锁</span>
                  )}
                </Link>
              );
            })}
          </nav>

          {/* Progress bar */}
          <div className="mt-5 border-t border-sidebar-border pt-4">
            <div className="mb-2.5 text-xs font-bold text-sidebar-foreground/60">
              完成进度
            </div>
            <Progress value={progressPct} className="h-2 bg-sidebar-accent/50" />
            <div className="mt-2 text-right text-xs text-sidebar-foreground/50">
              {completedCount} / {steps.length} 步
            </div>
          </div>
        </aside>

        {/* Main content */}
        <main>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
