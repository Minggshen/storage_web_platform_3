import React, { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { cancelSolverTask, fetchLatestSolverTask, fetchTaskLogs, rerunSolver } from '../../services/solver';
import { fetchProjectTopology } from '../../services/topology';
import type { SolverTask } from '../../types/api';

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
  const selectedTargetOption = useMemo(
    () => targetOptions.find((option) => option.id === targetId) ?? null,
    [targetOptions, targetId],
  );
  const latestRunRequest = toRecord(logsTask?.metadata?.run_request ?? latestTask?.metadata?.run_request);
  const latestTaskTargetId = String(latestRunRequest?.target_id ?? '').trim();
  const latestTaskTargetOption = latestTaskTargetId
    ? targetOptions.find((option) => option.id === latestTaskTargetId) ?? null
    : null;

  useEffect(() => {
    const taskId = String(latestTask?.task_id ?? '');
    const terminalStatus = new Set(['completed', 'failed', 'cancelled', 'canceled']);

    setDisplayProgress((previous) => {
      if (!taskId) {
        return { taskId: '', ...rawProgress };
      }
      if (previous.taskId !== taskId) {
        return { taskId, ...rawProgress };
      }
      if (terminalStatus.has(taskStatus)) {
        return {
          taskId,
          ...rawProgress,
          percent: Math.max(previous.percent, rawProgress.percent),
        };
      }
      return {
        taskId,
        ...rawProgress,
        percent: Math.max(previous.percent, rawProgress.percent),
      };
    });
  }, [latestTask?.task_id, rawProgress, taskStatus]);

  return (
    <div style={{ padding: 24, background: '#f8fafc', minHeight: '100vh' }}>
      <div style={{ maxWidth: 1280, margin: '0 auto' }}>
        <div style={{ marginBottom: 16 }}>
          <h1 style={{ margin: 0, fontSize: 32 }}>计算运行</h1>
          <div style={{ marginTop: 8, color: '#6b7280' }}>查看最近任务状态、日志文本，并支持重新发起任务。</div>
        </div>

        {error ? <div style={errorStyle}>加载失败：{error}</div> : null}

        <section style={sectionStyle}>
          <h2 style={sectionTitleStyle}>运行参数</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
            <label style={fieldStyle}>
              <span style={labelStyle}>population_size</span>
              <input
                type="number"
                min={1}
                step={1}
                value={populationSize}
                onChange={(event) => setPopulationSize(event.target.value)}
                style={inputStyle}
              />
            </label>
            <label style={fieldStyle}>
              <span style={labelStyle}>generations</span>
              <input
                type="number"
                min={1}
                step={1}
                value={generations}
                onChange={(event) => setGenerations(event.target.value)}
                style={inputStyle}
              />
            </label>
            <label style={fieldStyle}>
              <span style={labelStyle}>配储目标负荷</span>
              <select
                value={targetId}
                onChange={(event) => setTargetId(event.target.value)}
                style={inputStyle}
                disabled={hasNoTargetOptions}
              >
                <option value="">
                  {hasNoTargetOptions ? '未找到候选配储目标' : '请选择候选配储目标'}
                </option>
                {targetOptions.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label style={fieldStyle}>
              <span style={labelStyle}>年度初始 SOC</span>
              <input
                type="number"
                min={0}
                max={1}
                step={0.01}
                value={initialSoc}
                onChange={(event) => setInitialSoc(event.target.value)}
                style={inputStyle}
              />
            </label>
          </div>
          {hasNoTargetOptions ? (
            <div style={hintWarnStyle}>
              拓扑建模中没有设置为候选配储目标的负荷节点，请先把目标用户负荷的 optimize_storage 设置为“是”。
            </div>
          ) : mustChooseTarget ? (
            <div style={hintWarnStyle}>
              当前有多个候选配储目标，请先选择本次要单独配储优化的负荷节点。
            </div>
          ) : (
            <div style={hintStyle}>
              下拉列表只包含拓扑建模中设置为候选配储目标的负荷；其他启用负荷会作为背景负荷参与 OpenDSS 潮流。
            </div>
          )}
          {selectedTargetOption ? (
            <div style={targetDetailStyle}>
              <Mini label="当前选择目标" value={selectedTargetOption.label} />
              <Mini label="OpenDSS 母线" value={selectedTargetOption.busName || '--'} />
              <Mini label="DSS 负荷对象" value={selectedTargetOption.dssLoadName || '--'} />
              <Mini label="背景负荷策略" value="其他启用负荷参与全网潮流" />
            </div>
          ) : null}
          <div style={{ marginTop: 12, color: '#4b5563', fontSize: 13 }}>
            计算运行会在 fast_proxy 代表日和 full_recheck 全年重校核中调用 OpenDSS 全负荷潮流；页面会自动刷新任务状态和日志。
          </div>
          <div style={hintStyle}>
            年度初始 SOC 只用于首日开局；进入全年逐日重校核后，次日初始 SOC 会自动继承前一日末 SOC，不再强制要求单日首尾回到固定值。
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 16 }}>
            <button
              onClick={onRerun}
              disabled={loading || rerunning || taskIsActive || hasNoTargetOptions || mustChooseTarget}
              style={{
                ...primaryBtnStyle,
                opacity: loading || rerunning || taskIsActive || hasNoTargetOptions || mustChooseTarget ? 0.55 : 1,
                cursor: loading || rerunning || taskIsActive || hasNoTargetOptions || mustChooseTarget ? 'not-allowed' : 'pointer',
              }}
            >
              {rerunning || taskIsActive ? '运行中...' : '启用求解'}
            </button>
            <button
              onClick={onCancelRun}
              disabled={stopDisabled}
              style={{
                ...dangerBtnStyle,
                opacity: stopDisabled ? 0.55 : 1,
                cursor: stopDisabled ? 'not-allowed' : 'pointer',
              }}
            >
              {cancelling || taskStatus === 'cancelling' || taskStatus === 'canceling' ? '终止中...' : '终止运行'}
            </button>
          </div>
        </section>

        <section style={{ ...sectionStyle, marginTop: 16 }}>
          <h2 style={sectionTitleStyle}>运行进度</h2>
          <div style={progressHeaderStyle}>
            <strong>{displayProgress.label}</strong>
            <span>{displayProgress.percent.toFixed(0)}%</span>
          </div>
          <div style={progressTrackStyle}>
            <div style={{ ...progressFillStyle, width: `${displayProgress.percent}%` }} />
          </div>
          <div style={progressDetailStyle}>
            <span>{displayProgress.detail}</span>
            <span>{lastUpdatedAt ? `自动更新：${lastUpdatedAt.toLocaleTimeString('zh-CN')}` : '等待自动更新'}</span>
          </div>
        </section>

        <section style={{ ...sectionStyle, marginTop: 16 }}>
          <h2 style={sectionTitleStyle}>最近任务</h2>
          {!latestTask ? (
            <div>暂无任务。</div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
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

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 16 }}>
          <section style={sectionStyle}>
            <h2 style={sectionTitleStyle}>stdout 日志</h2>
            {!activeTaskId ? <div>暂无日志。</div> : <pre style={preStyle}>{stdoutText || 'stdout 为空。'}</pre>}
          </section>

          <section style={sectionStyle}>
            <h2 style={sectionTitleStyle}>stderr 日志</h2>
            <pre style={preStyle}>{stderrText || 'stderr 为空。'}</pre>
          </section>
        </div>
      </div>
    </div>
  );
}

