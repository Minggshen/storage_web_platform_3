import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import {
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts';
import {
  fetchResultCharts,
  fetchResultFilePreview,
  fetchLatestSolverTask,
  fetchResultFiles,
  fetchSolverTasks,
  fetchSolverSummary,
  getResultFileDownloadUrl,
} from '../../services/solver';
import type {
  EngineDiagnosticsPayload,
  EngineDiagnosticsScenario,
  ResultChartPoint,
  ResultChartsResponse,
  ResultFileItem,
  ResultFilePreviewResponse,
  SolverSummaryResponse,
  SolverTask,
} from '../../types/api';

type GenericRow = Record<string, unknown>;
type NetworkTopologyChart = {
  nodes?: ResultChartPoint[];
  edges?: ResultChartPoint[];
  summary?: ResultChartPoint[];
  warnings?: string[];
  selectedNodeId?: string | null;
  dataQuality?: string;
};
type TopologyLabelPlacement = {
  tx: number;
  ty: number;
  x: number;
  y: number;
  width: number;
  height: number;
};

const COLORS = {
  base: '#1f4e79',
  accent1: '#d08a33',
  accent2: '#4f8f5b',
  accent3: '#8e63a9',
  accent4: '#c67a7a',
  gray: '#6b7280',
  grid: '#e5e7eb',
};

const PIE_COLORS = [COLORS.base, COLORS.accent1, COLORS.accent4, COLORS.accent2, COLORS.gray, COLORS.accent3];

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function metricText(value: unknown, suffix = ''): string {
  const number = toFiniteNumber(value);
  if (number !== null) return `${number.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}${suffix}`;
  if (value === null || value === undefined || value === '') return '--';
  return `${String(value)}${suffix}`;
}

function formatTaskTime(value: unknown): string {
  if (value === null || value === undefined || value === '') return '未完成';
  if (typeof value === 'number' && Number.isFinite(value)) {
    const timestamp = value > 1_000_000_000_000 ? value : value * 1000;
    return new Date(timestamp).toLocaleString('zh-CN');
  }
  const parsed = new Date(String(value));
  if (!Number.isNaN(parsed.getTime())) return parsed.toLocaleString('zh-CN');
  return String(value);
}

function taskOptionLabel(task: SolverTask): string {
  const taskId = task.task_id || '--';
  const time = formatTaskTime(task.completed_at ?? task.started_at);
  const health = task.health_status ? ` ｜ ${healthStatusText(task.health_status)}` : '';
  const issueCount = toFiniteNumber(task.health_issue_count);
  const issueText = issueCount !== null && issueCount > 0 ? ` ${issueCount}项` : '';
  return `${taskId} ｜ ${time}${health}${issueText}`;
}

function puText(value: unknown): string {
  const number = toFiniteNumber(value);
  if (number === null || Math.abs(number) > 2) return '--';
  return number.toLocaleString('zh-CN', {
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
    useGrouping: false,
  });
}

function puRangeText(minValue: unknown, maxValue: unknown): string {
  const minText = puText(minValue);
  const maxText = puText(maxValue);
  if (minText === '--' && maxText === '--') return '';
  if (minText === maxText || maxText === '--') return minText;
  if (minText === '--') return maxText;
  return `${minText}-${maxText}`;
}

function signedMetricText(value: unknown, suffix = ''): string {
  const number = toFiniteNumber(value);
  if (number === null) return '--';
  return `${number > 0 ? '+' : ''}${metricText(number, suffix)}`;
}

function metricTextWithUnit(value: unknown, unit: unknown): string {
  const textUnit = unit ? String(unit) : '';
  if (textUnit === 'pu') return `${puText(value)} pu`;
  return metricText(value, textUnit ? ` ${textUnit}` : '');
}

function ampText(value: unknown): string {
  const number = toFiniteNumber(value);
  if (number === null || number <= 0) return '--';
  if (number >= 1000) return `${(number / 1000).toLocaleString('zh-CN', { maximumFractionDigits: number >= 10000 ? 1 : 2, minimumFractionDigits: 0 })} kA`;
  return `${Math.round(number).toLocaleString('zh-CN')} A`;
}

function kvaText(value: unknown): string {
  const number = toFiniteNumber(value);
  if (number === null || number <= 0) return '--';
  return `${Math.round(number).toLocaleString('zh-CN')} kVA`;
}

function ohmPerKmText(r1: unknown, x1: unknown): string {
  const r = toFiniteNumber(r1);
  const x = toFiniteNumber(x1);
  if (r === null && x === null) return '--';
  return `R1 ${r === null ? '--' : r.toFixed(5)} / X1 ${x === null ? '--' : x.toFixed(5)} Ω/km`;
}

function classifyRelativeServiceLineSize(rows: ResultChartPoint[], current: unknown): 'large' | 'small' | 'normal' {
  const value = toFiniteNumber(current);
  if (value === null) return 'normal';
  const samples = rows
    .map((row) => toFiniteNumber(row.normamps))
    .filter((item): item is number => item !== null)
    .sort((a, b) => a - b);
  if (!samples.length) return 'normal';
  const lowerIndex = Math.floor((samples.length - 1) * 0.2);
  const upperIndex = Math.ceil((samples.length - 1) * 0.8);
  const lower = samples[Math.max(0, lowerIndex)];
  const upper = samples[Math.min(samples.length - 1, upperIndex)];
  if (value <= lower) return 'small';
  if (value >= upper) return 'large';
  return 'normal';
}

function relativeServiceLineLabel(level: 'large' | 'small' | 'normal'): string {
  if (level === 'large') return '项目内偏大';
  if (level === 'small') return '项目内偏小';
  return '项目内常规';
}

function toRecord(value: unknown): GenericRow | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) return value as GenericRow;
  return null;
}

function pickString(record: GenericRow | null, ...keys: string[]): string | null {
  if (!record) return null;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim() !== '') return value;
    if (typeof value === 'number') return String(value);
  }
  return null;
}

function pickNumber(record: GenericRow | null, ...keys: string[]): number | null {
  if (!record) return null;
  for (const key of keys) {
    const value = toFiniteNumber(record[key]);
    if (value !== null) return value;
  }
  return null;
}

function normalizeNpvWan(record: GenericRow | null): number | null {
  const npvWan = pickNumber(record, 'npv_wan');
  if (npvWan !== null) return npvWan;
  const npvYuan = pickNumber(record, 'npv_yuan');
  return npvYuan !== null ? npvYuan / 10000 : null;
}

function normalizeIrrPercent(record: GenericRow | null): number | null {
  const irrPercent = pickNumber(record, 'irr_percent');
  if (irrPercent !== null) return irrPercent;
  const irr = pickNumber(record, 'irr');
  return irr !== null ? irr * 100 : null;
}

function normalizeCycles(record: GenericRow | null): number | null {
  return pickNumber(record, 'annual_equivalent_cycles', 'annual_equivalent_full_cycles');
}

function chartRows(rows: ResultChartPoint[] | undefined): ResultChartPoint[] {
  return rows ?? [];
}

function topologyBoxesOverlap(a: TopologyLabelPlacement, b: TopologyLabelPlacement, padding = 8): boolean {
  return !(
    a.x + a.width + padding < b.x ||
    b.x + b.width + padding < a.x ||
    a.y + a.height + padding < b.y ||
    b.y + b.height + padding < a.y
  );
}

function reserveTopologyPlacement(
  occupied: TopologyLabelPlacement[],
  candidates: TopologyLabelPlacement[],
): TopologyLabelPlacement {
  const selected = candidates.find((candidate) => occupied.every((box) => !topologyBoxesOverlap(candidate, box))) ?? candidates[0];
  occupied.push(selected);
  return selected;
}

function recordRows(rows: unknown): GenericRow[] {
  if (!Array.isArray(rows)) return [];
  return rows.map((row) => toRecord(row)).filter((row): row is GenericRow => row !== null);
}

function nonZeroRows(rows: ResultChartPoint[]): ResultChartPoint[] {
  const filtered = rows.filter((row) => Math.abs(toFiniteNumber(row.valueWan) ?? 0) > 1e-9);
  return filtered.length ? filtered : rows;
}

function isImageFile(file: ResultFileItem | null): boolean {
  const suffix = String(file?.suffix || file?.name?.split('.').pop() || '').toLowerCase();
  return ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', 'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(suffix);
}

function numberTooltipFormatter(value: unknown, name: unknown): [string, string] {
  return [metricText(value), String(name)];
}

function yuanToWanText(value: unknown): string {
  const amountYuan = toFiniteNumber(value);
  return amountYuan === null ? metricText(value) : metricText(amountYuan / 10000, ' 万元');
}

function feasibilityStatusText(summary: GenericRow): string {
  const status = String(summary.status ?? 'unknown');
  if (status === 'feasible') return '严格可行';
  if (status === 'infeasible') return '不可行，仅为最佳折中方案';
  return '状态未知';
}

function htmlEscape(value: unknown): string {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function reportValue(value: unknown, suffix = ''): string {
  return htmlEscape(metricText(value, suffix));
}

function reportTable(title: string, rows: Array<Record<string, unknown>>, maxRows = 24): string {
  if (!rows.length) return `<section><h2>${htmlEscape(title)}</h2><p class="muted">暂无数据</p></section>`;
  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row)))).slice(0, 12);
  const body = rows.slice(0, maxRows).map((row) => (
    `<tr>${columns.map((column) => `<td>${htmlEscape(row[column])}</td>`).join('')}</tr>`
  )).join('');
  return `
    <section>
      <h2>${htmlEscape(title)}</h2>
      <table>
        <thead><tr>${columns.map((column) => `<th>${htmlEscape(column)}</th>`).join('')}</tr></thead>
        <tbody>${body}</tbody>
      </table>
      ${rows.length > maxRows ? `<p class="muted">仅展示前 ${maxRows} 行，共 ${rows.length} 行。</p>` : ''}
    </section>
  `;
}

function reportBars(title: string, rows: ResultChartPoint[], labelKey: string, valueKey: string, unit = ''): string {
  if (!rows.length) return `<section><h2>${htmlEscape(title)}</h2><p class="muted">暂无数据</p></section>`;
  const maxAbs = Math.max(...rows.map((row) => Math.abs(toFiniteNumber(row[valueKey]) ?? 0)), 1);
  const items = rows.map((row) => {
    const value = toFiniteNumber(row[valueKey]) ?? 0;
    const width = Math.max(2, Math.abs(value) / maxAbs * 100);
    const color = value >= 0 ? COLORS.base : COLORS.accent4;
    return `
      <div class="bar-row">
        <div class="bar-label">${htmlEscape(row[labelKey])}</div>
        <div class="bar-track"><div class="bar" style="width:${width.toFixed(2)}%;background:${color};"></div></div>
        <div class="bar-value">${reportValue(value, unit)}</div>
      </div>
    `;
  }).join('');
  return `<section><h2>${htmlEscape(title)}</h2>${items}</section>`;
}

