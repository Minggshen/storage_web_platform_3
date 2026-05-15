import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { cancelSolverTask, fetchLatestSolverTask, fetchTaskLogs, rerunSolver } from '../../services/solver';
import { fetchProjectTopology } from '../../services/topology';
import type { SolverTask } from '../../types/api';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import StepBadge from '@/components/common/StepBadge';

type TargetOption = {
  id: string;
  label: string;
  nodeId?: string | number | null;
  dssLoadName?: string;
  busName?: string;
};

type ProgressInfo = {
  percent: number;
  label: string;
  detail: string;
};

type ProgressSnapshot = ProgressInfo & {
  taskId: string;
};

function formatDurationSeconds(task: SolverTask | null): string {
  if (!task?.started_at || !task?.completed_at) return '--';
  const start = new Date(task.started_at).getTime();
  const end = new Date(task.completed_at).getTime();
  if (Number.isNaN(start) || Number.isNaN(end)) return '--';
  return `${Math.max(Math.round((end - start) / 1000), 0)} s`;
}

function Mini(props: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-card p-3.5">
      <div className="mb-2 text-[13px] text-muted-foreground">{props.label}</div>
      <div className="font-bold text-foreground">{props.value}</div>
    </div>
  );
}

export default function SolverPage() {
  const { projectId = '' } = useParams();
  const [latestTask, setLatestTask] = useState<SolverTask | null>(null);
  const [logsTask, setLogsTask] = useState<SolverTask | null>(null);
  const [loading, setLoading] = useState(false);
  const [rerunning, setRerunning] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [populationSize, setPopulationSize] = useState('16');
  const [generations, setGenerations] = useState('8');
  const [targetId, setTargetId] = useState('');
  const [initialSoc, setInitialSoc] = useState('0.25');
  const [safetyTradeoff, setSafetyTradeoff] = useState(50);
  const [targetOptions, setTargetOptions] = useState<TargetOption[]>([]);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const [displayProgress, setDisplayProgress] = useState<ProgressSnapshot>({
    taskId: '',
    percent: 0,
    label: '暂无运行任务',
    detail: '启动求解后将自动显示进度。',
  });

  const activeTaskId = latestTask?.task_id;

  async function loadTargetOptions() {
    if (!projectId) return;
    const topology = await fetchProjectTopology(projectId);
    const options = topology.nodes
      .filter((node) => String(node.type) === 'load')
      .map((node) => {
        const params = typeof node.params === 'object' && node.params !== null
          ? (node.params as Record<string, unknown>)
          : {};
        return { node, params };
      })
      .filter(({ params }) => toBool(params.optimize_storage, false))
      .map(({ node, params }) => {
        const id = safeInternalId(String(node.id ?? ''));
        const name = String(node.name ?? node.id ?? id);
        const nodeId = params.node_id as string | number | null | undefined;
        const dssLoadName = typeof params.dss_load_name === 'string' ? params.dss_load_name : '';
        const busName = typeof params.dss_bus_name === 'string' ? params.dss_bus_name : '';
        const suffix = [
          nodeId ? `node_id=${nodeId}` : '',
          dssLoadName ? dssLoadName : '',
          busName ? busName : '',
        ].filter(Boolean).join(' / ');
        return {
          id,
          label: suffix ? `${name} (${suffix})` : name,
          nodeId,
          dssLoadName,
          busName,
        };
      })
      .filter((option) => option.id);

    setTargetOptions(options);
    setTargetId((current) => {
      if (current && options.some((option) => option.id === current)) return current;
      return options.length === 1 ? options[0].id : '';
    });
  }

  async function refreshTask(silent = false) {
    if (!projectId) return;
    if (!silent) setLoading(true);
    setError(null);
    try {
      const task = await fetchLatestSolverTask(projectId);
      setLatestTask(task);
      if (task?.task_id) {
        const logs = await fetchTaskLogs(task.task_id, projectId);
        setLogsTask(logs);
      } else {
        setLogsTask(null);
      }
      setLastUpdatedAt(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (!silent) setLoading(false);
    }
  }

  async function onRerun() {
    if (!projectId) return;
    setRerunning(true);
    setError(null);
    try {
      await rerunSolver(projectId, {
        task_name: 'ui_solver_run',
        population_size: Math.max(Number(populationSize) || 1, 1),
        generations: Math.max(Number(generations) || 1, 1),
        target_id: targetId.trim() || undefined,
        output_subdir_name: 'integrated_optimization',
        initial_soc: clampInputNumber(initialSoc, 0, 1, 0.25),
        safety_economy_tradeoff: safetyTradeoff / 100,
      });
      await refreshTask(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRerunning(false);
    }
  }

  async function onCancelRun() {
    if (!projectId || !latestTask?.task_id) return;
    setCancelling(true);
    setError(null);
    try {
      const task = await cancelSolverTask(projectId, latestTask.task_id);
      setLatestTask(task);
      const logs = await fetchTaskLogs(task.task_id, projectId);
      setLogsTask(logs);
      setLastUpdatedAt(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCancelling(false);
    }
  }

  useEffect(() => {
    loadTargetOptions().catch((err) => {
      setError(err instanceof Error ? err.message : String(err));
      setTargetOptions([]);
    });
    refreshTask(false);
    const timer = window.setInterval(() => {
      refreshTask(true);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [projectId]);

  const stdoutText = useMemo(() => logsTask?.stdout_text ?? '', [logsTask]);
  const stderrText = useMemo(() => logsTask?.stderr_text ?? '', [logsTask]);
  const rawProgress = useMemo(() => {
    const hinted = normalizeProgressHint(logsTask?.progress_hint ?? latestTask?.progress_hint);
    if (hinted) return hinted;
    return estimateSolverProgress(latestTask, stdoutText, Math.max(Number(generations) || 0, 0));
  }, [latestTask, logsTask?.progress_hint, stdoutText, generations]);
  const mustChooseTarget = targetOptions.length > 1 && !targetId;
  const hasNoTargetOptions = targetOptions.length === 0;
  const taskStatus = String(latestTask?.status ?? '').toLowerCase();
  const taskIsActive = taskStatus === 'running' || taskStatus === 'cancelling' || taskStatus === 'canceling';
  const stopDisabled = !activeTaskId || !taskIsActive || cancelling;
  const latestRunRequest = toRecord(logsTask?.metadata?.run_request ?? latestTask?.metadata?.run_request);
  const latestTaskTargetId = String(latestRunRequest?.target_id ?? '').trim();
  const latestTaskTargetOption = latestTaskTargetId
    ? targetOptions.find((option) => option.id === latestTaskTargetId) ?? null
    : null;

  // When a task is running, display the actual parameters used by that task (not local defaults).
  const freezeInputs = taskIsActive && latestRunRequest != null;
  const effectivePopulationSize = freezeInputs
    ? String(latestRunRequest?.population_size ?? populationSize)
    : populationSize;
  const effectiveGenerations = freezeInputs
    ? String(latestRunRequest?.generations ?? generations)
    : generations;
  const effectiveTargetId = freezeInputs
    ? String(latestRunRequest?.target_id ?? targetId)
    : targetId;
  const effectiveInitialSoc = freezeInputs
    ? String(latestRunRequest?.initial_soc ?? initialSoc)
    : initialSoc;
  const effectiveSafetyTradeoff = freezeInputs
    ? Math.round(Number(latestRunRequest?.safety_economy_tradeoff ?? 0.5) * 100)
    : safetyTradeoff;

  function tradeoffLabel(value: number): string {
    if (value <= 10) return '纯经济最优';
    if (value <= 30) return '偏重经济';
    if (value <= 70) return '经济安全并重';
    if (value <= 90) return '偏重安全';
    return '纯安全最优';
  }

  const selectedTargetOption = useMemo(
    () => targetOptions.find((option) => option.id === (freezeInputs ? effectiveTargetId : targetId)) ?? null,
    [targetOptions, targetId, freezeInputs, effectiveTargetId],
  );

  useEffect(() => {
    const taskId = String(latestTask?.task_id ?? '');
    const terminalStatus = new Set(['completed', 'failed', 'cancelled', 'canceled']);
    setDisplayProgress((previous) => {
      if (!taskId) return { taskId: '', ...rawProgress };
      if (previous.taskId !== taskId) return { taskId, ...rawProgress };
      if (terminalStatus.has(taskStatus)) {
        return { taskId, ...rawProgress, percent: Math.max(previous.percent, rawProgress.percent) };
      }
      return { taskId, ...rawProgress, percent: Math.max(previous.percent, rawProgress.percent) };
    });
  }, [latestTask?.task_id, rawProgress, taskStatus]);

  const runDisabled = loading || rerunning || taskIsActive || hasNoTargetOptions || mustChooseTarget;

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-[1280px]">
        {error && <ErrorBanner message={error} />}

        {/* Step 1: Run Parameters */}
        <section className="mb-5 rounded-2xl border border-border bg-card p-5">
          <StepBadge step={1} label="运行参数配置" />
          {freezeInputs && (
            <div className="mb-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3.5 py-2 text-[13px] font-semibold text-amber-700 dark:text-amber-400">
              任务运行中，参数已锁定为本次运行的实际设置。
            </div>
          )}
          <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
            <label htmlFor="solver-population-size" className="grid gap-1.5">
              <span className="text-[13px] font-bold text-foreground/70">population_size</span>
              <input
                id="solver-population-size"
                type="number" min={1} step={1}
                value={effectivePopulationSize}
                onChange={(e) => { if (!freezeInputs) setPopulationSize(e.target.value); }}
                readOnly={freezeInputs}
                className={`h-10 rounded-xl border px-2.5 text-sm ${freezeInputs ? 'border-border bg-muted/50 text-muted-foreground' : 'border-border bg-card'}`}
              />
            </label>
            <label htmlFor="solver-generations" className="grid gap-1.5">
              <span className="text-[13px] font-bold text-foreground/70">generations</span>
              <input
                id="solver-generations"
                type="number" min={1} step={1}
                value={effectiveGenerations}
                onChange={(e) => { if (!freezeInputs) setGenerations(e.target.value); }}
                readOnly={freezeInputs}
                className={`h-10 rounded-xl border px-2.5 text-sm ${freezeInputs ? 'border-border bg-muted/50 text-muted-foreground' : 'border-border bg-card'}`}
              />
            </label>
            <label htmlFor="solver-target-id" className="grid gap-1.5">
              <span className="text-[13px] font-bold text-foreground/70">配储目标负荷</span>
              <select
                id="solver-target-id"
                value={effectiveTargetId}
                onChange={(e) => { if (!freezeInputs) setTargetId(e.target.value); }}
                disabled={freezeInputs || hasNoTargetOptions}
                className="h-10 rounded-xl border border-border bg-card px-2.5 text-sm"
              >
                <option value="">
                  {hasNoTargetOptions ? '未找到候选配储目标' : '请选择候选配储目标'}
                </option>
                {targetOptions.map((option) => (
                  <option key={option.id} value={option.id}>{option.label}</option>
                ))}
              </select>
            </label>
            <label htmlFor="solver-initial-soc" className="grid gap-1.5">
              <span className="text-[13px] font-bold text-foreground/70">年度初始 SOC</span>
              <input
                id="solver-initial-soc"
                type="number" min={0} max={1} step={0.01}
                value={effectiveInitialSoc}
                onChange={(e) => { if (!freezeInputs) setInitialSoc(e.target.value); }}
                readOnly={freezeInputs}
                className={`h-10 rounded-xl border px-2.5 text-sm ${freezeInputs ? 'border-border bg-muted/50 text-muted-foreground' : 'border-border bg-card'}`}
              />
            </label>
          </div>

          {/* Safety-Economy Tradeoff Slider */}
          <div className="mt-4 rounded-xl border border-border bg-card p-4">
            <div className="mb-2 flex items-center justify-between gap-3">
              <span className="text-[13px] font-bold text-foreground/70">最终方案选取倾向</span>
              <span className="rounded-full bg-primary/10 px-3 py-0.5 text-xs font-bold text-primary">
                {tradeoffLabel(effectiveSafetyTradeoff)}
              </span>
            </div>
            <div className="mb-2 flex items-center justify-center gap-6 text-xs font-bold">
              <span className="text-red-600 dark:text-red-400">经济性 {100 - effectiveSafetyTradeoff}%</span>
              <span className="text-emerald-600 dark:text-emerald-400">安全性 {effectiveSafetyTradeoff}%</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs font-semibold text-red-600 dark:text-red-400 whitespace-nowrap">经济性</span>
              <input
                type="range"
                min={0}
                max={100}
                step={1}
                value={effectiveSafetyTradeoff}
                onChange={(e) => { if (!freezeInputs) setSafetyTradeoff(Number(e.target.value)); }}
                disabled={freezeInputs}
                className="h-2 w-full cursor-pointer appearance-none rounded-full bg-gradient-to-r from-red-400 via-amber-400 to-emerald-400 accent-primary"
              />
              <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 whitespace-nowrap">安全性</span>
            </div>
            <div className="mt-1.5 text-[12px] text-muted-foreground">
              控制最终储能方案选取时经济指标（NPV、回收期）与安全性指标（变压器越限、电压越限、线路过载）的相对权重。中间位置为经济与安全并重。
            </div>
          </div>

          {hasNoTargetOptions ? (
            <div className="mt-2.5 text-[13px] font-semibold text-amber-600">
              拓扑建模中没有设置为候选配储目标的负荷节点，请先把目标用户负荷的 optimize_storage 设置为"是"。
            </div>
          ) : mustChooseTarget ? (
            <div className="mt-2.5 text-[13px] font-semibold text-amber-600">
              当前有多个候选配储目标，请先选择本次要单独配储优化的负荷节点。
            </div>
          ) : (
            <div className="mt-2.5 text-[13px] text-muted-foreground">
              下拉列表只包含拓扑建模中设置为候选配储目标的负荷；其他启用负荷会作为背景负荷参与 OpenDSS 潮流。
            </div>
          )}

          {selectedTargetOption ? (
            <div className="mt-3 grid gap-2.5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
              <Mini label="当前选择目标" value={selectedTargetOption.label} />
              <Mini label="OpenDSS 母线" value={selectedTargetOption.busName || '--'} />
              <Mini label="DSS 负荷对象" value={selectedTargetOption.dssLoadName || '--'} />
              <Mini label="背景负荷策略" value="其他启用负荷参与全网潮流" />
            </div>
          ) : null}

          <div className="mt-3 text-[13px] text-muted-foreground">
            计算运行会在 fast_proxy 代表日和 full_recheck 全年重校核中调用 OpenDSS 全负荷潮流；页面会自动刷新任务状态和日志。
          </div>
          <div className="mt-2.5 text-[13px] text-muted-foreground">
            年度初始 SOC 只用于首日开局；进入全年逐日重校核后，次日初始 SOC 会自动继承前一日末 SOC，不再强制要求单日首尾回到固定值。
          </div>
        </section>

        {/* Step 2: Run Control */}
        <section className="mb-5 rounded-2xl border border-border bg-card p-5">
          <StepBadge step={2} label="运行控制" />
          <div className="mb-4 flex gap-2.5 flex-wrap items-center">
            <Button onClick={onRerun} disabled={runDisabled}>
              {rerunning ? '正在提交...' : taskIsActive ? (
                <span className="inline-flex items-center gap-1.5">
                  <span className="inline-block h-2.5 w-2.5 animate-pulse rounded-full bg-current" />
                  运行中...
                </span>
              ) : '启用求解'}
            </Button>
            <Button variant="destructive" onClick={onCancelRun} disabled={stopDisabled}>
              {cancelling || taskStatus === 'cancelling' || taskStatus === 'canceling' ? '终止中...' : '终止运行'}
            </Button>
          </div>
          <div className="mb-3 flex items-center justify-between gap-3 text-foreground">
            <strong>{displayProgress.label}</strong>
            <span>{displayProgress.percent.toFixed(0)}%</span>
          </div>
          <Progress value={displayProgress.percent} className="h-3" />
          <div className="mt-2.5 flex flex-wrap justify-between gap-3 text-[13px] text-muted-foreground">
            <span>{displayProgress.detail}</span>
            <span>{lastUpdatedAt ? `自动更新：${lastUpdatedAt.toLocaleTimeString('zh-CN')}` : '等待自动更新'}</span>
          </div>
        </section>

        {/* Step 3: Latest Task Info */}
        <section className="mb-5 rounded-2xl border border-border bg-card p-5">
          <StepBadge step={3} label="任务信息" />
          {!latestTask ? (
            <div className="text-muted-foreground">暂无任务。</div>
          ) : (
            <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
              <Mini label="任务 ID" value={latestTask.task_id} />
              <Mini label="状态" value={latestTask.status ?? '--'} />
              <Mini label="最近任务目标" value={latestTaskTargetOption?.label || latestTaskTargetId || '--'} />
              <Mini label="返回码" value={String(latestTask.return_code ?? '--')} />
              <Mini label="运行时长" value={formatDurationSeconds(latestTask)} />
              <Mini label="stdout 编码" value={logsTask?.stdout_encoding ?? '--'} />
              <Mini label="stderr 编码" value={logsTask?.stderr_encoding ?? '--'} />
            </div>
          )}
        </section>

        {/* Step 4: Logs */}
        <section className="rounded-2xl border border-border bg-card p-5">
          <StepBadge step={4} label="日志输出" />
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))' }} aria-live="polite">
          <section>
            <h3 className="mb-2 mt-0 text-sm font-semibold text-muted-foreground">stdout 日志</h3>
            {!activeTaskId ? (
              <div className="text-muted-foreground">暂无日志。</div>
            ) : (
              <pre className="whitespace-pre-wrap break-words rounded-xl border border-border bg-muted/30 p-3 text-sm max-h-[560px] min-h-[420px] overflow-auto overscroll-contain">
                {stdoutText || 'stdout 为空。'}
              </pre>
            )}
          </section>

          <section>
            <h3 className="mb-2 mt-0 text-sm font-semibold text-muted-foreground">stderr 日志</h3>
            <pre className="whitespace-pre-wrap break-words rounded-xl border border-border bg-muted/30 p-3 text-sm max-h-[560px] min-h-[420px] overflow-auto overscroll-contain">
              {stderrText || 'stderr 为空。'}
            </pre>
          </section>
        </div>
        </section>
      </div>
    </div>
  );
}

// ── utility functions (unchanged) ──

function safeInternalId(value: string): string {
  const out = value.trim().split('').map((ch) => (/[\p{L}\p{N}_-]/u.test(ch) ? ch : '_')).join('');
  return out.replace(/^_+|_+$/g, '') || 'unnamed';
}

function toBool(value: unknown, defaultValue: boolean): boolean {
  if (value === null || value === undefined || value === '') return defaultValue;
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return Boolean(Math.trunc(value));
  const text = String(value).trim().toLowerCase();
  if (['1', 'true', 'yes', 'y', 'on', '是', '启用'].includes(text)) return true;
  if (['0', 'false', 'no', 'n', 'off', '否', '停用'].includes(text)) return false;
  return defaultValue;
}

function toRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) return value as Record<string, unknown>;
  return null;
}

function estimateSolverProgress(task: SolverTask | null, stdoutText: string, requestedGenerations: number): ProgressInfo {
  if (!task) return { percent: 0, label: '暂无运行任务', detail: '启动求解后将自动显示进度。' };
  const parsed = parseStdoutProgress(stdoutText, requestedGenerations);
  const status = String(task.status ?? '').toLowerCase();
  if (status === 'completed') return { percent: 100, label: '求解完成', detail: '结果文件已生成，可进入结果展示页查看。' };
  if (status === 'failed') return { percent: Math.max(parsed.percent, 1), label: '求解失败', detail: parsed.detail || '请查看 stderr 日志定位失败原因。' };
  if (status === 'cancelled' || status === 'canceled') return { percent: Math.max(parsed.percent, 1), label: '运行已终止', detail: '用户已终止求解进程。' };
  if (status === 'cancelling' || status === 'canceling') return { percent: Math.max(parsed.percent, 1), label: '正在终止', detail: '已发送终止请求，等待求解器进程退出。' };
  if (status === 'running') return parsed.percent > 0 ? parsed : { percent: 3, label: '求解器已启动', detail: '正在等待求解器输出进度日志。' };
  return parsed.percent > 0 ? parsed : { percent: 0, label: task.status || '等待运行', detail: task.message || '暂无可解析进度。' };
}

function parseStdoutProgress(stdoutText: string, requestedGenerations: number): ProgressInfo {
  if (!stdoutText.trim()) return { percent: 0, label: '等待日志', detail: 'stdout 暂无进度输出。' };
  if (stdoutText.includes('已导出总体最优方案汇总')) return { percent: 100, label: '结果汇总已导出', detail: '求解流程已完成。' };

  const totalCases = lastNumber(stdoutText, /共加载\s+(\d+)\s+个待优化场景/g);
  const caseMatch = lastMatch(stdoutText, /开始场景优化\s+\[(\d+)\/(\d+)\]/g);
  const completedCases = countMatches(stdoutText, /场景完成：/g);
  const generationsFromLog = lastNumber(stdoutText, /优化参数：总代数=(\d+)/g);
  const generations = Math.max(generationsFromLog || requestedGenerations || 0, 1);
  const iteration = Math.min(lastNumber(stdoutText, /优化迭代\s+(\d+)/g) || 0, generations);
  const annualMatch = lastMatch(stdoutText, /年度运行[^\n]*进度\s+(\d+)\/365/g);
  const annualDay = annualMatch ? Math.min(Number(annualMatch[1]) || 0, 365) : 0;
  const proxyMatch = lastMatch(stdoutText, /年度运行[^\n]*代表日\s+(\d+)\/(\d+)/g);
  const proxyCurrent = proxyMatch ? (Number(proxyMatch[1]) || 0) : 0;
  const proxyTotal = proxyMatch ? (Number(proxyMatch[2]) || 0) : 0;
  const inFullRecheck = stdoutText.includes('full_recheck') && annualDay > 0;
  const inFinalRecheck = /对最终折中解执行全年重校核|调用 OpenDSS oracle 对最终折中解/.test(stdoutText);
  const inExport = stdoutText.includes('场景完成：') && completedCases > 0;

  const total = caseMatch ? Number(caseMatch[2]) : totalCases;
  const current = caseMatch ? Number(caseMatch[1]) : Math.min(completedCases + 1, total || 1);

  if (inExport && total && completedCases >= total) {
    return { percent: 95, label: '正在导出结果', detail: `全部 ${total} 个场景已完成，正在写入结果文件。` };
  }
  if (inFinalRecheck && annualDay > 0) {
    return { percent: clampProgress(35 + (annualDay / 365) * 55), label: '全年重校核（最耗时阶段）', detail: `OpenDSS 全年逐日潮流重校核 ${annualDay}/365 天。` };
  }
  if (inFullRecheck && annualDay > 0 && iteration >= generations) {
    return { percent: clampProgress(35 + (annualDay / 365) * 55), label: '全年重校核（最耗时阶段）', detail: `全年逐日重校核 ${annualDay}/365 天。` };
  }
  if (iteration >= generations && !inFullRecheck && !inFinalRecheck) {
    let detail = `GA 迭代已完成 ${generations} 代，正在评估最终种群。`;
    let percent = 32;
    if (proxyCurrent > 0 && proxyTotal > 0) { percent = clampProgress(30 + (proxyCurrent / proxyTotal) * 5); detail = `最终种群评估，代表日 ${proxyCurrent}/${proxyTotal}。`; }
    return { percent, label: '评估最终种群', detail };
  }
  if (total && current) {
    const iterationFraction = iteration > 0 ? iteration / generations : 0;
    const proxyFraction = (proxyCurrent > 0 && proxyTotal > 0) ? proxyCurrent / proxyTotal : 0;
    const inIterationFraction = iteration < generations ? iterationFraction + proxyFraction / generations : iterationFraction;
    const inCaseFraction = Math.min(inIterationFraction, 1.0);
    const completedFraction = completedCases / total;
    const runningFraction = (Math.max(current - 1, 0) + inCaseFraction) / total;
    const overallFraction = Math.max(completedFraction, runningFraction);
    const percent = clampProgress(5 + overallFraction * 25);
    let detail: string;
    if (proxyCurrent > 0 && proxyTotal > 0 && iteration > 0) detail = `第 ${current}/${total} 个场景，迭代 ${iteration}/${generations}，代表日 ${proxyCurrent}/${proxyTotal}。`;
    else if (iteration > 0) detail = `第 ${current}/${total} 个场景，优化迭代 ${iteration}/${generations}。`;
    else detail = `第 ${current}/${total} 个场景正在初始化。`;
    return { percent, label: '正在运行 GA 优化', detail };
  }
  if (iteration > 0) {
    return { percent: clampProgress(5 + (iteration / generations) * 25), label: '正在运行 GA 优化', detail: `优化迭代 ${iteration}/${generations}。` };
  }
  return { percent: 5, label: '求解器已启动', detail: '已捕获 stdout 日志，正在解析后续进度。' };
}

function lastMatch(text: string, pattern: RegExp): RegExpExecArray | null {
  let match: RegExpExecArray | null = null;
  let current: RegExpExecArray | null;
  pattern.lastIndex = 0;
  while ((current = pattern.exec(text)) !== null) match = current;
  return match;
}

function lastNumber(text: string, pattern: RegExp): number | null {
  const match = lastMatch(text, pattern);
  if (!match) return null;
  const number = Number(match[1]);
  return Number.isFinite(number) ? number : null;
}

function countMatches(text: string, pattern: RegExp): number {
  pattern.lastIndex = 0;
  return Array.from(text.matchAll(pattern)).length;
}

function clampProgress(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(99, value));
}

function clampInputNumber(value: string, min: number, max: number, fallback: number): number {
  if (!value.trim()) return fallback;
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.max(min, Math.min(max, number));
}

function normalizeProgressHint(value: SolverTask['progress_hint'] | undefined): ProgressInfo | null {
  if (!value) return null;
  const percent = Number(value.percent);
  const label = String(value.label ?? '').trim();
  const detail = String(value.detail ?? '').trim();
  if (!Number.isFinite(percent) || !label) return null;
  return { percent: Math.max(0, Math.min(percent, 100)), label, detail: detail || '后台已返回运行进度。' };
}