function safeInternalId(value: string): string {
  const out = value
    .trim()
    .split('')
    .map((ch) => (/[\p{L}\p{N}_-]/u.test(ch) ? ch : '_'))
    .join('');
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
  if (status === 'failed') {
    return {
      percent: Math.max(parsed.percent, 1),
      label: '求解失败',
      detail: parsed.detail || '请查看 stderr 日志定位失败原因。',
    };
  }
  if (status === 'cancelled' || status === 'canceled') {
    return {
      percent: Math.max(parsed.percent, 1),
      label: '运行已终止',
      detail: '用户已终止求解进程。',
    };
  }
  if (status === 'cancelling' || status === 'canceling') {
    return {
      percent: Math.max(parsed.percent, 1),
      label: '正在终止',
      detail: '已发送终止请求，等待求解器进程退出。',
    };
  }
  if (status === 'running') return parsed.percent > 0 ? parsed : { percent: 3, label: '求解器已启动', detail: '正在等待求解器输出进度日志。' };
  return parsed.percent > 0 ? parsed : { percent: 0, label: task.status || '等待运行', detail: task.message || '暂无可解析进度。' };
}

function parseStdoutProgress(stdoutText: string, requestedGenerations: number): ProgressInfo {
  // 求解器实际执行阶段与进度权重分配：
  //   阶段 1 — 初始化（加载数据、构建 OpenDSS oracle）:  0% ~  5%
  //   阶段 2 — GA 迭代（fast_proxy 代表日评估）:          5% ~ 30%
  //   阶段 3 — GA 最终种群评估（额外一轮 evaluate）:     30% ~ 35%
  //   阶段 4 — full_recheck（365 天全年 OpenDSS 潮流）:  35% ~ 90%
  //   阶段 5 — 结果导出（写 CSV/JSON/图表）:             90% ~100%

  if (!stdoutText.trim()) return { percent: 0, label: '等待日志', detail: 'stdout 暂无进度输出。' };
  if (stdoutText.includes('已导出总体最优方案汇总')) {
    return { percent: 100, label: '结果汇总已导出', detail: '求解流程已完成。' };
  }

  const totalCases = lastNumber(stdoutText, /共加载\s+(\d+)\s+个待优化场景/g);
  const caseMatch = lastMatch(stdoutText, /开始场景优化\s+\[(\d+)\/(\d+)\]/g);
  const completedCases = countMatches(stdoutText, /场景完成：/g);
  const generationsFromLog = lastNumber(stdoutText, /优化参数：总代数=(\d+)/g);
  const generations = Math.max(generationsFromLog || requestedGenerations || 0, 1);
  const iteration = Math.min(lastNumber(stdoutText, /优化迭代\s+(\d+)/g) || 0, generations);

  // full_recheck 阶段：匹配 "[年度运行] 进度 N/365"
  const annualMatch = lastMatch(stdoutText, /年度运行[^\n]*进度\s+(\d+)\/365/g);
  const annualDay = annualMatch ? Math.min(Number(annualMatch[1]) || 0, 365) : 0;

  // fast_proxy 阶段：匹配 "[年度运行] 代表日 N/M"
  const proxyMatch = lastMatch(stdoutText, /年度运行[^\n]*代表日\s+(\d+)\/(\d+)/g);
  const proxyCurrent = proxyMatch ? (Number(proxyMatch[1]) || 0) : 0;
  const proxyTotal = proxyMatch ? (Number(proxyMatch[2]) || 0) : 0;

  // 检测是否已进入 full_recheck 阶段
  const inFullRecheck = stdoutText.includes('full_recheck') && annualDay > 0;
  // 检测是否已进入最终重校核
  const inFinalRecheck = /对最终折中解执行全年重校核|调用 OpenDSS oracle 对最终折中解/.test(stdoutText);
  // 检测结果导出阶段
  const inExport = stdoutText.includes('场景完成：') && completedCases > 0;

  const total = caseMatch ? Number(caseMatch[2]) : totalCases;
  const current = caseMatch ? Number(caseMatch[1]) : Math.min(completedCases + 1, total || 1);

  // --- 阶段 5：结果导出 (90-100%) ---
  if (inExport && total && completedCases >= total) {
    return {
      percent: 95,
      label: '正在导出结果',
      detail: `全部 ${total} 个场景已完成，正在写入结果文件。`,
    };
  }

  // --- 阶段 4：full_recheck (35-90%) ---
  if (inFinalRecheck && annualDay > 0) {
    const recheckFraction = annualDay / 365;
    return {
      percent: clampProgress(35 + recheckFraction * 55),
      label: '全年重校核（最耗时阶段）',
      detail: `OpenDSS 全年逐日潮流重校核 ${annualDay}/365 天。`,
    };
  }

  if (inFullRecheck && annualDay > 0 && iteration >= generations) {
    const recheckFraction = annualDay / 365;
    return {
      percent: clampProgress(35 + recheckFraction * 55),
      label: '全年重校核（最耗时阶段）',
      detail: `全年逐日重校核 ${annualDay}/365 天。`,
    };
  }

  // --- 阶段 3：GA 最终种群评估 (30-35%) ---
  if (iteration >= generations && !inFullRecheck && !inFinalRecheck) {
    let detail = `GA 迭代已完成 ${generations} 代，正在评估最终种群。`;
    let percent = 32;
    if (proxyCurrent > 0 && proxyTotal > 0) {
      const proxyFraction = proxyCurrent / proxyTotal;
      percent = clampProgress(30 + proxyFraction * 5);
      detail = `最终种群评估，代表日 ${proxyCurrent}/${proxyTotal}。`;
    }
    return { percent, label: '评估最终种群', detail };
  }

  // --- 阶段 2：GA 迭代 (5-30%) ---
  if (total && current) {
    const iterationFraction = iteration > 0 ? iteration / generations : 0;
    const proxyFraction = (proxyCurrent > 0 && proxyTotal > 0) ? proxyCurrent / proxyTotal : 0;
    const inIterationFraction = iteration < generations
      ? iterationFraction + proxyFraction / generations
      : iterationFraction;
    const inCaseFraction = Math.min(inIterationFraction, 1.0);
    const completedFraction = completedCases / total;
    const runningFraction = (Math.max(current - 1, 0) + inCaseFraction) / total;
    const overallFraction = Math.max(completedFraction, runningFraction);
    const percent = clampProgress(5 + overallFraction * 25);
    let detail: string;
    if (proxyCurrent > 0 && proxyTotal > 0 && iteration > 0) {
      detail = `第 ${current}/${total} 个场景，迭代 ${iteration}/${generations}，代表日 ${proxyCurrent}/${proxyTotal}。`;
    } else if (iteration > 0) {
      detail = `第 ${current}/${total} 个场景，优化迭代 ${iteration}/${generations}。`;
    } else {
      detail = `第 ${current}/${total} 个场景正在初始化。`;
    }
    return { percent, label: '正在运行 GA 优化', detail };
  }

  if (iteration > 0) {
    const iterationFraction = iteration / generations;
    return {
      percent: clampProgress(5 + iterationFraction * 25),
      label: '正在运行 GA 优化',
      detail: `优化迭代 ${iteration}/${generations}。`,
    };
  }

  // --- 阶段 1：初始化 (0-5%) ---
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
  return {
    percent: Math.max(0, Math.min(percent, 100)),
    label,
    detail: detail || '后台已返回运行进度。',
  };
}