function buildReportHtml(input: {
  projectId: string;
  selectedCase: string | null;
  latestTask: ResultChartsResponse['latest_task'] | null;
  warnings: string[];
  primary: GenericRow | null;
  feasibilitySummary: GenericRow;
  feasibilityViolations: ResultChartPoint[];
  monthlyRevenue: ResultChartPoint[];
  financialMetrics: ResultChartPoint[];
  cashflow: ResultChartPoint[];
  pareto: ResultChartPoint[];
  history: ResultChartPoint[];
  storageImpact: ResultChartPoint[];
  networkConstraintDaily: ResultChartPoint[];
  lineCapacity: ResultChartPoint[];
  networkTopology: NetworkTopologyChart | null;
  deliverables: GenericRow;
  summaryRows: Record<string, unknown>[];
}): string {
  const generatedAt = new Date().toLocaleString('zh-CN');
  const configuration = toRecord(input.deliverables.configuration);
  const backgroundPolicy = String(configuration?.background_load_policy ?? '').trim();
  const keyMetrics = [
    ['推荐策略', pickString(input.primary, 'strategy_name', 'strategy_id')],
    ['配储目标', metricText(configuration?.target_id ?? input.selectedCase)],
    ['接入母线', metricText(configuration?.target_bus)],
    ['推荐功率', metricText(pickNumber(input.primary, 'power_kw', 'rated_power_kw'), ' kW')],
    ['推荐容量', metricText(pickNumber(input.primary, 'energy_kwh', 'rated_energy_kwh'), ' kWh')],
    ['NPV', metricText(normalizeNpvWan(input.primary), ' 万元')],
    ['回收期', metricText(pickNumber(input.primary, 'payback_years', 'simple_payback_years'), ' 年')],
    ['IRR', metricText(normalizeIrrPercent(input.primary), '%')],
    ['年等效循环', metricText(normalizeCycles(input.primary), ' 次')],
  ];
  const keyMetricHtml = keyMetrics.map(([label, value]) => (
    `<div class="metric"><span>${htmlEscape(label)}</span><strong>${htmlEscape(value)}</strong></div>`
  )).join('');
  const warnings = input.warnings.length
    ? `<section class="warning"><h2>结果提示</h2>${input.warnings.map((warning) => `<p>${htmlEscape(warning)}</p>`).join('')}</section>`
    : '';
  const targetPolicySection = backgroundPolicy
    ? `<section><h2>单目标配储流程</h2><p>${htmlEscape(backgroundPolicy)}</p></section>`
    : '';
  const topologySummary = input.networkTopology?.summary ?? [];

  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>储能优化结果分析报告</title>
  <style>
    body{font-family:Inter,Arial,"Microsoft YaHei",sans-serif;margin:0;background:#f8fafc;color:#111827;}
    main{max-width:1180px;margin:0 auto;padding:28px;}
    section{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:18px;margin:16px 0;}
    h1{margin:0 0 8px;font-size:28px;} h2{margin:0 0 14px;font-size:20px;}
    .muted{color:#6b7280;} .metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;}
    .metric{border:1px solid #e5e7eb;border-radius:8px;padding:12px;background:#fff;}
    .metric span{display:block;color:#6b7280;font-size:13px;margin-bottom:6px;} .metric strong{font-size:16px;}
    .warning{border-color:#fde68a;background:#fffbeb;color:#92400e;}
    table{border-collapse:collapse;width:100%;font-size:13px;} th,td{border-bottom:1px solid #e5e7eb;text-align:left;padding:8px;vertical-align:top;}
    th{background:#f9fafb;} .bar-row{display:grid;grid-template-columns:130px 1fr 120px;gap:10px;align-items:center;margin:9px 0;}
    .bar-track{height:12px;background:#eef2f7;border-radius:6px;overflow:hidden;} .bar{height:12px;border-radius:6px;}
    .bar-value{text-align:right;font-variant-numeric:tabular-nums;}
  </style>
</head>
<body>
  <main>
    <h1>储能优化结果分析报告</h1>
    <p class="muted">项目：${htmlEscape(input.projectId)}；节点：${htmlEscape(input.selectedCase)}；任务：${htmlEscape(input.latestTask?.task_id)}；导出时间：${htmlEscape(generatedAt)}</p>
    ${warnings}
    <section><h2>推荐方案摘要</h2><div class="metrics">${keyMetricHtml}</div></section>
    ${targetPolicySection}
    <section>
      <h2>可行性诊断</h2>
      <div class="metrics">
        <div class="metric"><span>推荐方案状态</span><strong>${htmlEscape(feasibilityStatusText(input.feasibilitySummary))}</strong></div>
        <div class="metric"><span>可行解数量</span><strong>${reportValue(input.feasibilitySummary.feasibleCount)} / ${reportValue(input.feasibilitySummary.populationSize)}</strong></div>
        <div class="metric"><span>总违反量</span><strong>${reportValue(input.feasibilitySummary.bestTotalViolation)}</strong></div>
        <div class="metric"><span>循环次数超限</span><strong>${reportValue(input.feasibilitySummary.bestCycleViolation, ' 次')}</strong></div>
      </div>
      <p class="muted">${htmlEscape(input.feasibilitySummary.message)}</p>
    </section>
    ${reportBars('约束违反项', input.feasibilityViolations, 'name', 'value')}
    ${reportBars('月度净现金流', input.monthlyRevenue, 'month', 'netCashflowWan', ' 万元')}
    ${reportBars('全寿命期累计折现现金流', input.cashflow, 'year', 'cumulativeDiscountedWan', ' 万元')}
    ${reportTable('配电网承载能力摘要', topologySummary)}
    ${reportTable('代表日储能接入影响', input.storageImpact)}
    ${reportTable('网侧约束日趋势', input.networkConstraintDaily)}
    ${reportTable('线路容量配置', input.lineCapacity)}
    ${reportTable('关键财务与运行指标', input.financialMetrics)}
    ${reportTable('候选方案明细', input.pareto)}
    ${reportTable('优化收敛记录', input.history)}
    ${reportTable('summary_rows', input.summaryRows)}
  </main>
</body>
</html>`;
}

export default function ResultsPage() {
  const { projectId = '' } = useParams();
  const [summary, setSummary] = useState<SolverSummaryResponse | null>(null);
  const [charts, setCharts] = useState<ResultChartsResponse | null>(null);
  const [files, setFiles] = useState<ResultFileItem[]>([]);
  const [selectedFile, setSelectedFile] = useState<ResultFileItem | null>(null);
  const [preview, setPreview] = useState<ResultFilePreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [serviceLineFilter, setServiceLineFilter] = useState<'all' | 'large' | 'small'>('all');
  const [tasks, setTasks] = useState<SolverTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState('');
  const [manualTaskSelection, setManualTaskSelection] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const [solverRunning, setSolverRunning] = useState(false);

  const primary = useMemo<GenericRow | null>(() => {
    if (!summary) return null;
    const fromSummaryRows = summary.summary_rows && summary.summary_rows.length > 0 ? toRecord(summary.summary_rows[0]) : null;
    if (fromSummaryRows) return fromSummaryRows;
    const fromOverallBest = summary.overall_best_schemes && summary.overall_best_schemes.length > 0 ? toRecord(summary.overall_best_schemes[0]) : null;
    return fromOverallBest;
  }, [summary]);

  async function loadTaskOptions(silent = false) {
    if (!projectId) return;
    try {
      const nextTasks = await fetchSolverTasks(projectId);
      setTasks(nextTasks);
      setSelectedTaskId((previous) => {
        if (manualTaskSelection && previous && nextTasks.some((task) => task.task_id === previous)) return previous;
        return '';
      });
    } catch (err) {
      if (!silent) setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function loadSummaryAndFiles(silent = false) {
    if (!projectId) return;
    if (!silent) setLoading(true);
    setError(null);
    try {
      const taskId = selectedTaskId || undefined;
      const [summaryData, fileData, chartData] = await Promise.all([
        fetchSolverSummary(projectId, taskId),
        fetchResultFiles(projectId, taskId),
        fetchResultCharts(projectId, taskId),
      ]);
      const nextFiles = fileData.files || [];
      setSummary(summaryData);
      setFiles(nextFiles);
      setCharts(chartData);
      setLastUpdatedAt(new Date().toLocaleTimeString('zh-CN', { hour12: false }));
      if (
        selectedFile &&
        !nextFiles.some((file) => file.group === selectedFile.group && file.relative_path === selectedFile.relative_path)
      ) {
        setSelectedFile(null);
        setPreview(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (!silent) setLoading(false);
    }
  }

  async function handlePreview(file: ResultFileItem) {
    if (!projectId) return;
    setSelectedFile(file);
    if (isImageFile(file)) {
      setPreviewLoading(false);
      setPreview({
        success: true,
        project_id: projectId,
        group: file.group,
        relative_path: file.relative_path,
        file_name: file.name,
        type: 'image',
        content: getResultFileDownloadUrl(projectId, file.relative_path, file.group, selectedTaskId || undefined),
      });
      return;
    }
    setPreviewLoading(true);
    try {
      const data = await fetchResultFilePreview(projectId, file.relative_path, file.group, selectedTaskId || undefined);
      setPreview(data);
    } catch (err) {
      setPreview({
        success: false,
        project_id: projectId,
        group: file.group,
        relative_path: file.relative_path,
        file_name: file.name,
        type: 'text',
        content: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setPreviewLoading(false);
    }
  }

  useEffect(() => {
    setTasks([]);
    setSelectedTaskId('');
    setManualTaskSelection(false);
    setSelectedFile(null);
    setPreview(null);
    setLastUpdatedAt(null);
    loadTaskOptions();
  }, [projectId]);

  useEffect(() => {
    loadSummaryAndFiles();
    const intervalId = window.setInterval(() => {
      loadTaskOptions(true);
      loadSummaryAndFiles(true);
      // Check if a solver task is currently running.
      if (projectId) {
        fetchLatestSolverTask(projectId).then((task) => {
          if (task) {
            const s = String(task.status ?? '').toLowerCase();
            setSolverRunning(s === 'running' || s === 'queued');
          }
        }).catch(() => {});
      }
    }, 8000);
    return () => window.clearInterval(intervalId);
  }, [projectId, selectedTaskId, manualTaskSelection]);

  const summaryRows = summary?.summary_rows ?? [];
  const summaryKeys = summaryRows.length > 0 ? Object.keys(summaryRows[0] as GenericRow) : [];
  const chartData = charts?.charts ?? {};
  const diagnostics = toRecord(charts?.diagnostics);
  const networkTopologyCacheDiagnostics = toRecord(diagnostics?.network_topology_cache);
  const deliverables = toRecord(chartData.deliverables) ?? {};
  const financialDeliverable = toRecord(deliverables.financial);
  const auditLedger = toRecord(financialDeliverable?.annual_audit_ledger);
  const auditLedgerItems = recordRows(auditLedger?.items);
  const networkImpactDeliverable = toRecord(deliverables.network_impact);
  const networkRiskDetails = toRecord(networkImpactDeliverable?.risk_details);
  const voltageRiskRows = recordRows(networkRiskDetails?.voltage_top_risks);
  const lineRiskRows = recordRows(networkRiskDetails?.line_top_risks);
  const transformerRisk = toRecord(networkRiskDetails?.transformer);
  const transformerTopRiskRows = recordRows(networkImpactDeliverable?.transformer_top_risks ?? networkRiskDetails?.transformer_top_risks);
  const transformerRiskRows = transformerTopRiskRows.length ? transformerTopRiskRows : transformerRisk ? [transformerRisk] : [];
  const feasibility = chartData.feasibility_diagnostics;
  const feasibilitySummary = (feasibility?.summary ?? {}) as GenericRow;
  const feasibilityViolations = chartRows(feasibility?.violations);
  const candidateStatus = chartRows(feasibility?.candidate_status);
  const candidateViolations = chartRows(feasibility?.candidate_violations);
  const monthlyRevenue = chartRows(chartData.monthly_revenue);
  const representativeDay = chartData.representative_day;
  const representativeRows = chartRows(representativeDay?.rows);
  const dailyOperation = chartRows(chartData.daily_operation);
  const yearlySoc = chartRows(chartData.yearly_soc);
  const cashflow = chartRows(chartData.cashflow);
  const capitalBreakdown = nonZeroRows(chartRows(chartData.capital_breakdown));
  const annualValueBreakdown = chartRows(chartData.annual_value_breakdown);
  const financialMetrics = chartRows(chartData.financial_metrics);
  const pareto = chartRows(chartData.pareto);
  const history = chartRows(chartData.optimization_history);
  const storageImpact = chartRows(chartData.storage_impact);
  const networkConstraints = chartData.network_constraints;
  const networkConstraintDaily = chartRows(networkConstraints?.daily);
  const lineCapacity = chartRows(chartData.line_capacity);
  const networkTopology = chartData.network_topology;
  const topologyEdges = chartRows(networkTopology?.edges);
  const autoServiceLineRows = lineCapacity.filter((row) => row.autoServiceLine === true);
  const serviceLineRuntimeById = useMemo(
    () =>
      new Map(
        topologyEdges
          .map((row) => [String(row.id ?? ''), row] as const)
          .filter(([id]) => id),
      ),
    [topologyEdges],
  );
  const filteredAutoServiceLineRows = autoServiceLineRows.filter((row) => {
    const level = classifyRelativeServiceLineSize(autoServiceLineRows, row.normamps);
    if (serviceLineFilter === 'large') return level === 'large';
    if (serviceLineFilter === 'small') return level === 'small';
    return true;
  });
  const plotFiles = useMemo(
    () => files.filter((file) => isImageFile(file) && file.relative_path.toLowerCase().includes('figures')),
    [files],
  );

  function handleExportReport() {
    const html = buildReportHtml({
      projectId,
      selectedCase: charts?.selected_case ?? null,
      latestTask: charts?.latest_task ?? null,
      warnings: charts?.warnings ?? [],
      primary,
      feasibilitySummary,
      feasibilityViolations,
      monthlyRevenue,
      financialMetrics,
      cashflow,
      pareto,
      history,
      storageImpact,
      networkConstraintDaily,
      lineCapacity,
      networkTopology: networkTopology ?? null,
      deliverables,
      summaryRows,
    });
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `storage-result-report-${projectId || 'project'}-${new Date().toISOString().slice(0, 10)}.html`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div style={{ padding: 24, background: '#f8fafc', minHeight: '100vh' }}>
      <div style={{ maxWidth: 1360, margin: '0 auto' }} aria-live="polite">
        {/* Top bar */}
        <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800 }}>结果展示</h1>
          <select
            id="result-task-select"
            value={selectedTaskId}
            onChange={(event) => {
              setManualTaskSelection(event.target.value !== '');
              setSelectedTaskId(event.target.value);
              setSelectedFile(null);
              setPreview(null);
            }}
            style={taskSelectStyle}
          >
            <option value="">最新完成任务（自动）</option>
            {tasks.map((task) => (
              <option key={task.task_id} value={task.task_id}>
                {taskOptionLabel(task)}
              </option>
            ))}
          </select>
          {loading ? <span style={{ color: '#64748b', fontSize: 12 }}>加载中...</span> : null}
          <span style={{ color: '#6b7280', fontSize: 11, marginLeft: 'auto' }}>
            {lastUpdatedAt ? `自动刷新：${lastUpdatedAt}` : ''}
          </span>
          <button onClick={handleExportReport} disabled={!summary && !charts} style={btnStyle}>
            导出分析报告
          </button>
        </div>

        {solverRunning && (
          <div style={{
            marginBottom: 16,
            padding: '10px 16px',
            borderRadius: 10,
            border: '1px solid rgba(245, 158, 11, 0.5)',
            background: 'rgba(245, 158, 11, 0.1)',
            color: '#92400e',
            fontWeight: 600,
            fontSize: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}>
            <span style={{
              display: 'inline-block',
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: '#f59e0b',
              animation: 'pulse 2s infinite',
            }} />
            求解任务正在运行中，当前展示的是历史结果。新结果将在任务完成后自动更新。
          </div>
        )}

        {error && <ErrorBanner message={error} />}
        {charts?.warnings?.length ? <WarningPanel warnings={charts.warnings} /> : null}
        {networkTopologyCacheDiagnostics ? (
          <DiagnosticsStrip diagnostics={networkTopologyCacheDiagnostics} />
        ) : null}

        {/* Step 1: Summary */}
        <section style={sectionStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24, borderRadius: '50%', background: '#2563eb', color: '#fff', fontSize: 11, fontWeight: 800, flexShrink: 0 }}>1</span>
            <span style={{ fontWeight: 700, fontSize: 16 }}>方案摘要</span>
          </div>
          {!primary ? (
            <div>暂无推荐方案。</div>
          ) : (
            <div style={metricGridStyle}>
              <Metric label="推荐策略" value={metricText(pickString(primary, 'strategy_name', 'strategy_id'))} />
              <Metric label="推荐功率" value={metricText(pickNumber(primary, 'power_kw', 'rated_power_kw'), ' kW')} />
              <Metric label="推荐容量" value={metricText(pickNumber(primary, 'energy_kwh', 'rated_energy_kwh'), ' kWh')} />
              <Metric label="推荐时长" value={metricText(pickNumber(primary, 'duration_h'), ' h')} />
              <Metric label="NPV" value={metricText(normalizeNpvWan(primary), ' 万元')} />
              <Metric label="回收期" value={metricText(pickNumber(primary, 'payback_years', 'simple_payback_years'), ' 年')} />
              <Metric label="IRR" value={metricText(normalizeIrrPercent(primary), '%')} />
              <Metric label="年等效循环" value={metricText(normalizeCycles(primary), ' 次')} />
            </div>
          )}
        </section>

        <section style={{ ...sectionStyle, marginTop: 16 }}>
          <h2 style={sectionTitleStyle}>四类交付物摘要</h2>
          <DeliverableSummaryPanel deliverables={deliverables} />
        </section>

        <section style={{ ...sectionStyle, marginTop: 16 }}>
          <h2 style={sectionTitleStyle}>经济性审计账本</h2>
          <FinancialAuditLedgerPanel rows={auditLedgerItems} />
        </section>

        {summary?.engine_diagnostics ? (
          <section style={{ ...sectionStyle, marginTop: 16 }}>
            <h2 style={sectionTitleStyle}>引擎诊断（约束分层 / 缓存 / 自适应种群）</h2>
            <EngineDiagnosticsPanel data={summary.engine_diagnostics} />
          </section>
        ) : null}

        {/* Step 2: Feasibility */}
        <section style={{ ...sectionStyle, marginTop: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24, borderRadius: '50%', background: '#2563eb', color: '#fff', fontSize: 11, fontWeight: 800, flexShrink: 0 }}>2</span>
            <span style={{ fontWeight: 700, fontSize: 16 }}>可行性验证</span>
          </div>
          {feasibility ? (
            <>
              <FeasibilityBanner summary={feasibilitySummary} />
              <div style={{ ...metricGridStyle, marginTop: 12 }}>
                <Metric label="推荐方案状态" value={feasibilityStatusText(feasibilitySummary)} />
                <Metric label="可行解数量" value={`${metricText(feasibilitySummary.feasibleCount)} / ${metricText(feasibilitySummary.populationSize)}`} />
                <Metric label="Archive 数量" value={metricText(feasibilitySummary.archiveSize)} />
                <Metric label="总违反量" value={metricText(feasibilitySummary.bestTotalViolation)} />
                <Metric label="循环次数超限" value={metricText(feasibilitySummary.bestCycleViolation, ' 次')} />
              </div>
            </>
          ) : (
            <div>暂无可行性诊断数据。</div>
          )}
        </section>

        {feasibility ? (
          <div style={{ ...chartGridStyle, marginTop: 16 }}>
            <ChartCard title="约束违反项">
              {feasibilityViolations.length ? <ViolationChart data={feasibilityViolations} /> : <EmptyChart />}
            </ChartCard>
            <ChartCard title="候选方案可行性分布">
              {candidateStatus.length ? <CandidateStatusChart data={candidateStatus} /> : <EmptyChart />}
            </ChartCard>
            <ChartCard title="候选方案违反量对比">
              {candidateViolations.length ? <CandidateViolationChart data={candidateViolations} /> : <EmptyChart />}
            </ChartCard>
          </div>
        ) : null}

        {/* Step 3: Grid Assessment */}
        <section style={{ ...sectionStyle, marginTop: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24, borderRadius: '50%', background: '#2563eb', color: '#fff', fontSize: 11, fontWeight: 800, flexShrink: 0 }}>3</span>
            <span style={{ fontWeight: 700, fontSize: 16 }}>配电网评估</span>
          </div>
          <NetworkTopologyPanel data={(networkTopology ?? null) as NetworkTopologyChart | null} />
        </section>

        <section style={{ ...sectionStyle, marginTop: 16 }}>
          <h2 style={sectionTitleStyle}>配电网影响风险清单</h2>
          <NetworkImpactRiskPanel voltageRows={voltageRiskRows} lineRows={lineRiskRows} transformerRows={transformerRiskRows} />
        </section>

        <section style={{ ...sectionStyle, marginTop: 16 }}>
          <div style={sectionHeaderRowStyle}>
            <h2 style={{ ...sectionTitleStyle, margin: 0 }}>自动接入线运行摘要</h2>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button type="button" onClick={() => setServiceLineFilter('all')} style={serviceLineFilter === 'all' ? activeChipBtnStyle : chipBtnStyle}>
                全部
              </button>
              <button type="button" onClick={() => setServiceLineFilter('large')} style={serviceLineFilter === 'large' ? activeChipBtnStyle : chipBtnStyle}>
                仅看偏大
              </button>
              <button type="button" onClick={() => setServiceLineFilter('small')} style={serviceLineFilter === 'small' ? activeChipBtnStyle : chipBtnStyle}>
                仅看偏小
              </button>
            </div>
          </div>

          <div style={{ color: '#6b7280', marginTop: 8, marginBottom: 12, lineHeight: 1.5 }}>
            这张表把自动生成的低压接入线配置，和本次结果里的线路运行电流、负载率放到一起。偏大/偏小按本项目自动接入线额定电流的前 20% / 后 20% 相对筛选。
          </div>

          {filteredAutoServiceLineRows.length ? (
            <div style={{ overflowX: 'auto' }}>
              <table style={resultTableStyle} aria-label="自动估算接入线运行结果">
                <thead>
                  <tr>
                    <th style={resultTableHeadStyle}>线路</th>
                    <th style={resultTableHeadStyle}>相对分组</th>
                    <th style={resultTableHeadStyle}>等值方式</th>
                    <th style={resultTableHeadStyle}>估算依据</th>
                    <th style={resultTableHeadStyle}>估算电流</th>
                    <th style={resultTableHeadStyle}>额定电流</th>
                    <th style={resultTableHeadStyle}>应急电流</th>
                    <th style={resultTableHeadStyle}>运行电流</th>
                    <th style={resultTableHeadStyle}>运行负载率</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAutoServiceLineRows.map((row) => {
                    const runtime = serviceLineRuntimeById.get(String(row.lineId ?? row.id ?? ''));
                    const level = classifyRelativeServiceLineSize(autoServiceLineRows, row.normamps);
                    return (
                      <tr key={String(row.lineId ?? row.name ?? `${row.fromBus}_${row.toBus}`)}>
                        <td style={resultTableCellStyle}>{String(row.name ?? row.lineId ?? '--')}</td>
                        <td style={resultTableCellStyle}>{relativeServiceLineLabel(level)}</td>
                        <td style={resultTableCellStyle}>
                          {row.serviceCableName
                            ? `${String(row.serviceCableName)} × ${metricText(row.serviceCableParallel)}；${ohmPerKmText(row.serviceEquivalentR1OhmPerKm, row.serviceEquivalentX1OhmPerKm)}`
                            : String(row.linecode ?? '--')}
                        </td>
                        <td style={resultTableCellStyle}>
                          {`配变 ${kvaText(row.serviceTransformerKva)} / 接入规模 ${kvaText(row.serviceResourceKva)} / ${metricText(row.serviceSecondaryKv, ' kV')}`}
                        </td>
                        <td style={resultTableCellStyle}>
                          {`配变侧 ${ampText(row.serviceTransformerCurrentA)} / 接入侧 ${ampText(row.serviceResourceCurrentA)}`}
                        </td>
                        <td style={resultTableCellStyle}>{ampText(row.normamps)}</td>
                        <td style={resultTableCellStyle}>{ampText(row.emergamps)}</td>
                        <td style={resultTableCellStyle}>{ampText(runtime?.currentA ?? runtime?.estimatedCurrentA)}</td>
                        <td style={resultTableCellStyle}>{metricText(runtime?.loadRatePct ?? runtime?.estimatedLoadRatePct, ' %')}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ color: '#6b7280' }}>
              {autoServiceLineRows.length ? '当前筛选条件下没有匹配的自动接入线。' : '当前结果里没有识别到自动接入线摘要。'}
            </div>
          )}
        </section>

        <div style={{ marginTop: 18, marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24, borderRadius: '50%', background: '#2563eb', color: '#fff', fontSize: 11, fontWeight: 800, flexShrink: 0 }}>4</span>
            <span style={{ fontWeight: 700, fontSize: 16 }}>详细分析</span>
          </div>
        </div>

        <div style={chartGridStyle}>
          <ChartCard title="储能接入对节点负荷影响">
            {storageImpact.length ? <StorageImpactChart data={storageImpact} /> : <EmptyChart />}
          </ChartCard>

          <ChartCard title="网侧约束与降损日趋势">
            {networkConstraintDaily.length ? <NetworkConstraintChart data={networkConstraintDaily} /> : <EmptyChart />}
          </ChartCard>

          <ChartCard title="线路额定/应急电流配置">
            {lineCapacity.length ? <LineCapacityChart data={lineCapacity} /> : <EmptyChart />}
          </ChartCard>

          <ChartCard title="月度收益与成本分解">
            {monthlyRevenue.length ? <MonthlyRevenueChart data={monthlyRevenue} /> : <EmptyChart />}
          </ChartCard>

          <ChartCard title={`代表日充放电与电价${representativeDay?.dayIndex ? `（第 ${representativeDay.dayIndex} 天）` : ''}`}>
            {representativeRows.length ? <RepresentativeDayChart data={representativeRows} /> : <EmptyChart />}
          </ChartCard>

          <ChartCard title="代表日 SOC 与小时净收益">
            {representativeRows.length ? <SocCashflowChart data={representativeRows} /> : <EmptyChart />}
          </ChartCard>

          <ChartCard title="全年逐时储能 SOC" fullWidth>
            {yearlySoc.length ? <YearlySocChart data={yearlySoc} /> : <EmptyChart />}
          </ChartCard>

          <ChartCard title="全年运行强度与收益波动">
            {dailyOperation.length ? <DailyOperationChart data={dailyOperation} /> : <EmptyChart />}
          </ChartCard>

          <ChartCard title="全寿命期现金流">
            {cashflow.length ? <CashflowChart data={cashflow} /> : <EmptyChart />}
          </ChartCard>

          <ChartCard title="投资构成">
            {capitalBreakdown.length ? <CapitalBreakdownChart data={capitalBreakdown} /> : <EmptyChart />}
          </ChartCard>

          <ChartCard title="年度价值贡献">
            {annualValueBreakdown.length ? <AnnualValueChart data={annualValueBreakdown} /> : <EmptyChart />}
          </ChartCard>

          <ChartCard title="关键财务与运行指标">
            {financialMetrics.length ? <FinancialMetricsChart data={financialMetrics} /> : <EmptyChart />}
          </ChartCard>

          <ChartCard title="候选方案经济性散点">
            {pareto.length ? <ParetoChart data={pareto} /> : <EmptyChart />}
          </ChartCard>

          <ChartCard title="优化收敛过程">
            {history.length ? <HistoryChart data={history} /> : <EmptyChart />}
          </ChartCard>
        </div>

        <section style={{ ...sectionStyle, marginTop: 16 }}>
          <h2 style={sectionTitleStyle}>summary_rows 表格</h2>
          {!summaryRows.length ? (
            <div>暂无 summary_rows。</div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', minWidth: 960 }} aria-label="summary_rows 数据表">
                <thead>
                  <tr>
                    {summaryKeys.map((key) => <th key={key} style={thStyle}>{key}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {summaryRows.map((row, idx) => {
                    const record = row as GenericRow;
                    return (
                      <tr key={idx}>
                        {summaryKeys.map((key) => (
                          <td key={key} style={tdStyle}>{String(record[key] ?? '')}</td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {plotFiles.length ? (
          <section style={{ ...sectionStyle, marginTop: 16 }}>
            <h2 style={sectionTitleStyle}>Python 绘图输出</h2>
            <div style={plotGridStyle}>
              {plotFiles.map((file) => (
                <div key={`${file.group}:${file.relative_path}`} style={plotCardStyle}>
                  <img
                    src={getResultFileDownloadUrl(projectId, file.relative_path, file.group, selectedTaskId || undefined)}
                    alt={file.name}
                    style={plotImageStyle}
                  />
                  <div style={{ fontWeight: 700, marginTop: 8 }}>{file.name}</div>
                  <div style={{ color: '#64748b', fontSize: 12, marginTop: 4 }}>{file.relative_path}</div>
                  <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                    <button type="button" style={btnStyle} onClick={() => handlePreview(file)}>预览</button>
                    <a
                      href={getResultFileDownloadUrl(projectId, file.relative_path, file.group, selectedTaskId || undefined)}
                      download={file.name}
                      style={{ ...btnStyle, textDecoration: 'none', color: '#111827' }}
                    >
                      下载
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        <section style={{ display: 'grid', gridTemplateColumns: '360px 1fr', gap: 16, marginTop: 16 }}>
          <div style={sectionStyle}>
            <h2 style={sectionTitleStyle}>结果文件列表</h2>
            {!files.length ? (
              <div>暂无结果文件。</div>
            ) : (
              <div style={{ border: '1px solid #ddd', maxHeight: 560, overflow: 'auto' }}>
                {files.map((file) => {
                  const isActive = selectedFile?.relative_path === file.relative_path && selectedFile?.group === file.group;
                  return (
                    <div
                      key={`${file.group}:${file.relative_path}`}
                      style={{
                        width: '100%',
                        textAlign: 'left',
                        padding: 10,
                        borderBottom: '1px solid #eee',
                        background: isActive ? '#eef2ff' : '#fff',
                        boxSizing: 'border-box',
                      }}
                    >
                      <div><strong>{file.name}</strong></div>
                      <div style={{ fontSize: 12, color: '#555' }}>{file.group}</div>
                      <div style={{ fontSize: 12, color: '#777' }}>{file.relative_path}</div>
                      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                        <button type="button" onClick={() => handlePreview(file)} style={smallBtnStyle}>
                          预览
                        </button>
                        <a
                          href={getResultFileDownloadUrl(projectId, file.relative_path, file.group, selectedTaskId || undefined)}
                          download={file.name}
                          style={{ ...smallBtnStyle, textDecoration: 'none', color: '#111827' }}
                        >
                          下载
                        </a>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div style={sectionStyle}>
            <h2 style={sectionTitleStyle}>选中文件预览</h2>
            {!selectedFile ? (
              <div>请选择左侧结果文件。</div>
            ) : previewLoading ? (
              <div>加载预览中...</div>
            ) : preview?.type === 'image' ? (
              <div>
                <div style={{ marginBottom: 8 }}>
                  <strong>{preview.file_name}</strong>
                  <div style={{ color: '#666', fontSize: 12 }}>{preview.relative_path}</div>
                </div>
                <img src={preview.content || ''} alt={preview.file_name} style={{ maxWidth: '100%', border: '1px solid #ddd', borderRadius: 8 }} />
              </div>
            ) : preview?.type === 'csv' ? (
              <div>
                <div style={{ marginBottom: 8 }}>
                  <strong>{preview.file_name}</strong>
                  <div style={{ color: '#666', fontSize: 12 }}>共 {preview.row_count ?? 0} 行，当前预览前 50 行。</div>
                </div>
                <div style={{ overflowX: 'auto', border: '1px solid #ddd' }}>
                  <table style={{ borderCollapse: 'collapse', minWidth: 900 }} aria-label="文件预览数据表">
                    <thead>
                      <tr>
                        {(preview.header ?? []).map((cell) => <th key={cell} style={thStyle}>{cell}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {(preview.rows ?? []).map((row, rowIdx) => (
                        <tr key={rowIdx}>
                          {row.map((cell, cellIdx) => <td key={cellIdx} style={tdStyle}>{cell}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <pre style={preStyle}>{preview?.content || '无可预览内容。'}</pre>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function FeasibilityBanner(props: { summary: GenericRow }) {
  const status = String(props.summary.status ?? 'unknown');
  const color = status === 'feasible' ? '#166534' : status === 'infeasible' ? '#991b1b' : '#92400e';
  const background = status === 'feasible' ? '#f0fdf4' : status === 'infeasible' ? '#fef2f2' : '#fffbeb';
  const border = status === 'feasible' ? '#bbf7d0' : status === 'infeasible' ? '#fecaca' : '#fde68a';
  return (
    <div style={{ border: `1px solid ${border}`, background, color, borderRadius: 8, padding: 14 }}>
      <strong>{feasibilityStatusText(props.summary)}</strong>
      <div style={{ marginTop: 6 }}>{String(props.summary.message ?? '未解析到可行性诊断说明。')}</div>
    </div>
  );
}

function ViolationChart(props: { data: ResultChartPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={310}>
      <BarChart data={props.data} layout="vertical" margin={{ top: 10, right: 18, bottom: 0, left: 78 }}>
        <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
        <XAxis type="number" />
        <YAxis dataKey="name" type="category" width={104} />
        <Tooltip formatter={numberTooltipFormatter} />
        <ReferenceLine x={0} stroke="#111827" strokeWidth={1} />
        <Bar dataKey="value" name="违反量" fill={COLORS.accent4} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function CandidateStatusChart(props: { data: ResultChartPoint[] }) {
  const total = props.data.reduce((sum, row) => sum + (toFiniteNumber(row.count) ?? 0), 0);
  if (total <= 0) return <EmptyChart />;
  return (
    <ResponsiveContainer width="100%" height={310}>
      <PieChart>
        <Tooltip formatter={numberTooltipFormatter} />
        <Legend />
        <Pie data={props.data} dataKey="count" nameKey="name" innerRadius={62} outerRadius={104} paddingAngle={2}>
          {props.data.map((entry, idx) => (
            <Cell key={String(entry.name ?? idx)} fill={String(entry.name).includes('不可行') ? COLORS.accent4 : COLORS.accent2} />
          ))}
        </Pie>
      </PieChart>
    </ResponsiveContainer>
  );
}

function CandidateViolationChart(props: { data: ResultChartPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={310}>
      <ComposedChart data={props.data} margin={{ top: 10, right: 18, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
        <XAxis dataKey="index" />
        <YAxis />
        <Tooltip formatter={numberTooltipFormatter} />
        <Legend />
        <Bar dataKey="cycleViolation" name="循环次数超限" fill={COLORS.accent4} opacity={0.7} />
        <Line type="monotone" dataKey="totalViolation" name="总违反量" stroke="#111827" strokeWidth={2} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function StorageImpactChart(props: { data: ResultChartPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={310}>
      <ComposedChart data={props.data} margin={{ top: 10, right: 18, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
        <XAxis dataKey="hour" />
        <YAxis yAxisId="power" />
        <YAxis yAxisId="tariff" orientation="right" />
        <Tooltip formatter={numberTooltipFormatter} />
        <Legend />
        <ReferenceLine yAxisId="power" y={0} stroke="#111827" strokeWidth={1} />
        <Bar yAxisId="power" dataKey="dischargeKw" name="放电削峰" fill={COLORS.accent2} />
        <Bar yAxisId="power" dataKey="chargeKw" name="充电增荷" fill={COLORS.accent1} />
        <Line yAxisId="power" type="monotone" dataKey="actualNetLoadKw" name="储能前净负荷" stroke={COLORS.base} strokeWidth={2} dot={false} />
        <Line yAxisId="power" type="monotone" dataKey="gridExchangeKw" name="储能后并网功率" stroke="#111827" strokeWidth={2} dot={false} />
        <Line yAxisId="tariff" type="stepAfter" dataKey="tariffYuanPerKwh" name="电价" stroke={COLORS.accent3} strokeWidth={2} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function NetworkConstraintChart(props: { data: ResultChartPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={310}>
      <ComposedChart data={props.data} margin={{ top: 10, right: 18, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
        <XAxis dataKey="dayIndex" />
        <YAxis yAxisId="penalty" />
        <YAxis yAxisId="power" orientation="right" />
        <Tooltip formatter={numberTooltipFormatter} />
        <Legend />
        <ReferenceLine yAxisId="power" y={0} stroke="#111827" strokeWidth={1} />
        <Bar yAxisId="penalty" dataKey="transformerPenaltyWan" name="变压器罚金" fill={COLORS.accent4} opacity={0.7} />
        <Bar yAxisId="penalty" dataKey="voltagePenaltyWan" name="电压罚金" fill={COLORS.accent1} opacity={0.7} />
        <Line yAxisId="power" type="monotone" dataKey="maxGridExchangeKw" name="日最大并网功率" stroke={COLORS.base} strokeWidth={1.6} dot={false} />
        <Line yAxisId="power" type="monotone" dataKey="opendssLossReductionKwh" name="OpenDSS日网损差" stroke="#0f766e" strokeWidth={1.6} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function LineCapacityChart(props: { data: ResultChartPoint[] }) {
  const data = props.data.slice(0, 32);
  return (
    <ResponsiveContainer width="100%" height={310}>
      <BarChart data={data} layout="vertical" margin={{ top: 10, right: 18, bottom: 0, left: 78 }}>
        <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
        <XAxis type="number" />
        <YAxis dataKey="lineId" type="category" width={104} />
        <Tooltip formatter={numberTooltipFormatter} />
        <Legend />
        <Bar dataKey="normamps" name="额定电流 A" fill={COLORS.base} />
        <Bar dataKey="emergamps" name="应急电流 A" fill={COLORS.accent1} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function MonthlyRevenueChart(props: { data: ResultChartPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={310}>
      <ComposedChart data={props.data} margin={{ top: 10, right: 18, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
        <XAxis dataKey="month" />
        <YAxis />
        <Tooltip formatter={numberTooltipFormatter} />
        <Legend />
        <ReferenceLine y={0} stroke="#111827" strokeWidth={1} />
        <Bar dataKey="arbitrageRevenueWan" name="套利收益" stackId="revenue" fill={COLORS.base} />
        <Bar dataKey="demandSavingWan" name="需量收益" stackId="revenue" fill={COLORS.accent1} />
        <Bar dataKey="serviceNetRevenueWan" name="服务净收益" stackId="revenue" fill={COLORS.accent2} />
        <Bar dataKey="capacityRevenueWan" name="容量收益" stackId="revenue" fill={COLORS.accent3} />
        <Bar dataKey="lossReductionRevenueWan" name="降损收益" stackId="revenue" fill="#0f766e" />
        <Bar dataKey="penaltyCostWan" name="退化与罚金" fill={COLORS.accent4} />
        <Line type="monotone" dataKey="netCashflowWan" name="月净现金流" stroke="#111827" strokeWidth={2} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function RepresentativeDayChart(props: { data: ResultChartPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={310}>
      <ComposedChart data={props.data} margin={{ top: 10, right: 18, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
        <XAxis dataKey="hour" />
        <YAxis yAxisId="power" />
        <YAxis yAxisId="tariff" orientation="right" />
        <Tooltip formatter={numberTooltipFormatter} />
        <Legend />
        <ReferenceLine yAxisId="power" y={0} stroke="#111827" strokeWidth={1} />
        <Bar yAxisId="power" dataKey="dischargeKw" name="放电功率" fill={COLORS.accent2} />
        <Bar yAxisId="power" dataKey="chargeKw" name="充电功率" fill={COLORS.accent1} />
        <Line yAxisId="power" type="monotone" dataKey="gridExchangeKw" name="并网交换功率" stroke="#111827" strokeWidth={2} dot={false} />
        <Line yAxisId="tariff" type="stepAfter" dataKey="tariffYuanPerKwh" name="分时电价" stroke={COLORS.accent3} strokeWidth={2} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function SocCashflowChart(props: { data: ResultChartPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={310}>
      <ComposedChart data={props.data} margin={{ top: 10, right: 18, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
        <XAxis dataKey="hour" />
        <YAxis yAxisId="soc" domain={[0, 1]} />
        <YAxis yAxisId="cash" orientation="right" />
        <Tooltip formatter={numberTooltipFormatter} />
        <Legend />
        <ReferenceLine yAxisId="cash" y={0} stroke="#111827" strokeWidth={1} />
        <Bar yAxisId="cash" dataKey="netCashflowYuan" name="小时净收益" fill={COLORS.accent4} opacity={0.45} />
        <Line yAxisId="soc" type="natural" dataKey="socClose" name="SOC" stroke={COLORS.accent2} strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function YearlySocChart(props: { data: ResultChartPoint[] }) {
  const dataLen = props.data.length;
  const [startIndex, setStartIndex] = useState(0);
  const [endIndex, setEndIndex] = useState(Math.max(0, dataLen - 1));
  const containerRef = useRef<HTMLDivElement>(null);
  const rangeRef = useRef({ start: startIndex, end: endIndex });
  rangeRef.current = { start: startIndex, end: endIndex };

  useEffect(() => {
    const max = Math.max(0, dataLen - 1);
    setStartIndex(0);
    setEndIndex(max);
  }, [dataLen]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (dataLen === 0) return;
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const mouseXRatio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const { start, end } = rangeRef.current;
      const currentRange = end - start;
      const centerIdx = Math.round(start + currentRange * mouseXRatio);
      const zoomFactor = 1.5;
      let newRange: number;
      if (e.deltaY < 0) { newRange = Math.round(currentRange / zoomFactor); }
      else { newRange = Math.round(currentRange * zoomFactor); }
      newRange = Math.max(24, Math.min(dataLen - 1, newRange));
      const half = Math.round(newRange / 2);
      let newStart = centerIdx - half;
      let newEnd = centerIdx + half;
      if (newStart < 0) { newEnd -= newStart; newStart = 0; }
      if (newEnd >= dataLen) { newStart -= newEnd - (dataLen - 1); newEnd = dataLen - 1; }
      newStart = Math.max(0, newStart);
      newEnd = Math.min(dataLen - 1, newEnd);
      setStartIndex(newStart);
      setEndIndex(newEnd);
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [dataLen]);

  return (
    <div ref={containerRef} style={{ overflow: 'hidden' }}>
      <ResponsiveContainer width="100%" height={310}>
        <ComposedChart data={props.data} margin={{ top: 10, right: 18, bottom: 8, left: 0 }}>
          <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
          <XAxis
            dataKey="hourOfYear"
            tickFormatter={formatHourOfYearTick}
            minTickGap={28}
          />
          <YAxis domain={[0, 1]} />
          <Tooltip formatter={numberTooltipFormatter} labelFormatter={formatHourOfYearLabel} />
          <Legend />
          <Line
            type="monotone"
            dataKey="socClose"
            name="SOC"
            stroke={COLORS.accent2}
            strokeWidth={1.8}
            dot={false}
            isAnimationActive={false}
          />
          <Brush
            dataKey="hourOfYear"
            height={22}
            travellerWidth={8}
            tickFormatter={formatHourOfYearTick}
            startIndex={startIndex}
            endIndex={endIndex}
            onChange={(e) => {
              setStartIndex(e.startIndex ?? 0);
              setEndIndex(e.endIndex ?? dataLen - 1);
            }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function DailyOperationChart(props: { data: ResultChartPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={310}>
      <ComposedChart data={props.data} margin={{ top: 10, right: 18, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
        <XAxis dataKey="dayIndex" />
        <YAxis yAxisId="throughput" />
        <YAxis yAxisId="cashflow" orientation="right" />
        <Tooltip formatter={numberTooltipFormatter} />
        <Legend />
        <Line yAxisId="throughput" type="monotone" dataKey="throughputKwh" name="日吞吐量" stroke={COLORS.base} strokeWidth={1.2} dot={false} opacity={0.3} />
        <Line yAxisId="throughput" type="monotone" dataKey="throughputMa7Kwh" name="吞吐量7日均值" stroke={COLORS.accent1} strokeWidth={2} dot={false} />
        <Line yAxisId="cashflow" type="monotone" dataKey="netCashflowMa7Yuan" name="净收益7日均值" stroke="#111827" strokeWidth={2} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function formatHourOfYearTick(value: unknown): string {
  const hourOfYear = toFiniteNumber(value);
  if (hourOfYear === null) return '';
  return `D${Math.floor(hourOfYear / 24) + 1}`;
}

function formatHourOfYearLabel(value: unknown): string {
  const hourOfYear = toFiniteNumber(value);
  if (hourOfYear === null) return '';
  return `第 ${Math.floor(hourOfYear / 24) + 1} 天 ${Math.floor(hourOfYear % 24)} 时`;
}

function CashflowChart(props: { data: ResultChartPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={310}>
      <ComposedChart data={props.data} margin={{ top: 10, right: 18, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
        <XAxis dataKey="year" />
        <YAxis />
        <Tooltip formatter={numberTooltipFormatter} />
        <Legend />
        <ReferenceLine y={0} stroke="#111827" strokeWidth={1} />
        <Bar dataKey="operatingRevenueWan" name="运行收益" fill={COLORS.base} opacity={0.72} />
        <Bar dataKey="operatingCostWan" name="运行成本" fill={COLORS.accent4} opacity={0.72} />
        <Bar dataKey="omCostWan" name="运维成本" fill={COLORS.accent1} opacity={0.72} />
        <Bar dataKey="replacementCostWan" name="更换成本" fill="#7c2d12" opacity={0.72} />
        <Bar dataKey="salvageValueWan" name="残值" fill={COLORS.accent2} opacity={0.72} />
        <Line type="monotone" dataKey="discountedNetCashflowWan" name="折现净现金流" stroke={COLORS.accent1} strokeWidth={2} />
        <Line type="monotone" dataKey="cumulativeDiscountedWan" name="累计折现现金流" stroke={COLORS.base} strokeWidth={2.2} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function CapitalBreakdownChart(props: { data: ResultChartPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={310}>
      <PieChart>
        <Tooltip formatter={numberTooltipFormatter} />
        <Legend />
        <Pie data={props.data} dataKey="valueWan" nameKey="name" innerRadius={62} outerRadius={104} paddingAngle={2}>
          {props.data.map((entry, idx) => (
            <Cell key={String(entry.name ?? idx)} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
          ))}
        </Pie>
      </PieChart>
    </ResponsiveContainer>
  );
}

function AnnualValueChart(props: { data: ResultChartPoint[] }) {
  const height = Math.max(360, props.data.length * 38 + 72);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={props.data} layout="vertical" margin={{ top: 10, right: 18, bottom: 0, left: 8 }}>
        <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
        <XAxis type="number" />
        <YAxis dataKey="name" type="category" width={120} interval={0} />
        <Tooltip formatter={numberTooltipFormatter} />
        <ReferenceLine x={0} stroke="#111827" strokeWidth={1} />
        <Bar dataKey="valueWan" name="金额">
          {props.data.map((entry, idx) => (
            <Cell key={String(entry.name ?? idx)} fill={(toFiniteNumber(entry.valueWan) ?? 0) >= 0 ? COLORS.base : COLORS.accent4} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function FinancialMetricsChart(props: { data: ResultChartPoint[] }) {
  return (
    <div style={metricGridStyle}>
      {props.data.map((item) => (
        <Metric
          key={String(item.name)}
          label={String(item.name)}
          value={metricTextWithUnit(item.value, item.unit)}
        />
      ))}
    </div>
  );
}

function ParetoChart(props: { data: ResultChartPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={310}>
      <ScatterChart margin={{ top: 10, right: 18, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
        <XAxis dataKey="initialInvestmentWan" name="初始投资" type="number" />
        <YAxis dataKey="npvWan" name="NPV" type="number" />
        <ZAxis dataKey="ratedEnergyKwh" range={[70, 220]} />
        <Tooltip formatter={numberTooltipFormatter} cursor={{ strokeDasharray: '3 3' }} />
        <Legend />
        <Scatter data={props.data} name="候选方案">
          {props.data.map((entry, idx) => (
            <Cell key={String(entry.index ?? idx)} fill={entry.feasible ? COLORS.accent2 : COLORS.accent4} />
          ))}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
}

function HistoryChart(props: { data: ResultChartPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={310}>
      <ComposedChart data={props.data} margin={{ top: 10, right: 18, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
        <XAxis dataKey="generation" />
        <YAxis yAxisId="npv" />
        <YAxis yAxisId="count" orientation="right" allowDecimals={false} />
        <Tooltip formatter={numberTooltipFormatter} />
        <Legend />
        <Line yAxisId="npv" type="monotone" dataKey="bestNpvWan" name="最优NPV" stroke={COLORS.base} strokeWidth={2} />
        <Line yAxisId="count" type="monotone" dataKey="archiveSize" name="Archive大小" stroke={COLORS.accent1} strokeWidth={2} />
        <Bar yAxisId="count" dataKey="feasibleCount" name="可行解数量" fill={COLORS.accent2} opacity={0.55} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function normalizeEngineDiagnostics(data: EngineDiagnosticsPayload): EngineDiagnosticsScenario[] {
  if (!data || typeof data !== 'object') return [];
  const maybeMulti = data as { scenarios?: EngineDiagnosticsScenario[] };
  if (Array.isArray(maybeMulti.scenarios)) return maybeMulti.scenarios.filter((item) => item && typeof item === 'object');
  return [data as EngineDiagnosticsScenario];
}

function EngineDiagnosticsPanel(props: { data: EngineDiagnosticsPayload }) {
  const scenarios = normalizeEngineDiagnostics(props.data);
  if (!scenarios.length) {
    return <div style={{ color: '#6b7280' }}>暂无引擎诊断数据。</div>;
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {scenarios.map((scenario, idx) => (
        <EngineDiagnosticsScenarioBlock
          key={String(scenario.scenario ?? idx)}
          scenario={scenario}
          index={idx}
        />
      ))}
    </div>
  );
}

function EngineDiagnosticsScenarioBlock(props: { scenario: EngineDiagnosticsScenario; index: number }) {
  const { scenario, index } = props;
  const cache = scenario.cache_stats ?? {};
  const breakdown = scenario.constraint_breakdown ?? {};
  const raw = breakdown.raw ?? {};
  const history = Array.isArray(scenario.population_history) ? scenario.population_history : [];
  const hitRate = toFiniteNumber(cache.hit_rate);
  const hitRateText = hitRate === null ? '--' : `${(hitRate * 100).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}%`;
  const rawEntries = Object.entries(raw)
    .map(([key, value]) => [key, toFiniteNumber(value)] as const)
    .filter(([, value]) => value !== null && Math.abs(value as number) > 1e-9);
  const historyData = history.map((row) => ({
    generation: toFiniteNumber(row.generation) ?? 0,
    population_size: toFiniteNumber(row.population_size) ?? 0,
    feasible_count: toFiniteNumber(row.feasible_count) ?? 0,
    archive_size: toFiniteNumber(row.archive_size) ?? 0,
    best_npv_yuan: toFiniteNumber(row.best_npv_yuan),
  }));
  const scenarioLabel = scenario.scenario ? String(scenario.scenario) : `场景 ${index + 1}`;
  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 16, background: '#fafbff' }}>
      <div style={{ fontWeight: 800, fontSize: 16, marginBottom: 12 }}>场景：{scenarioLabel}</div>

      <div style={{ ...metricGridStyle, marginBottom: 12 }}>
        <Metric label="硬约束违反 (hard)" value={metricText(breakdown.hard)} />
        <Metric label="中等约束 (medium)" value={metricText(breakdown.medium)} />
        <Metric label="软约束 (soft)" value={metricText(breakdown.soft)} />
        <Metric label="缓存命中率" value={hitRateText} />
        <Metric label="缓存命中次数" value={metricText(cache.cache_hits)} />
        <Metric label="缓存未命中次数" value={metricText(cache.cache_misses)} />
        <Metric label="缓存条目数" value={metricText(cache.cache_size)} />
      </div>

      {rawEntries.length ? (
        <>
          <div style={{ fontWeight: 700, marginBottom: 8, color: '#334155' }}>约束原始指标（非零项）</div>
          <div style={{ ...metricGridStyle, marginBottom: 12 }}>
            {rawEntries.map(([key, value]) => (
              <Metric key={key} label={key} value={metricText(value)} />
            ))}
          </div>
        </>
      ) : null}

      <div style={{ fontWeight: 700, marginBottom: 8, color: '#334155' }}>自适应种群历史</div>
      {historyData.length ? (
        <ResponsiveContainer width="100%" height={310}>
          <ComposedChart data={historyData} margin={{ top: 10, right: 18, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
            <XAxis dataKey="generation" />
            <YAxis yAxisId="npv" />
            <YAxis yAxisId="count" orientation="right" allowDecimals={false} />
            <Tooltip formatter={numberTooltipFormatter} />
            <Legend />
            <Bar yAxisId="count" dataKey="feasible_count" name="可行解数量" fill={COLORS.accent2} opacity={0.55} />
            <Line yAxisId="count" type="monotone" dataKey="population_size" name="种群规模" stroke={COLORS.accent1} strokeWidth={2} dot={false} />
            <Line yAxisId="count" type="monotone" dataKey="archive_size" name="Archive 大小" stroke={COLORS.accent3} strokeWidth={2} dot={false} />
            <Line yAxisId="npv" type="monotone" dataKey="best_npv_yuan" name="最优 NPV (元)" stroke={COLORS.base} strokeWidth={2.2} dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      ) : (
        <EmptyChart />
      )}
    </div>
  );
}

function NetworkTopologyPanel(props: { data: NetworkTopologyChart | null }) {
  const nodes = chartRows(props.data?.nodes);
  const edges = chartRows(props.data?.edges);
  const summary = chartRows(props.data?.summary);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [fullscreenOpen, setFullscreenOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const panDragRef = useRef<{ clientX: number; clientY: number; panX: number; panY: number } | null>(null);
  const topologySvgRef = useRef<SVGSVGElement | null>(null);
  const topologyWheelRef = useRef<HTMLDivElement | null>(null);
  const topologyStateRef = useRef({ zoom: 1, pan: { x: 0, y: 0 }, minX: 0, minY: 0, baseWidth: 600, baseHeight: 420 });
  useEffect(() => {
    const element = topologyWheelRef.current;
    if (!element) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const st = topologyStateRef.current;
      const nextZoom = Math.max(0.45, Math.min(3.5, st.zoom * (event.deltaY < 0 ? 1.12 : 0.89)));
      const rect = element.getBoundingClientRect();
      if (!rect.width || !rect.height) {
        setZoom(nextZoom);
        return;
      }
      const pointerXRatio = (event.clientX - rect.left) / rect.width;
      const pointerYRatio = (event.clientY - rect.top) / rect.height;
      const currentX = st.minX + st.pan.x;
      const currentY = st.minY + st.pan.y;
      const zoomedWidth = st.baseWidth / st.zoom;
      const zoomedHeight = st.baseHeight / st.zoom;
      const pointerModelX = currentX + pointerXRatio * zoomedWidth;
      const pointerModelY = currentY + pointerYRatio * zoomedHeight;
      const nextWidth = st.baseWidth / nextZoom;
      const nextHeight = st.baseHeight / nextZoom;
      setZoom(nextZoom);
      setPan({
        x: pointerModelX - pointerXRatio * nextWidth - st.minX,
        y: pointerModelY - pointerYRatio * nextHeight - st.minY,
      });
    };
    element.addEventListener('wheel', onWheel, { passive: false });
    return () => element.removeEventListener('wheel', onWheel);
  });
  if (!nodes.length) return <EmptyChart />;

  const nodeById = new Map(nodes.map((node) => [String(node.id ?? ''), node]));
  const xs = nodes.map((node) => toFiniteNumber(node.x) ?? 0);
  const ys = nodes.map((node) => toFiniteNumber(node.y) ?? 0);
  const minX = Math.min(...xs, 0) - 80;
  const maxX = Math.max(...xs, 900) + 120;
  const minY = Math.min(...ys, 0) - 80;
  const maxY = Math.max(...ys, 520) + 120;
  const baseWidth = Math.max(600, maxX - minX);
  const baseHeight = Math.max(420, maxY - minY);
  topologyStateRef.current = { zoom, pan, minX, minY, baseWidth, baseHeight };
  const zoomedWidth = baseWidth / zoom;
  const zoomedHeight = baseHeight / zoom;
  const viewBox = `${minX + pan.x} ${minY + pan.y} ${zoomedWidth} ${zoomedHeight}`;
  const qualityLabel = topologyQualityLabel(props.data?.dataQuality);
  const panelStyle = fullscreenOpen ? topologyFullscreenStyle : undefined;
  const canvasStyle = fullscreenOpen ? topologyCanvasFullscreenStyle : topologyCanvasStyle;
  const zoomDisplayMode = zoom < 0.75 ? 'overview' : zoom < 1.45 ? 'summary' : 'detail';
  const showSummaryLabels = detailsOpen || zoomDisplayMode !== 'overview';
  const showDetailedLabels = detailsOpen || zoomDisplayMode === 'detail';
  const zoomDisplayLabel = zoomDisplayMode === 'overview' ? '总览' : zoomDisplayMode === 'summary' ? '摘要' : '详细';
  const labelScale = Math.max(0.42, Math.min(1, 1 / zoom));
  const nodeVisualScale = Math.max(0.62, Math.min(1, 1 / Math.sqrt(zoom)));
  const topLoadedLineIds = new Set(
    edges
      .map((edge) => ({ id: String(edge.id ?? ''), loadRate: toFiniteNumber(edge.loadRatePct) }))
      .filter((edge) => edge.id && edge.loadRate !== null)
      .sort((a, b) => (b.loadRate ?? 0) - (a.loadRate ?? 0))
      .slice(0, 3)
      .map((edge) => edge.id),
  );
  const occupiedTopologyBoxes: TopologyLabelPlacement[] = nodes.map((node) => {
    const x = toFiniteNumber(node.x) ?? 0;
    const y = toFiniteNumber(node.y) ?? 0;
    const isTarget = node.storageTarget === true;
    const size = (isTarget ? 78 : 64) * nodeVisualScale;
    return {
      tx: x,
      ty: y,
      x: x - size / 2,
      y: y - size / 2,
      width: size,
      height: size + 20,
    };
  });
  const setClampedZoom = (nextZoom: number) => setZoom(Math.max(0.45, Math.min(3.5, nextZoom)));
  const resetView = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };
  const handleTopologyPointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    panDragRef.current = { clientX: event.clientX, clientY: event.clientY, panX: pan.x, panY: pan.y };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const handleTopologyPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const drag = panDragRef.current;
    if (!drag) return;
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const dx = (event.clientX - drag.clientX) * (zoomedWidth / rect.width);
    const dy = (event.clientY - drag.clientY) * (zoomedHeight / rect.height);
    setPan({ x: drag.panX - dx, y: drag.panY - dy });
  };
  const handleTopologyPointerUp = (event: React.PointerEvent<SVGSVGElement>) => {
    panDragRef.current = null;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // Pointer capture may already be released by the browser.
    }
  };

  return (
    <div style={panelStyle}>
      {props.data?.warnings?.length ? <WarningPanel warnings={props.data.warnings} /> : null}
      <div style={topologyToolbarStyle}>
        <div style={{ color: '#475569', fontSize: 13 }}>当前显示：{qualityLabel}</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button type="button" onClick={() => setDetailsOpen((value) => !value)} style={smallBtnStyle}>
            {detailsOpen ? '关闭强制详细' : '强制详细标注'}
          </button>
          <button type="button" onClick={() => setSummaryOpen((value) => !value)} style={smallBtnStyle}>
            {summaryOpen ? '隐藏承载能力摘要' : '显示承载能力摘要'}
          </button>
          <button type="button" onClick={() => setClampedZoom(zoom * 1.18)} style={smallBtnStyle}>放大</button>
          <button type="button" onClick={() => setClampedZoom(zoom / 1.18)} style={smallBtnStyle}>缩小</button>
          <button type="button" onClick={resetView} style={smallBtnStyle}>复位</button>
          <button type="button" onClick={() => setFullscreenOpen((value) => !value)} style={smallBtnStyle}>
            {fullscreenOpen ? '退出全屏' : '全屏查看'}
          </button>
        </div>
      </div>
      <div style={topologyViewHintStyle}>滚轮缩放，拖拽平移；当前缩放 {Math.round(zoom * 100)}%，标注层级：{zoomDisplayLabel}</div>
      <div style={topologyLegendStripStyle}>
        <TopologyLegend />
      </div>
      <div ref={topologyWheelRef} style={canvasStyle}>
        <svg
          ref={topologySvgRef}
          viewBox={viewBox}
          width="100%"
          height="100%"
          preserveAspectRatio="xMidYMid meet"
          style={topologySvgStyle}
          onPointerDown={handleTopologyPointerDown}
          onPointerMove={handleTopologyPointerMove}
          onPointerUp={handleTopologyPointerUp}
          onPointerLeave={handleTopologyPointerUp}
        >
            <defs>
              <linearGradient id="topology-floor-gradient" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#f8fbff" />
                <stop offset="100%" stopColor="#edf3f8" />
              </linearGradient>
              <pattern id="topology-grid" width="80" height="80" patternUnits="userSpaceOnUse">
                <path d="M 80 0 L 0 0 0 80" fill="none" stroke="#e2e8f0" strokeWidth="1" />
              </pattern>
              <filter id="topology-node-shadow" x="-60%" y="-60%" width="220%" height="220%">
                <feDropShadow dx="5" dy="8" stdDeviation="4" floodColor="#0f172a" floodOpacity="0.22" />
              </filter>
              <filter id="topology-label-shadow" x="-30%" y="-30%" width="160%" height="160%">
                <feDropShadow dx="2" dy="4" stdDeviation="2" floodColor="#0f172a" floodOpacity="0.12" />
              </filter>
            </defs>
            <rect x={minX - baseWidth} y={minY - baseHeight} width={baseWidth * 3} height={baseHeight * 3} fill="url(#topology-floor-gradient)" />
            <rect x={minX - baseWidth} y={minY - baseHeight} width={baseWidth * 3} height={baseHeight * 3} fill="url(#topology-grid)" opacity={0.5} />
            {edges.map((edge) => {
              const from = nodeById.get(String(edge.from_node_id ?? ''));
              const to = nodeById.get(String(edge.to_node_id ?? ''));
              if (!from || !to) return null;
              const x1 = toFiniteNumber(from.x) ?? 0;
              const y1 = toFiniteNumber(from.y) ?? 0;
              const x2 = toFiniteNumber(to.x) ?? 0;
              const y2 = toFiniteNumber(to.y) ?? 0;
              const loadRate = toFiniteNumber(edge.loadRatePct);
              const currentA = toFiniteNumber(edge.currentA ?? edge.estimatedCurrentA);
              const normamps = toFiniteNumber(edge.normamps);
              const emergamps = toFiniteNumber(edge.emergamps);
              const serviceTransformerCurrentA = toFiniteNumber(edge.serviceTransformerCurrentA);
              const serviceResourceCurrentA = toFiniteNumber(edge.serviceResourceCurrentA);
              const downstreamLoadKw = toFiniteNumber(edge.downstreamLoadKw);
              const estimatedRequiredCurrentA = toFiniteNumber(edge.estimatedRequiredCurrentA);
              const recommendedCurrentA = toFiniteNumber(edge.recommendedCurrentA);
              const capacityInsufficient = String(edge.capacityCheckStatus ?? '') === 'insufficient';
              const terminal1PowerKw = toFiniteNumber(edge.terminal1PowerKw);
              const stroke = topologyEdgeColor(loadRate);
              const isOpen = edge.enabled === false || edge.normallyOpen === true;
              const isTransformerLink = edge.isTransformerLink === true;
              const isTopLoadedLine = topLoadedLineIds.has(String(edge.id ?? ''));
              const isOverloadedLine = loadRate !== null && loadRate > 100;
              const shouldLabelLine = showDetailedLabels || isOverloadedLine || (showSummaryLabels && isTopLoadedLine);
              const flowDirection = String(edge.flowDirection ?? 'forward') === 'reverse' ? 'reverse' : 'forward';
              const lineDx = x2 - x1;
              const lineDy = y2 - y1;
              const lineLength = Math.hypot(lineDx, lineDy);
              const useElbowPath = !isTransformerLink && Math.abs(lineDx) > 24 && Math.abs(lineDy) > 24;
              const elbowX = x1 + lineDx * 0.52;
              const edgePathD = useElbowPath
                ? `M ${x1} ${y1} L ${elbowX} ${y1} L ${elbowX} ${y2} L ${x2} ${y2}`
                : `M ${x1} ${y1} L ${x2} ${y2}`;
              const edgeWidth = isTransformerLink ? 2.1 : loadRate !== null ? Math.min(5.2, Math.max(1.8, loadRate / 34)) : 1.8;
              const flowSign = flowDirection === 'reverse' ? -1 : 1;
              const flowUx = useElbowPath ? 0 : lineLength > 0 ? (lineDx / lineLength) * flowSign : 0;
              const flowUy = useElbowPath ? Math.sign(lineDy || 1) * flowSign : lineLength > 0 ? (lineDy / lineLength) * flowSign : 0;
              const arrowCenterX = useElbowPath ? elbowX : (x1 + x2) / 2;
              const arrowCenterY = (y1 + y2) / 2;
              const arrowTipX = arrowCenterX + flowUx * 10;
              const arrowTipY = arrowCenterY + flowUy * 10;
              const arrowBackX = arrowCenterX - flowUx * 8;
              const arrowBackY = arrowCenterY - flowUy * 8;
              const arrowPerpX = -flowUy * 5;
              const arrowPerpY = flowUx * 5;
              const flowArrowPoints = [
                `${arrowTipX},${arrowTipY}`,
                `${arrowBackX + arrowPerpX},${arrowBackY + arrowPerpY}`,
                `${arrowBackX - arrowPerpX},${arrowBackY - arrowPerpY}`,
              ].join(' ');
              const flowDirectionText = flowDirection === 'reverse'
                ? `${String(to.name || to.id || '')} → ${String(from.name || from.id || '')}`
                : `${String(from.name || from.id || '')} → ${String(to.name || to.id || '')}`;
              const edgeLabelLines = isTransformerLink
                ? showDetailedLabels ? ['主变连接'] : []
                : [
                    loadRate === null
                      ? (showDetailedLabels ? String(edge.linecode ?? '') : '')
                      : (shouldLabelLine ? `负载 ${metricText(loadRate, '%')}` : ''),
                    showDetailedLabels ? `潮流 ${flowDirection === 'reverse' ? '反向' : '正向'}` : '',
                    showDetailedLabels && terminal1PowerKw !== null ? `P ${metricText(Math.abs(terminal1PowerKw), ' kW')}` : '',
                    showDetailedLabels && edge.autoServiceLine === true
                      ? `自动接入 ${ampText(serviceTransformerCurrentA)} / ${ampText(serviceResourceCurrentA)}`
                      : '',
                    isOverloadedLine && currentA !== null ? `${metricText(currentA, ' A')} / ${metricText(normamps, ' A')}` : '',
                    isOverloadedLine && downstreamLoadKw !== null ? `下游 ${metricText(downstreamLoadKw, ' kW')}` : '',
                    capacityInsufficient && estimatedRequiredCurrentA !== null
                      ? `容量建议 ${ampText(estimatedRequiredCurrentA)} → ${ampText(recommendedCurrentA)}`
                      : '',
              ].filter(Boolean);
              const hasEdgeLabel = edgeLabelLines.length > 0;
              const labelWidth = isOverloadedLine || showDetailedLabels ? 128 : 82;
              const labelHeight = 18 + edgeLabelLines.length * 14;
              const labelBoxWidth = labelWidth * labelScale;
              const labelBoxHeight = labelHeight * labelScale;
              const edgeLabelOffset = Math.max(28, labelBoxHeight + 16);
              const edgePerpX = lineLength > 0 ? -lineDy / lineLength : 0;
              const edgePerpY = lineLength > 0 ? lineDx / lineLength : -1;
              const edgeLabelCandidate = (tx: number, ty: number): TopologyLabelPlacement => ({
                tx,
                ty,
                x: tx - labelBoxWidth / 2,
                y: ty + (-labelHeight + 8) * labelScale,
                width: labelBoxWidth,
                height: labelBoxHeight,
              });
              const edgeLabelPlacement = hasEdgeLabel
                ? reserveTopologyPlacement(occupiedTopologyBoxes, [
                    edgeLabelCandidate((x1 + x2) / 2 + edgePerpX * edgeLabelOffset, (y1 + y2) / 2 - 12 + edgePerpY * edgeLabelOffset),
                    edgeLabelCandidate((x1 + x2) / 2 - edgePerpX * edgeLabelOffset, (y1 + y2) / 2 - 12 - edgePerpY * edgeLabelOffset),
                    edgeLabelCandidate((x1 + x2) / 2 + edgePerpX * edgeLabelOffset * 2, (y1 + y2) / 2 - 12 + edgePerpY * edgeLabelOffset * 2),
                    edgeLabelCandidate((x1 + x2) / 2 - edgePerpX * edgeLabelOffset * 2, (y1 + y2) / 2 - 12 - edgePerpY * edgeLabelOffset * 2),
                    edgeLabelCandidate((x1 + x2) / 2, (y1 + y2) / 2 - 12),
                    edgeLabelCandidate((x1 + x2) / 2 + 72, (y1 + y2) / 2 - 12),
                    edgeLabelCandidate((x1 + x2) / 2 - 72, (y1 + y2) / 2 - 12),
                  ])
                : null;
              const serviceTitle = edge.autoServiceLine === true
                ? ` | 自动接入估算 配变侧 ${ampText(serviceTransformerCurrentA)} / 接入侧 ${ampText(serviceResourceCurrentA)}`
                : '';
              const capacityTitle = capacityInsufficient
                ? ` | 容量建议 估算需求 ${ampText(estimatedRequiredCurrentA)} / 建议 ${ampText(recommendedCurrentA)}`
                : '';
              const title = `${String(edge.name || edge.id || '')} | 潮流方向 ${flowDirectionText} | 端口有功 ${metricText(terminal1PowerKw, ' kW')} | 负载率 ${metricText(loadRate, '%')} | 电流 ${metricText(currentA, ' A')} | 额定 ${metricText(normamps, ' A')} | 应急 ${metricText(emergamps, ' A')}${serviceTitle}${capacityTitle}`;
              return (
                <g key={String(edge.id)}>
                  <title>{title}</title>
                  <path
                    d={edgePathD}
                    fill="none"
                    stroke="#334155"
                    strokeWidth={edgeWidth + 3.2}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    transform="translate(6 8)"
                    opacity={isOpen ? 0.08 : isTransformerLink ? 0.1 : 0.18}
                  />
                  <path
                    d={edgePathD}
                    fill="none"
                    stroke={stroke}
                    strokeWidth={edgeWidth}
                    strokeDasharray={isOpen ? '8 6' : undefined}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    opacity={isOpen ? 0.35 : isTransformerLink ? 0.55 : 0.86}
                  />
                  {!isOpen ? (
                    <path
                      d={edgePathD}
                      fill="none"
                      stroke="#ffffff"
                      strokeWidth={Math.max(0.7, edgeWidth * 0.22)}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      transform="translate(-1 -1)"
                      opacity={isTransformerLink ? 0.25 : 0.38}
                    />
                  ) : null}
                  {!isOpen && lineLength > 1 ? (
                    <polygon
                      points={flowArrowPoints}
                      fill={stroke}
                      stroke="#ffffff"
                      strokeWidth={1.2}
                      opacity={0.96}
                    />
                  ) : null}
                  {edgeLabelPlacement ? (
                    <>
                      <path
                        d={`M ${(x1 + x2) / 2} ${(y1 + y2) / 2} L ${edgeLabelPlacement.tx} ${edgeLabelPlacement.ty}`}
                        fill="none"
                        stroke="#64748b"
                        strokeWidth={Math.max(0.6, 1.4 * labelScale)}
                        strokeDasharray="4 4"
                        opacity={0.72}
                      />
                      <circle cx={(x1 + x2) / 2} cy={(y1 + y2) / 2} r={Math.max(1.4, 2.2 * labelScale)} fill="#64748b" opacity={0.72} />
                      <g transform={`translate(${edgeLabelPlacement.tx}, ${edgeLabelPlacement.ty}) scale(${labelScale})`}>
                        <rect
                          x={-labelWidth / 2}
                          y={-labelHeight + 8}
                          width={labelWidth}
                          height={labelHeight}
                          rx={6}
                          fill="#ffffff"
                          stroke="#dbe3ef"
                          opacity={0.92}
                          filter="url(#topology-label-shadow)"
                        />
                        <text textAnchor="middle" fontSize="10" fill="#334155" fontWeight={700}>
                          {edgeLabelLines.map((line, idx) => (
                            <tspan key={`${line}-${idx}`} x={0} y={-labelHeight + 24 + idx * 14}>
                              {line}
                            </tspan>
                          ))}
                        </text>
                      </g>
                    </>
                  ) : null}
                </g>
              );
            })}

            {nodes.map((node) => {
              const x = toFiniteNumber(node.x) ?? 0;
              const y = toFiniteNumber(node.y) ?? 0;
              const isTarget = node.storageTarget === true;
              const nodeType = String(node.type ?? '');
              const label = String(node.bus || node.name || node.id || '');
              const nodeShortLabel = zoomDisplayMode === 'overview' && !isTarget ? String(node.id || label) : label;
              const baselineVoltageMin = toFiniteNumber(node.baselineVoltagePuMin);
              const baselineVoltageMax = toFiniteNumber(node.baselineVoltagePuMax);
              const voltageMin = toFiniteNumber(node.voltagePuMin);
              const voltageMax = toFiniteNumber(node.voltagePuMax);
              const storageVoltageIncrement = toFiniteNumber(node.storageVoltageViolationIncrementPu);
              const designLoadKw = toFiniteNumber(node.designLoadKw);
              const capacityLimitKw = toFiniteNumber(node.capacityLimitKw);
              const capacityMarginBeforeKw = toFiniteNumber(node.capacityMarginBeforeKw);
              const capacityMarginDeltaKw = toFiniteNumber(node.capacityMarginDeltaKw);
              const storagePowerKw = toFiniteNumber(node.storagePowerKw);
              const storageEnergyKwh = toFiniteNumber(node.storageEnergyKwh);
              const voltageColor = topologyVoltageColor(voltageMin, voltageMax);
              const baselineVoltageLabel = puRangeText(baselineVoltageMin, baselineVoltageMax);
              const voltageLabel = puRangeText(voltageMin, voltageMax);
              const hasVoltageAlert = (voltageMin !== null && voltageMin < 0.95) || (voltageMax !== null && voltageMax > 1.05);
              const hasStorageVoltageWorsening = storageVoltageIncrement !== null && storageVoltageIncrement > 0.002;
              const showNodeInfo = showDetailedLabels || isTarget || hasVoltageAlert || hasStorageVoltageWorsening;
              const detailedInfoLines = [
                baselineVoltageLabel ? `储前电压标幺值 ${baselineVoltageLabel}` : '',
                voltageLabel ? `储后电压标幺值 ${voltageLabel}` : '储后电压标幺值 --',
                isTarget && storagePowerKw !== null && storageEnergyKwh !== null
                  ? `储能配置 ${metricText(storagePowerKw, ' kW')} / ${metricText(storageEnergyKwh, ' kWh')}`
                  : '',
                capacityMarginDeltaKw !== null && (showDetailedLabels || isTarget || Math.abs(capacityMarginDeltaKw) > 1e-6)
                  ? `储后裕度增量 ${signedMetricText(capacityMarginDeltaKw, ' kW')}`
                  : '',
              ].filter(Boolean);
              const compactInfoLines = [
                hasVoltageAlert && voltageLabel ? `储后V ${voltageLabel}` : '',
                isTarget && storagePowerKw !== null && storageEnergyKwh !== null
                  ? `储能 ${metricText(storagePowerKw, ' kW')} / ${metricText(storageEnergyKwh, ' kWh')}`
                  : '',
                isTarget && capacityMarginDeltaKw !== null
                  ? `裕度Δ ${signedMetricText(capacityMarginDeltaKw, ' kW')}`
                  : '',
              ].filter(Boolean);
              const infoLines = showDetailedLabels ? detailedInfoLines : compactInfoLines;
              const nodeInfoHeight = 16 + infoLines.length * 15;
              const nodeInfoWidth = isTarget ? 216 : 156;
              const nodeLabelWidth = nodeInfoWidth * labelScale;
              const nodeLabelHeight = nodeInfoHeight * labelScale;
              const nodeClearance = (isTarget ? 54 : 46) * nodeVisualScale;
              const nodeInfoCandidate = (dx: number, dy: number): TopologyLabelPlacement => ({
                tx: dx,
                ty: dy,
                x: x + dx - nodeLabelWidth / 2,
                y: y + dy,
                width: nodeLabelWidth,
                height: nodeLabelHeight,
              });
              const nodeInfoPlacement = showNodeInfo && infoLines.length
                ? reserveTopologyPlacement(occupiedTopologyBoxes, [
                    nodeInfoCandidate(0, nodeClearance),
                    nodeInfoCandidate(nodeClearance + nodeLabelWidth / 2, -nodeLabelHeight / 2),
                    nodeInfoCandidate(-(nodeClearance + nodeLabelWidth / 2), -nodeLabelHeight / 2),
                    nodeInfoCandidate(0, -(nodeLabelHeight + nodeClearance)),
                    nodeInfoCandidate(nodeClearance + nodeLabelWidth / 2, nodeClearance * 0.75),
                    nodeInfoCandidate(-(nodeClearance + nodeLabelWidth / 2), nodeClearance * 0.75),
                    nodeInfoCandidate(nodeClearance + nodeLabelWidth / 2, -(nodeLabelHeight + nodeClearance * 0.75)),
                    nodeInfoCandidate(-(nodeClearance + nodeLabelWidth / 2), -(nodeLabelHeight + nodeClearance * 0.75)),
                  ])
                : null;
              const title = [
                `${label}`,
                `储前电压标幺值 ${baselineVoltageLabel || '--'}`,
                `储后电压标幺值 ${voltageLabel || '--'}`,
                `负荷 ${metricText(designLoadKw, ' kW')}`,
                `承载上限 ${metricText(capacityLimitKw, ' kW')}`,
                `储前裕度 ${metricText(capacityMarginBeforeKw, ' kW')}`,
                `储后裕度增量 ${signedMetricText(capacityMarginDeltaKw, ' kW')}`,
                isTarget ? `储能配置 ${metricText(storagePowerKw, ' kW')} / ${metricText(storageEnergyKwh, ' kWh')}` : '',
              ].filter(Boolean).join(' | ');
              return (
                <g key={String(node.id)} transform={`translate(${x}, ${y})`}>
                  <title>{title}</title>
                  <g transform={`scale(${nodeVisualScale})`}>
                    <TopologyNodeSymbol
                      type={nodeType}
                      isTarget={isTarget}
                      voltageColor={voltageColor}
                      missingVoltage={voltageMin === null && voltageMax === null}
                    />
                    <text y={31} textAnchor="middle" fontSize="10.5" fill="#0f172a" fontWeight={700}>
                      {nodeShortLabel.length > 14 ? `${nodeShortLabel.slice(0, 13)}…` : nodeShortLabel}
                    </text>
                  </g>
                  {nodeInfoPlacement ? (
                    <>
                      <path
                        d={`M 0 0 L ${nodeInfoPlacement.tx} ${nodeInfoPlacement.ty + nodeLabelHeight / 2}`}
                        fill="none"
                        stroke={hasStorageVoltageWorsening ? COLORS.accent4 : isTarget ? '#f59e0b' : '#64748b'}
                        strokeWidth={Math.max(0.6, 1.3 * labelScale)}
                        strokeDasharray="4 4"
                        opacity={0.72}
                      />
                      <circle
                        cx={0}
                        cy={0}
                        r={Math.max(1.4, 2.2 * labelScale)}
                        fill={hasStorageVoltageWorsening ? COLORS.accent4 : isTarget ? '#f59e0b' : '#64748b'}
                        opacity={0.72}
                      />
                      <g transform={`translate(${nodeInfoPlacement.tx}, ${nodeInfoPlacement.ty}) scale(${labelScale})`}>
                        <rect
                          x={-nodeInfoWidth / 2}
                          y={0}
                          width={nodeInfoWidth}
                          height={nodeInfoHeight}
                          rx={6}
                          fill="#ffffff"
                          stroke={hasStorageVoltageWorsening ? COLORS.accent4 : isTarget ? '#f59e0b' : '#dbe3ef'}
                          opacity={0.94}
                        />
                        <text textAnchor="middle" fontSize="10" fill="#334155" fontWeight={700}>
                          {infoLines.map((line, idx) => (
                            <tspan
                              key={`${line}-${idx}`}
                              x={0}
                              y={17 + idx * 15}
                              fill={
                                line.startsWith('储后裕度增量') && capacityMarginDeltaKw !== null && capacityMarginDeltaKw < -1e-6
                                  ? COLORS.accent4
                                  : line.startsWith('储后裕度增量') && capacityMarginDeltaKw !== null && capacityMarginDeltaKw > 1e-6
                                    ? COLORS.accent2
                                    : line.includes('储后电压标幺值')
                                      ? voltageColor
                                      : line.startsWith('储能配置')
                                        ? COLORS.accent1
                                        : '#334155'
                              }
                            >
                              {line}
                            </tspan>
                          ))}
                        </text>
                      </g>
                    </>
                  ) : null}
                </g>
              );
            })}
        </svg>
        {summaryOpen ? (
          <aside style={topologySummaryStyle}>
            <h3 style={chartTitleStyle}>承载能力摘要</h3>
            <div style={topologySummaryGridStyle}>
              {summary.map((item) => (
                <Metric
                  key={String(item.name)}
                  label={String(item.name)}
                  value={metricTextWithUnit(item.value, item.unit)}
                />
              ))}
            </div>
          </aside>
        ) : null}
      </div>
    </div>
  );
}

function TopologyLegend() {
  return (
    <div style={legendStyle}>
      <div><span style={{ ...legendSwatchStyle, background: COLORS.accent2 }} />正常</div>
      <div><span style={{ ...legendSwatchStyle, background: COLORS.accent1 }} />接近上限</div>
      <div><span style={{ ...legendSwatchStyle, background: COLORS.accent4 }} />过载/越限</div>
      <div><span style={{ ...legendSwatchStyle, background: COLORS.gray }} />估算/缺少实测</div>
      <div><span style={{ ...legendSwatchStyle, background: '#cbd5e1' }} />缺少电压</div>
      <div style={{ color: '#475569' }}>线路箭头表示潮流方向</div>
      <div style={{ color: '#475569' }}>节点标注显示储前/储后电压标幺值、储能配置与储后裕度增量</div>
    </div>
  );
}

function topologyEdgeColor(loadRate: number | null) {
  if (loadRate === null) return COLORS.gray;
  if (loadRate > 100) return COLORS.accent4;
  if (loadRate > 80) return COLORS.accent1;
  return COLORS.accent2;
}

function topologyVoltageColor(voltageMin: number | null, voltageMax: number | null) {
  if (voltageMin === null && voltageMax === null) return '#cbd5e1';
  if ((voltageMin !== null && voltageMin < 0.93) || (voltageMax !== null && voltageMax > 1.07)) return COLORS.accent4;
  if ((voltageMin !== null && voltageMin < 0.95) || (voltageMax !== null && voltageMax > 1.05)) return COLORS.accent1;
  return COLORS.accent2;
}

function topologyQualityLabel(dataQuality: string | undefined) {
  if (dataQuality === 'opendss') return '真实潮流结果拓扑热力图';
  if (dataQuality === 'mixed') return '部分真实潮流结果拓扑热力图';
  return '估算拓扑图';
}

function topologyNodeColor(type: string) {
  if (type === 'grid' || type === 'source') return '#b91c1c';
  if (type === 'transformer') return COLORS.accent1;
  if (type === 'load') return COLORS.accent2;
  if (type === 'branch' || type === 'ring_main_unit') return COLORS.gray;
  if (type === 'bus') return '#2563eb';
  return COLORS.base;
}

function TopologyNodeSymbol(props: { type: string; isTarget: boolean; voltageColor: string; missingVoltage: boolean }) {
  const color = topologyNodeColor(props.type);
  const ringRadius = props.isTarget ? 22 : 17;
  const ringOpacity = props.missingVoltage ? 0.28 : 0.9;
  const commonStroke = props.isTarget ? COLORS.accent1 : color;
  return (
    <g filter="url(#topology-node-shadow)">
      <ellipse cx={7} cy={12} rx={ringRadius + 9} ry={ringRadius * 0.48} fill="#0f172a" opacity={0.13} />
      <circle
        r={ringRadius + 5}
        fill="#ffffff"
        stroke={props.voltageColor}
        strokeWidth={props.isTarget ? 4 : 3}
        opacity={ringOpacity}
      />
      {props.type === 'grid' || props.type === 'source' ? (
        <g>
          <circle cx={5} cy={6} r={ringRadius} fill="#7f1d1d" opacity={0.2} />
          <circle r={ringRadius} fill="#fff7ed" stroke={commonStroke} strokeWidth={2.4} />
          <path d="M -3 -10 L -11 2 H -3 L -6 11 L 8 -4 H 0 L 3 -10 Z" fill={commonStroke} />
        </g>
      ) : props.type === 'transformer' ? (
        <g>
          <rect x={-13} y={-7} width={36} height={26} rx={6} fill="#92400e" opacity={0.22} />
          <rect x={-18} y={-13} width={36} height={26} rx={6} fill="#fff7ed" stroke={commonStroke} strokeWidth={2.2} />
          <circle cx={-6} cy={0} r={6} fill="none" stroke={commonStroke} strokeWidth={2} />
          <circle cx={6} cy={0} r={6} fill="none" stroke={commonStroke} strokeWidth={2} />
        </g>
      ) : props.type === 'load' ? (
        <g>
          <rect x={-12} y={-6} width={34} height={24} rx={5} fill="#166534" opacity={0.2} />
          <rect x={-17} y={-12} width={34} height={24} rx={5} fill="#ecfdf5" stroke={commonStroke} strokeWidth={2.2} />
          <path d="M -10 6 V -2 L -4 -7 L 2 -2 V 6 M 2 -2 L 8 -7 L 14 -2 V 6" fill="none" stroke={commonStroke} strokeWidth={2} strokeLinejoin="round" />
        </g>
      ) : props.type === 'branch' || props.type === 'ring_main_unit' || props.type === 'bus' ? (
        <g>
          <rect x={-14} y={-4} width={38} height={20} rx={10} fill="#1e3a8a" opacity={0.18} />
          <rect x={-19} y={-10} width={38} height={20} rx={10} fill="#eff6ff" stroke={commonStroke} strokeWidth={2.2} />
          <path d="M -12 0 H 12 M -7 -7 V 7 M 0 -7 V 7 M 7 -7 V 7" stroke={commonStroke} strokeWidth={2} strokeLinecap="round" />
        </g>
      ) : (
        <g>
          <circle cx={5} cy={6} r={ringRadius} fill="#0f172a" opacity={0.18} />
          <circle r={ringRadius} fill={color} stroke="#ffffff" strokeWidth={2.4} />
          <circle r={4} fill="#ffffff" opacity={0.9} />
        </g>
      )}
      {props.isTarget ? (
        <path d="M 0 -30 L 5 -20 H -5 Z" fill={COLORS.accent1} stroke="#ffffff" strokeWidth={1} />
      ) : null}
    </g>
  );
}

function WarningPanel(props: { warnings: string[] }) {
  return (
    <div style={warningStyle}>
      {props.warnings.map((warning) => (
        <div key={warning}>{warning}</div>
      ))}
    </div>
  );
}

function DiagnosticsStrip(props: { diagnostics: GenericRow }) {
  const status = String(props.diagnostics.status ?? '').trim();
  const reason = String(props.diagnostics.reason ?? '').trim();
  const busCount = toFiniteNumber(props.diagnostics.bus_voltage_summary_count);
  const lineCount = toFiniteNumber(props.diagnostics.line_loading_summary_count);
  return (
    <div style={diagnosticStripStyle}>
      <strong>拓扑缓存：</strong>
      {cacheStatusText(status)}
      {reason ? `（${reason}）` : ''}
      {busCount !== null || lineCount !== null
        ? `；电压汇总 ${metricText(busCount)} 项，线路汇总 ${metricText(lineCount)} 项`
        : ''}
    </div>
  );
}

function cacheStatusText(value: string): string {
  const mapping: Record<string, string> = {
    hit: '命中',
    rebuilt: '已重建',
    missing: '缺失/数据不足',
    invalid: '失效',
  };
  return mapping[value] ?? (value || '--');
}

function ChartCard(props: { title: string; children: React.ReactNode; fullWidth?: boolean }) {
  return (
    <section style={props.fullWidth ? fullWidthChartCardStyle : chartCardStyle}>
      <h3 style={chartTitleStyle}>{props.title}</h3>
      {props.children}
    </section>
  );
}

function EmptyChart() {
  return <div style={{ color: '#6b7280', padding: 18 }}>暂无可视化数据。</div>;
}

function Metric(props: { label: string; value: string }) {
  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 14 }}>
      <div style={{ color: '#6b7280', fontSize: 13, marginBottom: 8 }}>{props.label}</div>
      <div style={{ fontWeight: 800 }}>{props.value}</div>
    </div>
  );
}

function FinancialAuditLedgerPanel(props: { rows: GenericRow[] }) {
  if (!props.rows.length) {
    return <div style={{ color: '#6b7280' }}>暂无经济性审计账本。重新运行后将展示各收益/成本项的单价、数量和公式来源。</div>;
  }
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={resultTableStyle} aria-label="经济性审计账本">
        <thead>
          <tr>
            <th style={resultTableHeadStyle}>项目</th>
            <th style={resultTableHeadStyle}>类型</th>
            <th style={resultTableHeadStyle}>金额</th>
            <th style={resultTableHeadStyle}>数量</th>
            <th style={resultTableHeadStyle}>单价</th>
            <th style={resultTableHeadStyle}>年度金额校核</th>
            <th style={resultTableHeadStyle}>异常提示</th>
            <th style={resultTableHeadStyle}>计算公式</th>
            <th style={resultTableHeadStyle}>数据来源</th>
          </tr>
        </thead>
        <tbody>
          {props.rows.map((row) => {
            const anomaly = ledgerAnomalyText(row);
            return (
              <tr key={`${String(row.name ?? '')}_${String(row.category ?? '')}`}>
                <td style={resultTableCellStyle}>{String(row.name ?? '--')}</td>
                <td style={resultTableCellStyle}>{ledgerCategoryText(row.category)}</td>
                <td style={resultTableCellStyle}>{yuanToWanText(row.amount_yuan)}</td>
                <td style={resultTableCellStyle}>{ledgerQuantityText(row)}</td>
                <td style={resultTableCellStyle}>{ledgerUnitPriceText(row)}</td>
                <td style={resultTableCellStyle}>{ledgerComputedAmountText(row)}</td>
                <td style={{ ...resultTableCellStyle, color: anomaly === '正常' ? '#15803d' : '#b45309' }}>{anomaly}</td>
                <td style={resultTableCellStyle}>{String(row.formula ?? '--')}</td>
                <td style={resultTableCellStyle}>{String(row.source ?? '--')}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function NetworkImpactRiskPanel(props: { voltageRows: GenericRow[]; lineRows: GenericRow[]; transformerRows: GenericRow[] }) {
  if (!props.voltageRows.length && !props.lineRows.length && !props.transformerRows.length) {
    return <div style={{ color: '#6b7280' }}>暂无风险清单。新结果会从 OpenDSS 储前/储后逐时潮流中提取 Top 风险节点、线路和变压器。</div>;
  }
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: 16 }}>
      <RiskTable
        title="节点电压风险"
        rows={props.voltageRows}
        columns={[
          ['bus', '母线'],
          ['classification', '归因'],
          ['baseline_violation_hours', '储前越限 h'],
          ['with_storage_violation_hours', '储后越限 h'],
          ['max_baseline_violation_pu', '储前最大 pu'],
          ['max_with_storage_violation_pu', '储后最大 pu'],
        ]}
      />
      <RiskTable
        title="线路过载风险"
        rows={props.lineRows}
        columns={[
          ['line', '线路'],
          ['classification', '归因'],
          ['baseline_overload_hours', '储前过载 h'],
          ['with_storage_overload_hours', '储后过载 h'],
          ['max_baseline_loading_pct', '储前最大 %'],
          ['max_with_storage_loading_pct', '储后最大 %'],
        ]}
      />
      <RiskTable
        title="变压器过载风险"
        rows={props.transformerRows}
        columns={[
          ['transformer', '配变'],
          ['classification', '归因'],
          ['baseline_overload_hours', '储前过载 h'],
          ['with_storage_overload_hours', '储后过载 h'],
          ['overload_hour_delta', '变化 h'],
          ['max_with_storage_loading_pct', '储后最大 %'],
        ]}
      />
    </div>
  );
}

function RiskTable(props: { title: string; rows: GenericRow[]; columns: Array<[string, string]> }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <h3 style={chartTitleStyle}>{props.title}</h3>
      {!props.rows.length ? (
        <div style={{ color: '#6b7280' }}>暂无。</div>
      ) : (
        <table style={resultTableStyle} aria-label="风险分析数据表">
          <thead>
            <tr>
              {props.columns.map(([, label]) => (
                <th key={label} style={resultTableHeadStyle}>{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {props.rows.map((row, rowIndex) => (
              <tr key={`${props.title}_${rowIndex}`}>
                {props.columns.map(([key]) => (
                  <td key={key} style={resultTableCellStyle}>
                    {key === 'classification' ? riskClassificationText(row[key]) : metricText(row[key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function riskClassificationText(value: unknown): string {
  const text = String(value ?? '').trim();
  const mapping: Record<string, string> = {
    storage_induced: '储能引起',
    worsened_by_storage: '储能加重',
    improved_by_storage: '储能改善',
    cleared_by_storage: '储能清除',
    existing_background: '原网背景风险',
    normal: '正常',
  };
  return mapping[text] ?? (text || '--');
}

function ledgerCategoryText(value: unknown): string {
  const text = String(value ?? '').toLowerCase();
  if (text === 'revenue') return '收益';
  if (text === 'cost') return '成本';
  if (text === 'subsidy') return '补贴';
  return '--';
}

function ledgerQuantityText(row: GenericRow): string {
  const value = toFiniteNumber(row.quantity);
  if (value === null) return '--';
  const unit = row.quantity_unit ? ` ${String(row.quantity_unit)}` : '';
  return metricText(value, unit);
}

function ledgerUnitPriceText(row: GenericRow): string {
  const value = toFiniteNumber(row.unit_price);
  if (value === null) return '--';
  const unit = row.unit_price_unit ? ` ${String(row.unit_price_unit)}` : '';
  return metricText(value, unit);
}

function ledgerComputedAmountText(row: GenericRow): string {
  const quantity = toFiniteNumber(row.quantity);
  const unitPrice = toFiniteNumber(row.unit_price);
  if (quantity === null || unitPrice === null) return '--';
  return yuanToWanText(quantity * unitPrice);
}

function ledgerAnomalyText(row: GenericRow): string {
  const amount = toFiniteNumber(row.amount_yuan);
  const quantity = toFiniteNumber(row.quantity);
  const unitPrice = toFiniteNumber(row.unit_price);
  const category = String(row.category ?? '').toLowerCase();
  const issues: string[] = [];
  if (row.amount_yuan !== null && row.amount_yuan !== undefined && row.amount_yuan !== '' && amount === null) issues.push('金额非数值');
  if (row.quantity !== null && row.quantity !== undefined && row.quantity !== '' && quantity === null) issues.push('数量非数值');
  if (row.unit_price !== null && row.unit_price !== undefined && row.unit_price !== '' && unitPrice === null) issues.push('单价非数值');
  if (amount !== null && Math.abs(amount) > 100_000_000_000) issues.push('金额异常大');
  if ((category === 'revenue' || category === 'subsidy') && amount !== null && amount < 0) issues.push('收益为负');
  if (amount !== null && quantity !== null && unitPrice !== null) {
    const expected = quantity * unitPrice;
    const tolerance = Math.max(1, Math.abs(amount) * 0.01);
    if (Math.abs(expected - amount) > tolerance) issues.push('单价×数量偏差>1%');
  } else if (amount !== null && Math.abs(amount) > 1 && (quantity === null || unitPrice === null)) {
    issues.push('缺少数量或单价');
  }
  return issues.length ? issues.join('；') : '正常';
}

function DeliverableSummaryPanel(props: { deliverables: GenericRow }) {
  const configuration = toRecord(props.deliverables.configuration);
  const operation = toRecord(props.deliverables.operation);
  const financial = toRecord(props.deliverables.financial);
  const networkImpact = toRecord(props.deliverables.network_impact);
  const runHealth = toRecord(props.deliverables.run_health);
  const operationMetrics = toRecord(operation?.annual_metrics);
  const financialMetrics = toRecord(financial?.core_metrics);
  const networkDelta = toRecord(networkImpact?.delta);
  const networkQuality = toRecord(networkImpact?.data_quality);
  const targetAreaConclusion = toRecord(networkImpact?.target_area_conclusion);
  const networkAttribution = toRecord(networkImpact?.attribution_summary);
  const auditLedgerSummary = toRecord(financial?.audit_ledger_summary);
  const hasReports = [configuration, operation, financial, networkImpact, runHealth].some((item) => Boolean(item && Object.keys(item).length));
  const npvWan = normalizeNpvWan(financialMetrics);
  const irrPercent = normalizeIrrPercent(financialMetrics);
  const healthSummary = toRecord(runHealth?.summary);
  const issueCounts = toRecord(runHealth?.issue_counts);
  const totalIssues = toFiniteNumber(issueCounts?.total ?? healthSummary?.issue_count);
  const healthIssues = recordRows(runHealth?.issues);
  const backgroundPolicy = String(configuration?.background_load_policy ?? '').trim();
  const reportModules = [
    {
      title: '储能配置方案',
      conclusion: `${metricText(configuration?.rated_power_kw, ' kW')} / ${metricText(configuration?.rated_energy_kwh, ' kWh')}，接入 ${metricText(configuration?.target_id)}。`,
      metrics: [`目标母线 ${metricText(configuration?.target_bus)}`, `策略 ${metricText(configuration?.strategy_name ?? configuration?.strategy_id)}`],
      risk: healthIssues.some((item) => item.related_section === 'feasibility') ? '存在可行性健康检查问题，需复核配置边界。' : '未发现配置层健康异常。',
      source: 'configuration_report.json / best_result_summary.json',
    },
    {
      title: '年运行情况',
      conclusion: `${metricText(operationMetrics?.equivalent_full_cycles, ' 次循环')}，吞吐 ${metricText(operationMetrics?.battery_throughput_kwh, ' kWh')}。`,
      metrics: [`SOC/能量守恒：${healthIssues.some((item) => item.related_section === 'operation') ? '需复核' : '通过'}`],
      risk: String(healthIssues.find((item) => item.related_section === 'operation')?.suggestion ?? '暂无运行健康风险提示。'),
      source: 'operation_report.json / best_annual_hourly_operation.csv',
    },
    {
      title: '经济性分析',
      conclusion: `NPV ${metricText(npvWan, ' 万元')}，IRR ${metricText(irrPercent, '%')}。`,
      metrics: [`账本项 ${metricText(auditLedgerSummary?.item_count)} 项`, `异常提示 ${metricText(auditLedgerSummary?.anomaly_count)} 项`],
      risk: String(healthIssues.find((item) => item.related_section === 'financial')?.suggestion ?? '以审计账本逐项核对单价、数量和年度金额。'),
      source: 'financial_report.json / best_cashflow_table.csv',
    },
    {
      title: '配网承载力变化',
      conclusion: String(targetAreaConclusion?.conclusion ?? '暂无目标接入区域结论，需重新运行生成配网影响报告。'),
      metrics: [
        `安全越限Δ ${signedMetricText(networkDelta?.safety_violation_hours, ' h')}`,
        `降损 ${signedMetricText(networkDelta?.loss_reduction_kwh, ' kWh')}`,
      ],
      risk: String(networkAttribution?.target_area ?? '暂无配网归因摘要。'),
      source: 'network_impact_report.json / OpenDSS trace',
    },
  ];

  if (!hasReports) {
    return (
      <div style={{ color: '#6b7280', lineHeight: 1.6 }}>
        当前结果尚未生成结构化交付物 JSON。重新运行一次求解后，将生成配置方案、运行情况、经济性、配电网影响四份报告。
      </div>
    );
  }

  return (
    <>
      <div style={metricGridStyle}>
        <Metric
          label="① 储能配置方案"
          value={`${metricText(configuration?.rated_power_kw, ' kW')} / ${metricText(configuration?.rated_energy_kwh, ' kWh')}`}
        />
        <Metric
          label="储能接入位置"
          value={`${metricText(configuration?.target_id)} / ${metricText(configuration?.target_bus)}`}
        />
        <Metric
          label="② 年运行情况"
          value={`${metricText(operationMetrics?.equivalent_full_cycles, ' 次循环')} / ${metricText(operationMetrics?.battery_throughput_kwh, ' kWh')}`}
        />
        <Metric
          label="③ 经济性"
          value={`NPV ${metricText(npvWan, ' 万元')} / IRR ${metricText(irrPercent, '%')}`}
        />
        <Metric
          label="④ 配电网影响"
          value={`ΔSafety ${signedMetricText(networkDelta?.safety_violation_hours, ' h')} / 降损 ${signedMetricText(networkDelta?.loss_reduction_kwh, ' kWh')}`}
        />
        <Metric
          label="OpenDSS 数据覆盖"
          value={`${metricText(networkQuality?.opendss_trace_hours, ' h')} / ${networkQuality?.has_opendss_loss ? '含网损' : '未含网损'}`}
        />
        <Metric
          label="运行健康检查"
          value={`${healthStatusText(runHealth?.status)} / ${totalIssues === null ? '--' : `${totalIssues} 项问题`}`}
        />
      </div>
      {backgroundPolicy ? <div style={deliverableNoteStyle}>{backgroundPolicy}</div> : null}
      <div style={reportModuleGridStyle}>
        {reportModules.map((module) => (
          <div key={module.title} style={reportModuleItemStyle}>
            <h3 style={reportModuleTitleStyle}>{module.title}</h3>
            <div style={reportModuleConclusionStyle}>{module.conclusion}</div>
            <div style={reportModuleMetaStyle}>{module.metrics.join(' ｜ ')}</div>
            <div style={reportModuleRiskStyle}>{module.risk}</div>
            <div style={reportModuleSourceStyle}>数据来源：{module.source}</div>
          </div>
        ))}
      </div>
    </>
  );
}

function healthStatusText(value: unknown): string {
  const text = String(value ?? '').trim().toLowerCase();
  if (text === 'passed') return '通过';
  if (text === 'warning') return '有警告';
  if (text === 'failed' || text === 'critical') return '严重异常';
  return '--';
}

const metricGridStyle: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 };
const deliverableNoteStyle: React.CSSProperties = { marginTop: 12, color: '#4b5563', fontSize: 13, lineHeight: 1.6 };
const reportModuleGridStyle: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12, marginTop: 14 };
const reportModuleItemStyle: React.CSSProperties = { border: '1px solid #e5e7eb', borderRadius: 8, padding: 14, background: '#ffffff' };
const reportModuleTitleStyle: React.CSSProperties = { margin: '0 0 8px 0', fontSize: 16, color: '#0f172a' };
const reportModuleConclusionStyle: React.CSSProperties = { color: '#111827', fontWeight: 700, lineHeight: 1.5 };
const reportModuleMetaStyle: React.CSSProperties = { marginTop: 8, color: '#475569', fontSize: 12, lineHeight: 1.5 };
const reportModuleRiskStyle: React.CSSProperties = { marginTop: 8, color: '#92400e', fontSize: 12, lineHeight: 1.5 };
const reportModuleSourceStyle: React.CSSProperties = { marginTop: 8, color: '#64748b', fontSize: 12, lineHeight: 1.5 };
const chartGridStyle: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: 16 };
const sectionStyle: React.CSSProperties = { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 20 };
const chartCardStyle: React.CSSProperties = { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 18, minHeight: 380 };
const fullWidthChartCardStyle: React.CSSProperties = { ...chartCardStyle, gridColumn: '1 / -1' };
const sectionTitleStyle: React.CSSProperties = { margin: '0 0 14px 0', fontSize: 24 };
const sectionHeaderRowStyle: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' };
const chartTitleStyle: React.CSSProperties = { margin: '0 0 12px 0', fontSize: 18 };
const plotGridStyle: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14 };
const plotCardStyle: React.CSSProperties = { border: '1px solid #e5e7eb', borderRadius: 8, padding: 12, background: '#fff' };
const plotImageStyle: React.CSSProperties = { width: '100%', height: 220, objectFit: 'contain', background: '#f8fafc', border: '1px solid #e5e7eb', borderRadius: 8 };
const topologyToolbarStyle: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 10, flexWrap: 'wrap' };
const topologyCanvasStyle: React.CSSProperties = { position: 'relative', height: 660, border: '1px solid #dbe3ef', borderRadius: 8, background: '#eef4f8', overflow: 'hidden' };
const topologySvgStyle: React.CSSProperties = { cursor: 'grab', touchAction: 'none', userSelect: 'none', display: 'block' };
const topologyViewHintStyle: React.CSSProperties = { margin: '-2px 0 8px 0', color: '#64748b', fontSize: 12 };
const topologyLegendStripStyle: React.CSSProperties = {
  marginBottom: 10,
  padding: '8px 10px',
  border: '1px solid #e5e7eb',
  borderRadius: 8,
  background: '#ffffff',
};
const topologyFullscreenStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 12,
  zIndex: 80,
  display: 'flex',
  flexDirection: 'column',
  padding: 14,
  background: '#ffffff',
  border: '1px solid #dbe3ef',
  borderRadius: 8,
  boxShadow: '0 24px 70px rgba(15,23,42,0.24)',
};
const topologyCanvasFullscreenStyle: React.CSSProperties = {
  ...topologyCanvasStyle,
  flex: 1,
  height: 'auto',
  minHeight: 0,
};
const topologySummaryStyle: React.CSSProperties = {
  position: 'absolute',
  top: 14,
  right: 14,
  zIndex: 2,
  width: 'min(420px, calc(100% - 28px))',
  maxHeight: 'calc(100% - 28px)',
  overflow: 'auto',
  border: '1px solid #e5e7eb',
  borderRadius: 8,
  padding: 14,
  background: 'rgba(255,255,255,0.96)',
  boxShadow: '0 18px 42px rgba(15,23,42,0.16)',
};
const topologySummaryGridStyle: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10 };
const legendStyle: React.CSSProperties = { display: 'flex', gap: '8px 14px', flexWrap: 'wrap', color: '#475569', fontSize: 12 };
const legendSwatchStyle: React.CSSProperties = { display: 'inline-block', width: 12, height: 12, borderRadius: 2, marginRight: 8, verticalAlign: '-1px' };
const btnStyle: React.CSSProperties = { padding: '10px 14px', borderRadius: 8, border: '1px solid #d1d5db', background: '#fff', fontWeight: 600, cursor: 'pointer' };
const taskSelectStyle: React.CSSProperties = { minWidth: 320, maxWidth: '100%', padding: '9px 12px', borderRadius: 8, border: '1px solid #d1d5db', background: '#fff', color: '#111827', fontWeight: 600 };
const smallBtnStyle: React.CSSProperties = { padding: '7px 10px', borderRadius: 8, border: '1px solid #d1d5db', background: '#fff', fontWeight: 600, cursor: 'pointer', fontSize: 12 };
const chipBtnStyle: React.CSSProperties = { padding: '7px 10px', borderRadius: 999, border: '1px solid #d1d5db', background: '#fff', fontWeight: 600, cursor: 'pointer', fontSize: 12, color: '#334155' };
const activeChipBtnStyle: React.CSSProperties = { ...chipBtnStyle, border: '1px solid #93c5fd', background: '#dbeafe', color: '#1d4ed8' };
const warningStyle: React.CSSProperties = { background: '#fffbeb', border: '1px solid #fde68a', color: '#92400e', borderRadius: 8, padding: 14, marginBottom: 16 };
const diagnosticStripStyle: React.CSSProperties = { background: '#eef6ff', border: '1px solid #bfdbfe', color: '#1e3a8a', borderRadius: 8, padding: 12, marginBottom: 16, fontSize: 13 };
const thStyle: React.CSSProperties = { textAlign: 'left', padding: 10, borderBottom: '1px solid #d1d5db', background: '#f9fafb' };
const tdStyle: React.CSSProperties = { padding: 10, borderBottom: '1px solid #e5e7eb', verticalAlign: 'top' };
const resultTableStyle: React.CSSProperties = { width: '100%', borderCollapse: 'collapse', minWidth: 920 };
const resultTableHeadStyle: React.CSSProperties = { textAlign: 'left', padding: 10, borderBottom: '1px solid #d1d5db', background: '#f9fafb', fontSize: 12, color: '#475569', whiteSpace: 'nowrap' };
const resultTableCellStyle: React.CSSProperties = { padding: 10, borderBottom: '1px solid #e5e7eb', verticalAlign: 'top', fontSize: 13 };
const preStyle: React.CSSProperties = { whiteSpace: 'pre-wrap', wordBreak: 'break-word', background: '#f8fafc', padding: 12, border: '1px solid #e5e7eb', borderRadius: 8, maxHeight: 560, overflow: 'auto', overscrollBehavior: 'contain' };