function Mini(props: { label: string; value: string }) {
  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, padding: 14 }}>
      <div style={{ color: '#6b7280', fontSize: 13, marginBottom: 8 }}>{props.label}</div>
      <div style={{ fontWeight: 700 }}>{props.value}</div>
    </div>
  );
}

const sectionStyle: React.CSSProperties = { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 16, padding: 20 };
const sectionTitleStyle: React.CSSProperties = { margin: '0 0 14px 0', fontSize: 24 };
const fieldStyle: React.CSSProperties = { display: 'grid', gap: 6 };
const labelStyle: React.CSSProperties = { color: '#4b5563', fontSize: 13, fontWeight: 700 };
const inputStyle: React.CSSProperties = { height: 40, border: '1px solid #d1d5db', borderRadius: 10, padding: '0 10px', fontSize: 14 };
const primaryBtnStyle: React.CSSProperties = { padding: '10px 14px', borderRadius: 12, border: '1px solid #111827', background: '#111827', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const dangerBtnStyle: React.CSSProperties = { padding: '10px 14px', borderRadius: 12, border: '1px solid #dc2626', background: '#dc2626', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const errorStyle: React.CSSProperties = { background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c', borderRadius: 12, padding: 14, marginBottom: 16 };
const hintStyle: React.CSSProperties = { marginTop: 10, color: '#4b5563', fontSize: 13 };
const hintWarnStyle: React.CSSProperties = { marginTop: 10, color: '#b45309', fontSize: 13, fontWeight: 600 };
const targetDetailStyle: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10, marginTop: 12 };
const progressHeaderStyle: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', color: '#111827' };
const progressTrackStyle: React.CSSProperties = { height: 12, overflow: 'hidden', borderRadius: 999, background: '#e5e7eb', marginTop: 12 };
const progressFillStyle: React.CSSProperties = { height: '100%', borderRadius: 999, background: '#2563eb', transition: 'width 300ms ease' };
const progressDetailStyle: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginTop: 10, color: '#6b7280', fontSize: 13 };
const preStyle: React.CSSProperties = { whiteSpace: 'pre-wrap', wordBreak: 'break-word', background: '#f8fafc', padding: 12, border: '1px solid #e5e7eb', borderRadius: 12, maxHeight: 560, overflow: 'auto', minHeight: 420 };
