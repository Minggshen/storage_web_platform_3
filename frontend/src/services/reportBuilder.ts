import type { ReportPayload, ReportFinancial } from '../types/api';
import { SEMANTIC_COLORS } from '@/constants/chartStyles';

// ====================================================================
// formatting helpers
// ====================================================================

function esc(value: unknown): string {
  const text = value === null || value === undefined ? '' : String(value);
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function blank(value: unknown, placeholder = '暂无数据'): string {
  if (value === null || value === undefined) return placeholder;
  if (typeof value === 'string' && value.trim() === '') return placeholder;
  if (typeof value === 'number' && !Number.isFinite(value)) return placeholder;
  return esc(value);
}

function num(value: unknown, decimals = 2): string {
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return '--';
  return n.toLocaleString('zh-CN', { maximumFractionDigits: decimals, minimumFractionDigits: 0 });
}

function money(value: unknown): string {
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return '--';
  const wan = n / 10000;
  return `${wan.toLocaleString('zh-CN', { maximumFractionDigits: 2, minimumFractionDigits: 0 })} 万元`;
}

function pct(decimal: unknown): string {
  const n = typeof decimal === 'number' ? decimal : Number(decimal);
  if (!Number.isFinite(n)) return '--';
  return `${(n * 100).toFixed(2)}%`;
}

function dateLabel(iso: unknown): string {
  if (!iso || typeof iso !== 'string') return '--';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' });
  } catch {
    return String(iso);
  }
}

// ====================================================================
// Chinese label mapping — every English key used in the report maps here
// ====================================================================

const LABEL_MAP: Record<string, string> = {
  // project meta
  project_name: '项目名称',
  description: '项目描述',
  created_at: '创建日期',
  version: '软件版本',
  node_count: '节点总数',
  edge_count: '边（线路）总数',
  load_node_count: '负荷节点数',
  has_tariff: '是否已导入电价',
  tariff_year: '电价年份',

  // task meta
  task_id: '任务编号',
  status: '状态',
  started_at: '开始时间',
  completed_at: '完成时间',
  selected_case: '选用算例',

  // devices
  vendor: '供应商 / 品牌',
  model: '设备型号',
  series_name: '产品系列',
  device_family: '设备类别',
  battery_chemistry: '电化学类型',
  usable_energy_kwh_at_fat: '可用容量（出厂）',
  duration_hour: '额定时长',
  duration_h: '持续放电时间',
  dc_voltage_range_v: '直流电压范围',
  ac_grid_voltage_v: '交流并网电压',
  efficiency_pct: '充放电效率',
  cooling_type: '冷却方式',
  fire_detection: '消防探测',
  fire_suppression: '消防灭火',
  safety_level: '安全等级',
  cycle_life: '循环寿命',
  soc_min: 'SOC 下限',
  soc_max: 'SOC 上限',
  ip_system: '防护等级',
  corrosion_grade: '防腐等级',
  install_mode: '安装方式',
  weight_kg: '重量',
  price_yuan_per_wh: '参考单价',
  energy_unit_price_yuan_per_kwh: '能量单价',
  power_related_capex_yuan_per_kw: '功率相关投资',
  communication_protocol: '通讯协议',
  supports_black_start: '支持黑启动',
  supports_offgrid_microgrid: '支持离网微电网',
  dimension_w_mm: '外形尺寸 (W×D×H)',

  // configuration
  target_id: '目标负荷编号',
  target_bus: '接入母线',
  strategy_id: '策略编号',
  strategy_name: '运行策略',
  capacity_factor: '容量因子',
  background_load_policy: '备电保障策略',

  // operation
  annual_equivalent_full_cycles: '年等效全循环次数',
  annual_battery_throughput_kwh: '年电池吞吐量',
  rated_power_kw: '额定功率',
  rated_energy_kwh: '额定容量',

  // financial — core
  npv_yuan: '净现值 (NPV)',
  irr: '全投资内部收益率 (IRR)',
  simple_payback_years: '静态投资回收期',
  discounted_payback_years: '动态投资回收期',
  initial_investment_yuan: '初始总投资',
  annualized_net_cashflow_yuan: '年均净现金流',
  lcoe_yuan_per_kwh: '平准化度电成本 (LCOE)',
  roi_pct: '投资回报率 (ROI)',

  // financial — revenue
  arbitrage: '峰谷套利收益',
  demand_saving: '需量管理节约',
  capacity: '容量市场收益',
  loss_reduction: '降损收益',
  auxiliary_service: '辅助服务净收益',

  // financial — cost
  degradation: '电池衰减成本',
  o_and_m: '运维费用 (O&M)',
  replacement: '设备更换等效年金',
  transformer_penalty: '变压器越限惩罚',
  voltage_penalty: '电压越限惩罚',

  // financial — ledger
  name: '科目名称',
  category: '类别',
  amount_yuan: '金额',
  quantity: '数量',
  unit_price: '单价',
  anomaly: '异常标记',

  // network impact
  target_area_conclusion: '目标接入区域综合结论',
  attribution_summary: '归因摘要',
  risk_classification: '风险分类统计',
  voltage_top_risks: '电压风险 Top 项',
  line_top_risks: '线路风险 Top 项',
  transformer_top_risks: '变压器风险 Top 项',
  data_quality: '数据质量',
  baseline: '储能接入前',
  with_storage: '储能接入后',
  delta: '变化量',
  total: '总计',
  voltage: '电压',
  line: '线路',
  transformer: '变压器',
  bus: '母线',
  classification: '分类',
  baseline_violation_hours: '基准越限小时',
  with_storage_violation_hours: '储能后越限小时',
  max_violation_pu: '最大越限 (pu)',
  bus1: '母线1',
  bus2: '母线2',
  normamps: '额定电流 (A)',
  baseline_overload_hours: '基准过载小时',
  with_storage_overload_hours: '储能后过载小时',
  max_loading_pct: '最大负载率',
  overload_hour_delta: '过载小时变化',
  max_baseline_loading_pct: '基准最大负载率',
  max_with_storage_loading_pct: '储能后最大负载率',

  // run health
  code: '代码',
  message: '问题描述',
  reason: '原因',
  impact: '影响',
  suggestion: '建议',
  severity: '级别',
  level: '级别',

  // status labels
  passed: '通过',
  warning: '有警告',
  critical: '严重异常',
  failed: '失败',
  completed: '已完成',
  running: '运行中',
  queued: '排队中',
  cancelled: '已取消',
  feasible: '可行',
  infeasible: '不可行',

  // conclusion status
  improved: '改善',
  worsened: '恶化',
  neutral: '基本持平',

  // charts
  month: '月份',
  year: '年份',
  hour: '小时',
  value: '数值',
  unit: '单位',
  revenueWan: '收益（万元）',
  netCashflowWan: '净现金流（万元）',
  npvWan: '净现值（万元）',
  cumulativeDiscountedWan: '累计折现（万元）',
  initialInvestmentWan: '初始投资（万元）',
  paybackYears: '回收期（年）',
  ratedPowerKw: '功率 (kW)',
  ratedEnergyKwh: '容量 (kWh)',
  generation: '代数',
  populationSize: '种群规模',
  feasibleCount: '可行解数',
  archiveSize: '归档大小',
  bestNpvWan: '最优 NPV（万元）',
  total_generations: '总代数',
  final_feasible_count: '最终可行解数',
  final_population_size: '最终种群规模',

  // load profile
  peak_kw: '峰值负荷',
  valley_kw: '谷值负荷',
  annual_mean_kw: '年均负荷',
  mean_daily_energy_kwh: '日均用电量',
  load_factor: '负荷率',
  target_node_name: '目标负荷名称',
  target_node_id: '目标负荷编号',

  // assumptions
  discount_rate: '贴现率',
  project_life_years: '项目寿命',
  opendss_coverage_hours: 'OpenDSS 覆盖小时数',
  opendss_enabled: 'OpenDSS 启用',
  initial_soc: '初始 SOC',
  terminal_soc_mode: '终端 SOC 模式',
  safety_economy_tradeoff: '安全-经济权衡系数',

  // data quality
  missing_data_flags: '缺失数据标记',
  degraded_calculations: '降级计算标记',
  trace_completeness: 'Trace 完整度',

  // source files
  relative_path: '文件路径',
  group: '文件类别',
};

const _CJK_RE = /[一-鿿㐀-䶿豈-﫿]/;

function friendlyNodeName(id: string): string {
  if (!id) return '暂无数据';
  // already has Chinese characters — likely a user-visible name
  if (_CJK_RE.test(id)) return id;
  // n<N>_load → 负荷节点 <N>
  let m = id.match(/^n(\d+)_load$/i);
  if (m) return `负荷节点 ${m[1]}（${id}）`;
  // n<N>_lv... → <N>#配变低压侧
  m = id.match(/^n(\d+)_lv/i);
  if (m) return `${m[1]}#配变低压侧（${id}）`;
  // edge_tx_load_<N> → <N>#配变线路
  m = id.match(/^edge_tx_load_(\d+)$/i);
  if (m) return `${m[1]}#配变线路（${id}）`;
  // edge_<from>_<to> → 线路 <from>-<to>
  m = id.match(/^edge_(.+)_(.+)$/i);
  if (m) return `线路 ${m[1]}-${m[2]}（${id}）`;
  // line_<from>_<to> → 线路 <from>-<to>
  m = id.match(/^line_(.+)_(.+)$/i);
  if (m) return `线路 ${m[1]}-${m[2]}（${id}）`;
  // bus_<N> → 母线 <N>
  m = id.match(/^bus_(\d+)$/i);
  if (m) return `母线 ${m[1]}（${id}）`;
  // load_<N> → 负荷点 <N>
  m = id.match(/^load_(\d+)$/i);
  if (m) return `负荷点 ${m[1]}（${id}）`;
  // tx_... or transformer_... → 变压器 ...
  if (/^(tx_|transformer_|user_tx_)/i.test(id)) return `变压器 ${id}`;
  // branch_* → 分支点
  if (/^branch_/i.test(id)) return `分支点 ${id}`;
  return id;
}

function label(key: string): string {
  const mapped = LABEL_MAP[key];
  if (mapped) return mapped;
  // already Chinese display text — pass through unchanged
  if (_CJK_RE.test(key)) return key;
  return `【${key}】`;
}

function classifyLabel(val: string): string {
  // already Chinese display text — pass through unchanged
  if (_CJK_RE.test(val)) return val;
  const map: Record<string, string> = {
    // risk / status classifications
    existing_background: '现有背景风险',
    storage_induced: '储能引发风险',
    worsened_by_storage: '储能加剧风险',
    improved_by_storage: '储能改善项',
    cleared_by_storage: '储能清除项',
    baseline: '基线风险',
    improved: '改善',
    worsened: '恶化',
    neutral: '基本持平',
    normal: '正常',
    overloaded: '过载',
    undervoltage: '低电压',
    overvoltage: '过电压',
    critical: '严重',
    warning: '警告',
    info: '提示',
    passed: '通过',
    none: '无',
    high: '高',
    medium: '中',
    low: '低',
    // financial ledger categories
    revenue: '收益',
    cost: '成本',
    subsidy: '政府补贴',
    tax: '税金',
    capex: '初始投资',
    opex: '运营支出',
    salvage: '残值',
    energy_capex: '能量部分投资',
    power_capex: '功率部分投资',
    safety_markup: '安全加价',
    integration_markup: '集成加价',
    other_capex: '其他投资',
    // operational values
    auto: '自动计算',
    // source file groups
    monthly_summary: '月度汇总',
    hourly_operation: '年度逐时运行',
    cashflow: '现金流表',
    annual_summary: '年度汇总',
    financial_summary: '财务汇总',
    population_results: '种群结果',
    archive_results: '归档结果',
    optimization_history: '优化历史',
    best_result_summary: '最佳结果摘要',
    configuration_report: '配置方案报告',
    operation_report: '运行报告',
    financial_report: '经济性报告',
    network_impact_report: '电网影响报告',
    run_health_report: '运行健康报告',
    bus_voltage_trace: '母线电压 Trace',
    line_loading_trace: '线路负载 Trace',
    network_loss_trace: '网损 Trace',
    line_capacity: '线路容量',
    // health check codes
    soc_energy_balance_residual_noticeable: 'SOC-能量平衡差异显著',
    npv_below_threshold: 'NPV 低于阈值',
    payback_exceeds_life: '回收期超过项目寿命',
    transformer_overload: '变压器过载',
    voltage_violation: '电压越限',
    line_overload: '线路过载',
    infeasible_solution: '不可行解',
    missing_data: '数据缺失',
  };
  return map[val] || `【${val}】`;
}

// ====================================================================
// CSS
// ====================================================================

const CSS = /* css */ `
  :root {
    --c-primary-900: #0f2340;
    --c-primary-700: #1e3a5f;
    --c-primary-500: #2563eb;
    --c-primary-100: #e8edf5;
    --c-primary-50:  #f5f7fa;
    --c-success: #059669;
    --c-warning: #d97706;
    --c-danger:  #dc2626;
    --c-gray-700: #374151;
    --c-gray-500: #6b7280;
    --c-gray-200: #e5e7eb;
    --c-gray-100: #f3f4f6;
  }
  @page { size: A4; margin: 18mm 16mm; }
  * { box-sizing: border-box; }
  body {
    font-family: "PingFang SC", "Microsoft YaHei", "SimSun", serif;
    font-size: 11pt; line-height: 1.75; color: var(--c-gray-700);
    margin: 0; padding: 0; background: #fff;
  }

  /* ===== Cover ===== */
  .cover {
    display: flex; flex-direction: column; justify-content: center; align-items: center;
    height: 100vh; text-align: center; page-break-after: always;
    background: linear-gradient(160deg, #0a1628 0%, #1e3a5f 40%, #1a3a5c 100%);
    position: relative; overflow: hidden;
  }
  .cover::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; bottom: 0;
    background:
      linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px),
      linear-gradient(0deg, rgba(255,255,255,0.025) 1px, transparent 1px);
    background-size: 60px 60px;
    pointer-events: none;
  }
  .cover h1 { font-size: 28pt; color: #fff; margin: 0 0 12pt; letter-spacing: 6px; font-weight: 700; position: relative; text-shadow: 0 2px 12px rgba(0,0,0,0.3); }
  .cover .subtitle { font-size: 14pt; color: rgba(255,255,255,0.75); margin: 0 0 32pt; font-weight: 300; letter-spacing: 2px; position: relative; }
  .cover .divider { width: 50%; height: 1px; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent); margin: 24pt auto; position: relative; }
  .cover p { font-size: 11pt; color: rgba(255,255,255,0.65); margin: 6pt 0; position: relative; }
  .cover .confidential { margin-top: 40pt; padding: 6px 18px; border: 1px solid rgba(255,255,255,0.3); color: rgba(255,255,255,0.5); font-size: 10pt; display: inline-block; border-radius: 4px; position: relative; }

  main { max-width: 180mm; margin: 0 auto; padding: 0; }

  /* ===== TOC ===== */
  .toc { page-break-after: always; padding: 20pt 0; }
  .toc h2 { font-size: 18pt; color: var(--c-primary-900); text-align: center; border-bottom: none; margin-bottom: 24pt; }
  .toc ol { list-style: none; counter-reset: toc; padding: 0; max-width: 420px; margin: 0 auto; }
  .toc li { counter-increment: toc; padding: 9pt 0; border-bottom: 1px dotted var(--c-gray-200); font-size: 11pt; }
  .toc li::before { content: counter(toc, cjk-ideographic) '、'; color: var(--c-primary-500); font-weight: 600; margin-right: 8pt; }
  .toc .toc-sub { font-size: 10pt; color: var(--c-gray-500); margin-left: 2.5em; }

  /* ===== Section Headings ===== */
  .section { page-break-before: always; margin-bottom: 24pt; }
  .section h2 {
    font-size: 15pt; color: var(--c-primary-900); border-bottom: 2.5px solid var(--c-primary-700);
    padding: 0 0 8pt 14pt; margin: 0 0 16pt 0; letter-spacing: 1px;
    position: relative;
  }
  .section h2::before {
    content: ''; position: absolute; left: 0; top: 2pt; bottom: 2pt;
    width: 3pt; background: var(--c-primary-500); border-radius: 2px;
  }
  .section h3 {
    font-size: 12pt; color: var(--c-primary-700); margin: 16pt 0 8pt;
    padding-left: 8pt; border-left: 3px solid var(--c-primary-500);
  }
  .section h4 { font-size: 11pt; color: var(--c-gray-700); font-weight: 600; margin: 12pt 0 6pt; }
  .section p { margin: 6pt 0; text-indent: 2em; font-size: 10.5pt; line-height: 1.8; }

  /* ===== Cards ===== */
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8pt; margin: 12pt 0; }
  .card {
    background: #fff; border: 1px solid var(--c-gray-200); border-radius: 6px;
    padding: 10pt 14pt; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }
  .card:first-child { border-left: 3px solid var(--c-primary-500); }
  .card .label { font-size: 8pt; color: var(--c-gray-500); letter-spacing: 0.5px; margin-bottom: 4pt; }
  .card .value { font-size: 14pt; font-weight: 700; color: var(--c-primary-900); }

  /* ===== Conclusion Box ===== */
  .conclusion-box { border-radius: 6px; padding: 12pt 16pt; margin: 10pt 0; font-size: 10.5pt; line-height: 1.7; }
  .conclusion-box.improved { background: #ecfdf5; border-left: 4px solid var(--c-success); color: #065f46; }
  .conclusion-box.neutral  { background: #eff6ff; border-left: 4px solid var(--c-primary-500); color: #1e40af; }
  .conclusion-box.worsened { background: #fef2f2; border-left: 4px solid var(--c-danger); color: #991b1b; }

  /* ===== Key-Value Spec Table ===== */
  .spec-table { width: 100%; border-collapse: separate; border-spacing: 0; margin: 8pt 0; border: 1px solid var(--c-gray-200); border-radius: 4px; overflow: hidden; }
  .spec-table th, .spec-table td { border-bottom: 1px solid var(--c-gray-100); padding: 4pt 8pt; text-align: left; font-size: 8.5pt; }
  .spec-table tr:last-child th, .spec-table tr:last-child td { border-bottom: none; }
  .spec-table th { background: var(--c-primary-100); color: var(--c-primary-900); font-weight: 600; width: 35%; }
  .spec-table td { background: #fff; }
  .spec-table tr { break-inside: avoid; page-break-inside: avoid; }

  /* ===== Data Table ===== */
  table { width: 100%; border-collapse: separate; border-spacing: 0; margin: 8pt 0; font-size: 8.5pt; border: 1px solid var(--c-gray-200); border-radius: 4px; overflow: hidden; }
  th { background: var(--c-primary-700); color: #fff; font-weight: 600; font-size: 8pt; letter-spacing: 0.5px; padding: 5pt 6pt; }
  td { padding: 4pt 6pt; border-bottom: 1px solid var(--c-gray-100); }
  td.left { text-align: left; }
  td { text-align: right; }
  tr:last-child td { border-bottom: none; }
  tr:nth-child(even) td { background: var(--c-primary-50); }
  thead { display: table-header-group; }
  tr { break-inside: avoid; page-break-inside: avoid; }

  /* ===== Utility ===== */
  .no-data { color: #9ca3af; font-style: italic; text-indent: 0; }
  .warning-banner { background: #fffbeb; border-left: 4px solid var(--c-warning); padding: 10pt 14pt; border-radius: 4px; margin: 10pt 0; color: #92400e; font-size: 10pt; }
  .note { background: #f0f9ff; border-left: 4px solid var(--c-primary-500); padding: 8pt 12pt; margin: 10pt 0; font-size: 10pt; color: #1e40af; border-radius: 4px; }

  /* ===== Recommendation Card ===== */
  .recommendation-card { border: 2px solid var(--c-primary-700); border-radius: 8px; padding: 16pt 20pt; margin: 14pt 0; background: linear-gradient(135deg, #f8fafc 0%, var(--c-primary-100) 100%); box-shadow: 0 2px 8px rgba(15,35,64,0.08); }
  .recommendation-card h3 { font-size: 13pt; color: var(--c-primary-900); margin: 0 0 10pt; border-left: none; padding-left: 0; }
  .rec-status { display: inline-block; padding: 6px 18px; border-radius: 4px; font-weight: 700; font-size: 12pt; letter-spacing: 1px; text-align: center; }
  .rec-status.recommended { background: #ecfdf5; color: #065f46; border: 1px solid var(--c-success); }
  .rec-status.conditional { background: #fffbeb; color: #92400e; border: 1px solid var(--c-warning); }
  .rec-status.not-recommended { background: #fef2f2; color: #991b1b; border: 1px solid var(--c-danger); }
  .disclaimer-box { border: 1px solid var(--c-gray-200); border-radius: 6px; padding: 12pt 16pt; margin: 10pt 0; background: #f9fafb; color: var(--c-gray-500); font-size: 9.5pt; }

  /* ===== Charts ===== */
  .chart-figure { break-inside: avoid; page-break-inside: avoid; margin: 14pt 0; text-align: center; }
  .report-chart { display: block; width: 100%; height: auto; overflow: visible; max-width: 100%; }

  /* ===== Severity ===== */
  .severity-critical { color: var(--c-danger); font-weight: 700; }
  .severity-warning { color: var(--c-warning); font-weight: 600; }

  /* ===== Print ===== */
  @media print {
    @page { size: A4; margin: 16mm 14mm; }
    body { -webkit-print-color-adjust: exact; print-color-adjust: exact; font-size: 10.5pt; line-height: 1.6; }
    .cover { height: 100vh; }
    .section { page-break-before: always; }
    .section h3, .section h4, .section p, .section ul, .section ol { orphans: 3; widows: 3; }
    .chart-figure { break-inside: avoid; page-break-inside: avoid; }
    tr { break-inside: avoid; page-break-inside: avoid; }
  }
`;

// ====================================================================
// reusable HTML snippets
// ====================================================================

function section(title: string, body: string): string {
  return `<div class="section"><h2>${title}</h2>${body}</div>`;
}

function subSection(title: string, body: string): string {
  return `<h3>${title}</h3>${body}`;
}

function cards(items: [string, string][]): string {
  const html = items.map(([labelText, value]) =>
    `<div class="card"><div class="label">${esc(labelText)}</div><div class="value">${esc(value)}</div></div>`
  ).join('');
  return `<div class="cards">${html}</div>`;
}

function kvTable(rows: [string, unknown][], col1Width = '35%', rawLabels?: boolean): string {
  const body = rows.map(([key, val]) => {
    const displayKey = rawLabels ? key : label(key);
    return `<tr><td style="width:${col1Width};text-align:left;font-weight:600;background:#f9fafb;">${esc(displayKey)}</td><td style="text-align:left;">${blank(val)}</td></tr>`;
  }).join('');
  return `<table class="spec-table">${body}</table>`;
}

function dataTable(columns: string[], rows: string[][], colAligns?: ('left' | 'right')[], rawColIndices?: Set<number>): string {
  const header = `<tr>${columns.map(c => `<th>${esc(label(c))}</th>`).join('')}</tr>`;
  const body = rows.map(row =>
    `<tr>${row.map((cell, i) => {
      const align = colAligns?.[i] === 'left' ? ' class="left"' : '';
      const useRaw = rawColIndices?.has(i);
      const cellHtml = useRaw ? cell : esc(cell);
      return `<td${align}>${cellHtml}</td>`;
    }).join('')}</tr>`
  ).join('');
  return `<table>${header}${body}</table>`;
}

// ====================================================================
// SVG chart generators (self-contained, no external dependencies)
// ====================================================================

type SvgRefLine = { value: number; label?: string; color?: string; dashArray?: string };

function buildReferenceLines(
  refs: SvgRefLine[],
  margin: { left: number; right: number; top: number },
  plotW: number,
  yToSvg: (v: number) => number,
): string {
  return refs.map((r) => {
    const y = yToSvg(r.value);
    const color = r.color || SEMANTIC_COLORS.constraint;
    const dash = r.dashArray ? ` stroke-dasharray="${r.dashArray}"` : '';
    const labelSvg = r.label
      ? `<text x="${margin.left + plotW - 4}" y="${y - 4}" text-anchor="end" font-size="9" fill="${color}">${esc(r.label)}</text>`
      : '';
    return `<line x1="${margin.left}" x2="${margin.left + plotW}" y1="${y}" y2="${y}" stroke="${color}" stroke-width="1"${dash} />${labelSvg}`;
  }).join('');
}

function svgBarChart(
  data: { label: string; value: number }[],
  width = 600,
  height = 350,
  cfg: {
    xLabel?: string; yLabel?: string;
    color?: string; negativeColor?: string;
    valueFormatter?: (v: number) => string;
    referenceLines?: SvgRefLine[];
    caption?: string;
  } = {},
): string {
  const margin = { top: 30, right: 30, bottom: 70, left: 70 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const allVals = data.map(d => d.value);
  const maxVal = Math.max(...allVals, 0) * 1.1 || 1;
  const minVal = Math.min(...allVals, 0);
  const range = maxVal - minVal || 1;
  const barW = Math.max(6, (plotW / data.length) * 0.65);
  const gap = plotW / data.length;
  const color = cfg.color || SEMANTIC_COLORS.optimized;
  const negColor = cfg.negativeColor || SEMANTIC_COLORS.charge;
  const fmt = cfg.valueFormatter || ((v: number) => v.toLocaleString('zh-CN', { maximumFractionDigits: 0 }));
  const zeroY = margin.top + plotH - ((0 - minVal) / range) * plotH;

  const toY = (v: number) => margin.top + plotH - ((v - minVal) / range) * plotH;

  // y-axis grid & ticks
  const yTicks = 5;
  const yStep = range / yTicks;
  const yGrid = Array.from({ length: yTicks + 1 }, (_, i) => {
    const val = minVal + yStep * i;
    const y = toY(val);
    return `<line x1="${margin.left}" x2="${width - margin.right}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}" stroke="${SEMANTIC_COLORS.grid}" stroke-width="0.5" />
      <text x="${margin.left - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="9" fill="${SEMANTIC_COLORS.neutral}">${fmt(val)}</text>`;
  }).join('');

  // zero baseline (always visible when there are negatives)
  const zeroLine = minVal < 0
    ? `<line x1="${margin.left}" x2="${margin.left + plotW}" y1="${zeroY.toFixed(1)}" y2="${zeroY.toFixed(1)}" stroke="${SEMANTIC_COLORS.zeroLine}" stroke-width="1" />`
    : '';

  // bars
  const bars = data.map((d, i) => {
    const x = margin.left + gap * i + (gap - barW) / 2;
    const v = d.value;
    const h = Math.max(0.5, (Math.abs(v) / range) * plotH);
    const isNeg = v < 0;
    const y = isNeg ? zeroY : zeroY - h;
    const barFill = isNeg ? negColor : color;
    const labelY = isNeg ? y + h + 14 : y - 6;
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" fill="${barFill}" rx="2" />
      <text x="${(x + barW / 2).toFixed(1)}" y="${labelY.toFixed(1)}" text-anchor="middle" font-size="9" fill="${SEMANTIC_COLORS.zeroLine}">${fmt(v)}</text>
      <text x="${(x + barW / 2).toFixed(1)}" y="${margin.top + plotH + 16}" text-anchor="end" font-size="9" fill="${SEMANTIC_COLORS.neutral}" transform="rotate(-35, ${(x + barW / 2).toFixed(1)}, ${margin.top + plotH + 16})">${esc(d.label)}</text>`;
  }).join('');

  // reference lines
  const refLines = cfg.referenceLines
    ? buildReferenceLines(cfg.referenceLines, margin, plotW, toY)
    : '';

  const yLabel = cfg.yLabel ? `<text x="${margin.left - 55}" y="${margin.top + plotH / 2}" text-anchor="middle" font-size="10" fill="${SEMANTIC_COLORS.zeroLine}" transform="rotate(-90, ${margin.left - 55}, ${margin.top + plotH / 2})">${esc(cfg.yLabel)}</text>` : '';
  const xLabel = cfg.xLabel ? `<text x="${margin.left + plotW / 2}" y="${height - 6}" text-anchor="middle" font-size="10" fill="${SEMANTIC_COLORS.zeroLine}">${esc(cfg.xLabel)}</text>` : '';
  const caption = cfg.caption ? `<text x="${margin.left + plotW / 2}" y="${height - 2}" text-anchor="middle" font-size="9" fill="${SEMANTIC_COLORS.neutral}">${esc(cfg.caption)}</text>` : '';

  return `<div class="chart-figure"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" class="report-chart" style="font-family:'PingFang SC','Microsoft YaHei',sans-serif;max-width:100%;">
    ${yLabel}${xLabel}${yGrid}${zeroLine}${refLines}${bars}${caption}
  </svg></div>`;
}

function svgLineChart(
  data: { label: string; value: number }[],
  width = 600,
  height = 350,
  cfg: {
    xLabel?: string; yLabel?: string; color?: string;
    series?: { key: string; color: string; label: string; lineStyle?: 'solid' | 'dashed' | 'dashDot' }[];
    multiData?: Record<string, number | string | null | undefined>[];
    referenceLines?: SvgRefLine[];
    caption?: string;
  } = {},
): string {
  const margin = { top: 30, right: 50, bottom: 70, left: 70 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;

  // ── resolve dash arrays ──
  const dashMap: Record<string, string> = { solid: '', dashed: '5,5', dashDot: '8,4,2,4' };

  let allValues: number[] = [];
  if (cfg.multiData && cfg.series) {
    for (const row of cfg.multiData) {
      for (const s of cfg.series) {
        const v = row[s.key];
        if (typeof v === 'number') allValues.push(v);
      }
    }
  } else {
    allValues = data.map(d => d.value);
  }
  const maxVal = Math.max(...allValues, 0) * 1.1 || 1;
  const minVal = Math.min(...allValues, 0);
  const range = maxVal - minVal || 1;

  const toY = (v: number) => margin.top + plotH - ((v - minVal) / range) * plotH;

  const yTicks = 5;
  const yStep = range / yTicks;
  const yGrid = Array.from({ length: yTicks + 1 }, (_, i) => {
    const val = minVal + yStep * i;
    const y = toY(val);
    return `<line x1="${margin.left}" x2="${width - margin.right}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}" stroke="${SEMANTIC_COLORS.grid}" stroke-width="0.5" />
      <text x="${margin.left - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="9" fill="${SEMANTIC_COLORS.neutral}">${num(val, 0)}</text>`;
  }).join('');

  // zero line when data spans negative & positive
  const zeroLine = minVal < 0 && maxVal > 0
    ? `<line x1="${margin.left}" x2="${margin.left + plotW}" y1="${toY(0).toFixed(1)}" y2="${toY(0).toFixed(1)}" stroke="${SEMANTIC_COLORS.zeroLine}" stroke-width="0.8" />`
    : '';

  const buildPath = (values: number[]) => {
    if (values.length === 0) return '';
    return values.map((v, i) => {
      const x = margin.left + (i / Math.max(values.length - 1, 1)) * plotW;
      const y = toY(v);
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
  };

  let paths = '';
  let dots = '';
  let legend = '';

  if (cfg.multiData && cfg.series) {
    const labels = cfg.multiData.map(d => String(d.label ?? ''));
    const xLabels = labels.map((l, i) => {
      const x = margin.left + (i / Math.max(labels.length - 1, 1)) * plotW;
      return `<text x="${x.toFixed(1)}" y="${margin.top + plotH + 16}" text-anchor="end" font-size="9" fill="${SEMANTIC_COLORS.neutral}" transform="rotate(-35, ${x.toFixed(1)}, ${margin.top + plotH + 16})">${esc(l)}</text>`;
    }).join('');
    paths = cfg.series.map(s => {
      const vals = cfg.multiData!.map(d => (typeof d[s.key] === 'number' ? d[s.key] as number : 0));
      const dashStr = dashMap[s.lineStyle || 'solid'];
      const dashAttr = dashStr ? ` stroke-dasharray="${dashStr}"` : '';
      return `<path d="${buildPath(vals)}" fill="none" stroke="${s.color}" stroke-width="2"${dashAttr} />`;
    }).join('');
    legend = cfg.series.map((s, i) =>
      `<rect x="${width - margin.right - 140 + i * 90}" y="6" width="12" height="12" fill="${s.color}" rx="2" />
       <text x="${width - margin.right - 124 + i * 90}" y="16" font-size="9" fill="${SEMANTIC_COLORS.zeroLine}">${esc(s.label)}</text>`
    ).join('');
    dots = xLabels;
  } else {
    const dashStr = dashMap.solid;
    paths = `<path d="${buildPath(data.map(d => d.value))}" fill="none" stroke="${cfg.color || SEMANTIC_COLORS.revenue.primary}" stroke-width="2"${dashStr ? ` stroke-dasharray="${dashStr}"` : ''} />`;
    // dots at each data point
    dots = data.map((_, i) => {
      const x = margin.left + (i / Math.max(data.length - 1, 1)) * plotW;
      const y = toY(data[i].value);
      return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3" fill="${cfg.color || SEMANTIC_COLORS.revenue.primary}" />`;
    }).join('');
    dots += data.map((d, i) => {
      const x = margin.left + (i / Math.max(data.length - 1, 1)) * plotW;
      return `<text x="${x.toFixed(1)}" y="${margin.top + plotH + 16}" text-anchor="end" font-size="9" fill="${SEMANTIC_COLORS.neutral}" transform="rotate(-35, ${x.toFixed(1)}, ${margin.top + plotH + 16})">${esc(d.label)}</text>`;
    }).join('');
  }

  // reference lines
  const refLines = cfg.referenceLines
    ? buildReferenceLines(cfg.referenceLines, margin, plotW, toY)
    : '';

  const yLabel = cfg.yLabel ? `<text x="${margin.left - 55}" y="${margin.top + plotH / 2}" text-anchor="middle" font-size="10" fill="${SEMANTIC_COLORS.zeroLine}" transform="rotate(-90, ${margin.left - 55}, ${margin.top + plotH / 2})">${esc(cfg.yLabel)}</text>` : '';
  const caption = cfg.caption ? `<text x="${margin.left + plotW / 2}" y="${height - 2}" text-anchor="middle" font-size="9" fill="${SEMANTIC_COLORS.neutral}">${esc(cfg.caption)}</text>` : '';

  return `<div class="chart-figure"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" class="report-chart" style="font-family:'PingFang SC','Microsoft YaHei',sans-serif;max-width:100%;">
    ${yLabel}${yGrid}${zeroLine}${refLines}${legend}${paths}${dots}${caption}
  </svg></div>`;
}

function svgStackedBarChart(
  data: { label: string; segments: { key: string; value: number; color: string }[] }[],
  width = 600,
  height = 380,
  cfg: { xLabel?: string; yLabel?: string; referenceLines?: SvgRefLine[]; caption?: string } = {},
): string {
  const margin = { top: 30, right: 30, bottom: 80, left: 70 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;

  // signed domain: positive totals → maxPos, negative totals → maxNeg (abs)
  const posTotals = data.map(d => d.segments.filter(s => s.value >= 0).reduce((sum, s) => sum + s.value, 0));
  const negTotals = data.map(d => d.segments.filter(s => s.value < 0).reduce((sum, s) => sum + Math.abs(s.value), 0));
  const maxPos = Math.max(...posTotals, 1) * 1.15;
  const maxNeg = Math.max(...negTotals, 1) * 1.15;
  const range = maxPos + maxNeg; // full signed range
  const barW = Math.max(8, (plotW / data.length) * 0.6);
  const gap = plotW / data.length;

  // zero Y: proportion of negative range from the bottom
  const zeroY = margin.top + plotH - (maxNeg / range) * plotH;

  const toY = (v: number) => {
    // v is positive-only; maps to absolute pixel distance from zero
    return (v / range) * plotH;
  };

  // y-axis ticks (signed: -maxNeg … 0 … +maxPos)
  const yTicks = 6;
  const yStep = range / (yTicks - 1);
  const yGrid = Array.from({ length: yTicks }, (_, i) => {
    const val = -maxNeg + yStep * i;
    const y = zeroY - (val / range) * plotH;
    return `<line x1="${margin.left}" x2="${width - margin.right}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}" stroke="${SEMANTIC_COLORS.grid}" stroke-width="0.5" />
      <text x="${margin.left - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="9" fill="${SEMANTIC_COLORS.neutral}">${num(val, 0)}</text>`;
  }).join('');

  // zero baseline
  const zeroLine = negTotals.some(n => n > 0)
    ? `<line x1="${margin.left}" x2="${margin.left + plotW}" y1="${zeroY.toFixed(1)}" y2="${zeroY.toFixed(1)}" stroke="${SEMANTIC_COLORS.zeroLine}" stroke-width="1" />`
    : '';

  const bars = data.map((d, i) => {
    const x = margin.left + gap * i + (gap - barW) / 2;
    let html = '';
    // positive segments — stack upward from zeroY
    let posCumPx = 0;
    for (const seg of d.segments.filter(s => s.value >= 0)) {
      const h = Math.max(0.5, toY(seg.value));
      const y = zeroY - posCumPx - h;
      html += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" fill="${seg.color}" />`;
      posCumPx += h;
    }
    // negative segments — stack downward from zeroY
    let negCumPx = 0;
    for (const seg of d.segments.filter(s => s.value < 0)) {
      const h = Math.max(0.5, toY(Math.abs(seg.value)));
      const y = zeroY + negCumPx;
      html += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" fill="${seg.color}" />`;
      negCumPx += h;
    }
    const netTotal = posTotals[i] - negTotals[i];
    // label position: above positive stack if it's taller, below negative stack otherwise
    const labelY = posCumPx >= negCumPx ? zeroY - posCumPx - 6 : zeroY + negCumPx + 14;
    html += `<text x="${(x + barW / 2).toFixed(1)}" y="${labelY.toFixed(1)}" text-anchor="middle" font-size="8" fill="${SEMANTIC_COLORS.zeroLine}">${num(netTotal, 0)}</text>`;
    html += `<text x="${(x + barW / 2).toFixed(1)}" y="${margin.top + plotH + 16}" text-anchor="end" font-size="9" fill="${SEMANTIC_COLORS.neutral}" transform="rotate(-35, ${(x + barW / 2).toFixed(1)}, ${margin.top + plotH + 16})">${esc(d.label)}</text>`;
    return html;
  }).join('');

  // reference lines use signed toY
  const signedToY = (v: number) => zeroY - (v / range) * plotH;
  const refLines = cfg.referenceLines
    ? buildReferenceLines(cfg.referenceLines, margin, plotW, signedToY)
    : '';

  const yLabel = cfg.yLabel ? `<text x="${margin.left - 55}" y="${margin.top + plotH / 2}" text-anchor="middle" font-size="10" fill="${SEMANTIC_COLORS.zeroLine}" transform="rotate(-90, ${margin.left - 55}, ${margin.top + plotH / 2})">${esc(cfg.yLabel)}</text>` : '';
  const caption = cfg.caption ? `<text x="${margin.left + plotW / 2}" y="${height - 2}" text-anchor="middle" font-size="9" fill="${SEMANTIC_COLORS.neutral}">${esc(cfg.caption)}</text>` : '';

  // legend — multi-row, wrap within plot width
  const legendItemW = 110;
  const legendCols = Math.max(1, Math.floor(plotW / legendItemW));
  const allKeys = data[0]?.segments || [];
  const legend = allKeys.map((seg, i) => {
    const col = i % legendCols;
    const row = Math.floor(i / legendCols);
    const lx = margin.left + col * legendItemW;
    const ly = height - 12 - row * 16;
    return `<rect x="${lx}" y="${ly}" width="10" height="10" fill="${seg.color}" rx="2" />
     <text x="${lx + 14}" y="${ly + 10}" font-size="9" fill="${SEMANTIC_COLORS.zeroLine}">${esc(seg.key)}</text>`;
  }).join('');

  return `<div class="chart-figure"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" class="report-chart" style="font-family:'PingFang SC','Microsoft YaHei',sans-serif;max-width:100%;">
    ${yLabel}${yGrid}${zeroLine}${refLines}${bars}${legend}${caption}
  </svg></div>`;
}

function svgScatterChart(
  data: { x: number; y: number; label?: string; feasible?: boolean; recommended?: boolean }[],
  width = 600,
  height = 400,
  cfg: {
    xLabel: string; yLabel: string;
    referenceLines?: SvgRefLine[];
    frontierData?: { x: number; y: number }[];
    caption?: string;
  },
): string {
  const margin = { top: 30, right: 30, bottom: 70, left: 70 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;

  const xs = data.map(d => d.x);
  const ys = data.map(d => d.y);
  const xMin = Math.min(...xs, 0);
  const xMax = Math.max(...xs, 1) * 1.1;
  const yMin = Math.min(...ys, 0);
  const yMax = Math.max(...ys, 1) * 1.1;

  const toX = (v: number) => margin.left + ((v - xMin) / (xMax - xMin || 1)) * plotW;
  const toY = (v: number) => margin.top + plotH - ((v - yMin) / (yMax - yMin || 1)) * plotH;

  // y-axis ticks and grid
  const yTicks = 5;
  const yStep = (yMax - yMin) / yTicks || 1;
  const yAxis = Array.from({ length: yTicks + 1 }, (_, i) => {
    const val = yMin + yStep * i;
    const y = toY(val);
    return `<line x1="${margin.left}" x2="${width - margin.right}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}" stroke="${SEMANTIC_COLORS.grid}" stroke-width="0.5" />
      <text x="${margin.left - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="9" fill="${SEMANTIC_COLORS.neutral}">${num(val, 0)}</text>`;
  }).join('');

  // x-axis ticks and grid
  const xTicks = 5;
  const xStep = (xMax - xMin) / xTicks || 1;
  const xAxis = Array.from({ length: xTicks + 1 }, (_, i) => {
    const val = xMin + xStep * i;
    const x = toX(val);
    return `<line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${margin.top}" y2="${margin.top + plotH}" stroke="${SEMANTIC_COLORS.grid}" stroke-width="0.5" />
      <text x="${x.toFixed(1)}" y="${margin.top + plotH + 16}" text-anchor="middle" font-size="9" fill="${SEMANTIC_COLORS.neutral}">${num(val, 0)}</text>`;
  }).join('');

  // axis lines
  const axisLines = `<line x1="${margin.left}" x2="${margin.left}" y1="${margin.top}" y2="${margin.top + plotH}" stroke="${SEMANTIC_COLORS.zeroLine}" stroke-width="1" />
    <line x1="${margin.left}" x2="${margin.left + plotW}" y1="${margin.top + plotH}" y2="${margin.top + plotH}" stroke="${SEMANTIC_COLORS.zeroLine}" stroke-width="1" />`;

  // reference lines
  const refLines = cfg.referenceLines
    ? buildReferenceLines(cfg.referenceLines, margin, plotW, toY)
    : '';
  const frontierLine = cfg.frontierData && cfg.frontierData.length >= 2
    ? `<path d="${cfg.frontierData.map((d, i) => `${i === 0 ? 'M' : 'L'}${toX(d.x).toFixed(1)},${toY(d.y).toFixed(1)}`).join(' ')}" fill="none" stroke="${SEMANTIC_COLORS.recommended}" stroke-width="2" stroke-dasharray="8,4,2,4" />`
    : '';

  const dots = data.map(d => {
    const cx = toX(d.x);
    const cy = toY(d.y);
    const r = d.recommended ? 8 : 5;
    const fill = d.recommended ? SEMANTIC_COLORS.recommended : d.feasible ? SEMANTIC_COLORS.feasible : SEMANTIC_COLORS.infeasible;
    const stroke = d.recommended ? SEMANTIC_COLORS.constraint : 'none';
    const labelSvg = d.label ? `<text x="${cx.toFixed(1)}" y="${(cy - 10).toFixed(1)}" text-anchor="middle" font-size="8" fill="${SEMANTIC_COLORS.zeroLine}">${esc(d.label)}</text>` : '';
    return `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${d.recommended ? 2 : 0}" opacity="0.8" />${labelSvg}`;
  }).join('');

  const xLabel = cfg.xLabel ? `<text x="${margin.left + plotW / 2}" y="${height - 6}" text-anchor="middle" font-size="10" fill="${SEMANTIC_COLORS.zeroLine}">${esc(cfg.xLabel)}</text>` : '';
  const yLabel = cfg.yLabel ? `<text x="${margin.left - 55}" y="${margin.top + plotH / 2}" text-anchor="middle" font-size="10" fill="${SEMANTIC_COLORS.zeroLine}" transform="rotate(-90, ${margin.left - 55}, ${margin.top + plotH / 2})">${esc(cfg.yLabel)}</text>` : '';
  const caption = cfg.caption ? `<text x="${margin.left + plotW / 2}" y="${height - 2}" text-anchor="middle" font-size="9" fill="${SEMANTIC_COLORS.neutral}">${esc(cfg.caption)}</text>` : '';

  // legend
  const legend = `<rect x="${width - 180}" y="8" width="10" height="10" fill="${SEMANTIC_COLORS.feasible}" rx="2" opacity="0.8" />
    <text x="${width - 166}" y="18" font-size="9" fill="${SEMANTIC_COLORS.zeroLine}">可行方案</text>
    <rect x="${width - 100}" y="8" width="10" height="10" fill="${SEMANTIC_COLORS.infeasible}" rx="2" opacity="0.8" />
    <text x="${width - 86}" y="18" font-size="9" fill="${SEMANTIC_COLORS.zeroLine}">不可行</text>`;

  return `<div class="chart-figure"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" class="report-chart" style="font-family:'PingFang SC','Microsoft YaHei',sans-serif;max-width:100%;">
    ${yLabel}${xLabel}${yAxis}${xAxis}${axisLines}${refLines}${frontierLine}${dots}${legend}${caption}
  </svg></div>`;
}

function svgDualAxisChart(
  data: { label: string; leftValue: number; rightValue: number }[],
  width = 600,
  height = 350,
  cfg: {
    leftLabel: string; rightLabel: string;
    leftColor?: string; rightColor?: string;
    leftReferenceLines?: SvgRefLine[];
    rightReferenceLines?: SvgRefLine[];
    caption?: string;
  },
): string {
  const margin = { top: 30, right: 60, bottom: 55, left: 60 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;

  const leftMax = Math.max(...data.map(d => d.leftValue), 0) * 1.15 || 1;
  const leftMin = Math.min(...data.map(d => d.leftValue), 0);
  const leftRange = (leftMax - leftMin) || 1;

  const rightMax = Math.max(...data.map(d => d.rightValue), 0) * 1.15 || 1;
  const rightMin = Math.min(...data.map(d => d.rightValue), 0);
  const rightRange = (rightMax - rightMin) || 1;

  const leftColor = cfg.leftColor || SEMANTIC_COLORS.revenue.primary;
  const rightColor = cfg.rightColor || SEMANTIC_COLORS.feasible;

  const toLeftY = (v: number) => margin.top + plotH - ((v - leftMin) / leftRange) * plotH;
  const toRightY = (v: number) => margin.top + plotH - ((v - rightMin) / rightRange) * plotH;

  // left axis ticks
  const leftTicks = Array.from({ length: 5 }, (_, i) => {
    const val = leftMin + (leftRange / 4) * i;
    const y = toLeftY(val);
    return `<text x="${margin.left - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="9" fill="${leftColor}">${num(val, 0)}</text>`;
  }).join('');

  // right axis ticks
  const rightTicks = Array.from({ length: 5 }, (_, i) => {
    const val = rightMin + (rightRange / 4) * i;
    const y = toRightY(val);
    return `<text x="${width - margin.right + 8}" y="${(y + 4).toFixed(1)}" text-anchor="start" font-size="9" fill="${rightColor}">${num(val, 0)}</text>`;
  }).join('');

  // left line
  const leftPath = data.map((d, i) => {
    const x = margin.left + (i / Math.max(data.length - 1, 1)) * plotW;
    const y = toLeftY(d.leftValue);
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');

  // right bars — zero baseline
  const zeroY = toRightY(0);
  const barW = Math.max(6, (plotW / data.length) * 0.7);
  const gap = plotW / data.length;
  const bars = data.map((d, i) => {
    const x = margin.left + gap * i + (gap - barW) / 2;
    const barH = Math.max(0.5, Math.abs((d.rightValue - 0) / rightRange) * plotH);
    const barTop = d.rightValue >= 0 ? zeroY - barH : zeroY;
    const fill = d.rightValue >= 0 ? rightColor : SEMANTIC_COLORS.charge;
    return `<rect x="${x.toFixed(1)}" y="${barTop.toFixed(1)}" width="${barW.toFixed(1)}" height="${barH.toFixed(1)}" fill="${fill}" opacity="0.6" rx="1" />`;
  }).join('');

  // x labels (thinned for large datasets)
  const step = Math.max(1, Math.ceil(data.length / 12));
  const xLabels = data.filter((_, i) => i % step === 0).map(d => {
    const i = data.indexOf(d);
    const x = margin.left + (i / Math.max(data.length - 1, 1)) * plotW;
    return `<text x="${x.toFixed(1)}" y="${margin.top + plotH + 14}" text-anchor="middle" font-size="9" fill="${SEMANTIC_COLORS.neutral}">${esc(d.label)}</text>`;
  }).join('');

  // axis labels
  const leftLabel = `<text x="${margin.left - 48}" y="${margin.top + plotH / 2}" text-anchor="middle" font-size="10" fill="${leftColor}" transform="rotate(-90, ${margin.left - 48}, ${margin.top + plotH / 2})">${esc(cfg.leftLabel)}</text>`;
  const rightLabel = `<text x="${width - margin.right + 48}" y="${margin.top + plotH / 2}" text-anchor="middle" font-size="10" fill="${rightColor}" transform="rotate(90, ${width - margin.right + 48}, ${margin.top + plotH / 2})">${esc(cfg.rightLabel)}</text>`;

  // reference lines (left axis)
  const leftRefLines = cfg.leftReferenceLines
    ? buildReferenceLines(cfg.leftReferenceLines, margin, plotW, toLeftY)
    : '';
  const rightRefLines = cfg.rightReferenceLines
    ? buildReferenceLines(cfg.rightReferenceLines, margin, plotW, toRightY)
    : '';

  // legend
  const legend = `<line x1="${margin.left}" y1="12" x2="${margin.left + 24}" y2="12" stroke="${leftColor}" stroke-width="2" />
    <text x="${margin.left + 28}" y="16" font-size="9" fill="${SEMANTIC_COLORS.zeroLine}">${esc(cfg.leftLabel)}</text>
    <rect x="${margin.left + 120}" y="6" width="12" height="12" fill="${rightColor}" opacity="0.6" rx="1" />
    <text x="${margin.left + 136}" y="16" font-size="9" fill="${SEMANTIC_COLORS.zeroLine}">放电 (正)</text>
    <rect x="${margin.left + 210}" y="6" width="12" height="12" fill="${SEMANTIC_COLORS.charge}" opacity="0.6" rx="1" />
    <text x="${margin.left + 226}" y="16" font-size="9" fill="${SEMANTIC_COLORS.zeroLine}">充电 (负)</text>`;

  const caption = cfg.caption ? `<text x="${margin.left + plotW / 2}" y="${height - 2}" text-anchor="middle" font-size="9" fill="${SEMANTIC_COLORS.neutral}">${esc(cfg.caption)}</text>` : '';

  return `<div class="chart-figure"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" class="report-chart" style="font-family:'PingFang SC','Microsoft YaHei',sans-serif;max-width:100%;">
    ${leftLabel}${rightLabel}${leftTicks}${rightTicks}${leftRefLines}${rightRefLines}${xLabels}${legend}<path d="${leftPath}" fill="none" stroke="${leftColor}" stroke-width="2" />${bars}${caption}
  </svg></div>`;
}

// ====================================================================
// shared helpers
// ====================================================================

function countRiskItems(ni: ReportPayload['network_impact']): { improved: number; worsened: number } {
  const risks = Array.isArray(ni?.risk_classification) ? ni.risk_classification : [];
  let improved = 0;
  let worsened = 0;
  for (const r of risks) {
    const cls = String((r as Record<string, unknown>).classification ?? '');
    const total = Number((r as Record<string, unknown>).total) || 0;
    if (cls === 'improved_by_storage' || cls === 'cleared_by_storage') improved += total;
    if (cls === 'worsened_by_storage' || cls === 'storage_induced') worsened += total;
  }
  return { improved, worsened };
}

// ====================================================================
// section builders
// ====================================================================

function buildCover(payload: ReportPayload): string {
  const meta = payload.project_meta;
  return `<div class="cover">
    <h1>储能系统技术经济评价报告</h1>
    <p class="subtitle">工商业储能项目配置方案 · 技术经济评价</p>
    <div class="divider"></div>
    <p><strong>项目名称：</strong>${esc(meta.project_name || '未命名项目')}</p>
    <p><strong>编制日期：</strong>${dateLabel(payload.generated_at)}</p>
    <p><strong>文档版本：</strong>v${esc(meta.version || '2.1.0')}</p>
    <p class="confidential">内部资料 · 注意保密</p>
  </div>`;
}

function buildToc(): string {
  const items = [
    '执行摘要',
    '一、项目概况与需求分析',
    '二、技术方案设计',
    '三、控制策略',
    '四、全生命周期经济性分析',
    '五、安全与电网影响分析',
    '六、项目实施与运维',
    '七、风险管控与应急预案',
    '附件',
  ];
  const list = items.map((item) => `<li>${esc(item)}</li>`).join('');
  return `<div class="toc"><h2>目  录</h2><ol>${list}</ol></div>`;
}

function buildExecutiveSummary(payload: ReportPayload): string {
  const cfg = payload.configuration;
  const fin = payload.financial?.core;
  const ni = payload.network_impact;
  const rh = payload.run_health;

  let description = payload.project_meta.description;
  if (!description || !description.trim()) {
    description = '本项目通过部署电池储能系统，利用峰谷电价差进行削峰填谷，降低用电成本，同时提供需量管理与电网支持服务。';
  }

  const metricCards: [string, string][] = [];
  if (fin?.irr != null) metricCards.push(['全投资 IRR', pct(fin.irr)]);
  if (fin?.simple_payback_years != null) metricCards.push(['投资回收期', `${num(fin.simple_payback_years, 1)} 年`]);
  if (cfg?.rated_power_kw != null) metricCards.push(['储能功率', `${num(cfg.rated_power_kw, 0)} kW`]);
  if (cfg?.rated_energy_kwh != null) metricCards.push(['储能容量', `${num(cfg.rated_energy_kwh, 0)} kWh`]);
  if (fin?.npv_yuan != null) metricCards.push(['NPV', money(fin.npv_yuan)]);
  if (fin?.annualized_net_cashflow_yuan != null) metricCards.push(['年均净现金流', money(fin.annualized_net_cashflow_yuan)]);
  if (rh?.status) {
    const healthLabel = rh.status === 'passed' ? '✓ 通过' : rh.status === 'warning' ? '⚠ 有警告' : '✗ 严重异常';
    metricCards.push(['健康检查', healthLabel]);
  }
  if (!metricCards.length) {
    metricCards.push(['提示', '暂无求解数据，请运行求解后更新报告']);
  }

  // feasibility status from solver diagnostics
  const feasibility = payload.charts?.feasibility_diagnostics?.summary as Record<string, unknown> | null | undefined;
  const feasibilityStatus = feasibility?.status ? String(feasibility.status) : '';
  const feasibilityFeasible = feasibilityStatus === 'feasible';
  const feasibilityInfeasible = feasibilityStatus === 'infeasible';

  const { improved, worsened } = countRiskItems(ni);
  const gridStatus = improved > worsened ? 'improved' : worsened > improved ? 'worsened' : 'neutral';

  // derive recommendation level
  let recLevel: 'recommended' | 'conditional' | 'not-recommended' = 'conditional';
  let recLabel = '有条件推荐';
  if (feasibilityInfeasible) {
    recLevel = 'not-recommended';
    recLabel = '暂不推荐';
  } else if (feasibilityFeasible && (fin?.npv_yuan ?? 0) > 0 && gridStatus === 'improved') {
    recLevel = 'recommended';
    recLabel = '推荐实施';
  }

  // build recommendation card
  const recRows: [string, string][] = [];
  if (cfg?.rated_power_kw != null && cfg?.rated_energy_kwh != null) {
    recRows.push(['推荐配置', `${num(cfg.rated_power_kw, 0)} kW / ${num(cfg.rated_energy_kwh, 0)} kWh / ${num(cfg.duration_h, 1)} h`]);
  }
  if (fin?.initial_investment_yuan != null) recRows.push(['总投资', money(fin.initial_investment_yuan)]);
  if (fin?.npv_yuan != null) recRows.push(['净现值 (NPV)', money(fin.npv_yuan)]);
  if (fin?.irr != null) recRows.push(['全投资 IRR', pct(fin.irr)]);
  if (fin?.simple_payback_years != null) recRows.push(['投资回收期', `${num(fin.simple_payback_years, 1)} 年`]);

  // annual revenue estimate from revenue breakdown or cashflow
  const rev = fin?.revenue_breakdown;
  const totalAnnualRevenue = (rev?.arbitrage ?? 0) + (rev?.demand_saving ?? 0) + (rev?.capacity ?? 0) + (rev?.loss_reduction ?? 0) + (rev?.auxiliary_service ?? 0);
  if (totalAnnualRevenue > 0) recRows.push(['年化总收益（估算）', money(totalAnnualRevenue)]);

  // main risks
  const criticalIssues = (rh?.issues || []).filter(i => i.level === 'critical');
  if (criticalIssues.length > 0) {
    const riskText = criticalIssues.slice(0, 3).map(i => classifyLabel(i.code || '')).join('、');
    recRows.push(['主要风险', riskText || '详见第七章风险矩阵']);
  } else if (worsened > 0) {
    recRows.push(['主要风险', `电网影响分析识别出 ${worsened} 项安全指标恶化，需复核（详见第五章）`]);
  } else {
    recRows.push(['主要风险', '暂未识别严重风险项']);
  }

  // prerequisites
  const prerequisites: string[] = [];
  if (!payload.assumptions?.opendss_enabled) {
    prerequisites.push('建议启用 OpenDSS 配电网安全校核后重新求解验证');
  }
  if (worsened > 0) {
    prerequisites.push(`需对 ${worsened} 项恶化指标对应的线路/变压器进行现场复核或改造`);
  }
  prerequisites.push('实施前需完成现场踏勘与接入方案电网公司批复');
  recRows.push(['实施前置条件', prerequisites.join('；') || '完成现场踏勘与接入方案批复']);

  const recCard = `<div class="recommendation-card">
    <h3>结论</h3>
    <div style="margin:6pt 0;"><span class="rec-status ${recLevel}">${esc(recLabel)}</span></div>
    ${kvTable(recRows, '30%', true)}
  </div>`;

  // conclusion text
  let recommendation = '基于上述分析，建议按推荐方案配置储能系统。';
  let conclusionClass = '';
  if (feasibilityInfeasible) {
    recommendation = '当前推荐方案未通过可行性校验，建议检查输入数据与约束条件，调整搜索空间后重新求解。项目不建议按当前方案实施。';
    conclusionClass = 'worsened';
  } else if (worsened === 0 && improved > 0) {
    recommendation = '储能接入后目标区域电网安全指标整体改善，未新增系统性风险。推荐按本方案实施，建议在项目实施前完成现场踏勘与详细接入设计。';
    conclusionClass = 'improved';
  } else if (worsened > 0 && improved >= worsened) {
    recommendation = `储能接入后电网部分指标改善（${improved} 项），但存在 ${worsened} 项局部风险需关注。建议在实施前对恶化项进行现场复核，并经电网公司接入审批。`;
    conclusionClass = 'neutral';
  } else if (worsened > improved) {
    recommendation = `储能接入后存在 ${worsened} 项安全指标恶化（改善 ${improved} 项），建议在实施前对配电网进行针对性改造或调整储能运行策略，并经电网公司接入审批。`;
    conclusionClass = 'worsened';
  }

  return `<div class="section">
    <h2>执行摘要</h2>
    <p>${esc(description)}</p>
    ${cards(metricCards)}
    ${recCard}
    <div class="conclusion-box ${conclusionClass}"><strong>综合建议：</strong>${esc(recommendation)}</div>
  </div>`;
}

function buildProjectOverview(payload: ReportPayload): string {
  const meta = payload.project_meta;
  const lp = payload.load_profile;
  const task = payload.task_meta;

  let loadSection = '';
  if (lp?.peak_kw != null || lp?.valley_kw != null) {
    const loadRows: [string, unknown][] = [
      ['目标负荷名称', lp.target_node_name],
      ['目标负荷编号', lp.target_node_id],
      ['峰值负荷', lp.peak_kw != null ? `${num(lp.peak_kw, 0)} kW` : null],
      ['谷值负荷', lp.valley_kw != null ? `${num(lp.valley_kw, 0)} kW` : null],
      ['年均负荷', lp.annual_mean_kw != null ? `${num(lp.annual_mean_kw, 0)} kW` : null],
      ['日均用电量', lp.mean_daily_energy_kwh != null ? `${num(lp.mean_daily_energy_kwh, 0)} kWh` : null],
      ['负荷率', lp.load_factor != null ? pct(lp.load_factor) : null],
    ];
    let loadNote = '';
    if (lp.load_factor != null && lp.load_factor < 0.5) {
      loadNote = '<p class="note">负荷率较低（<' + pct(0.5) + '），日间峰谷差较大，储能削峰填谷空间充足。</p>';
    } else if (lp.load_factor != null && lp.load_factor >= 0.7) {
      loadNote = '<p class="note">负荷率较高，日间峰谷差相对较小，储能套利空间可能受限，建议结合需量管理优化策略。</p>';
    }
    loadSection = subSection('1.4 负荷特性分析',
      kvTable(loadRows) +
      loadNote +
      '<p class="note">数据来源：负荷推算引擎（基于项目绑定的年负荷数据），覆盖最近 365 天逐时数据。负荷指标用于储能容量优化及运行策略生成。</p>'
    );
  } else {
    // show node identity even without metrics
    const nodeInfoRows: [string, unknown][] = [];
    if (lp?.target_node_name) nodeInfoRows.push(['目标负荷名称', lp.target_node_name]);
    if (lp?.target_node_id) nodeInfoRows.push(['目标负荷编号', lp.target_node_id]);
    if (nodeInfoRows.length > 0) {
      loadSection = subSection('1.4 负荷特性分析',
        kvTable(nodeInfoRows) +
        '<div class="note"><strong>负荷画像缺失说明：</strong>未能提取峰值/谷值/年均负荷等统计指标（可能原因：负荷数据覆盖不足或建模未完成）。<strong>这不影响本次基于求解结果的方案摘要</strong>——后续章节的目标接入点、设备配置、收益测算及电网影响分析均已基于求解器输出完成。如需完整的负荷特性分析，请确认已在资产配置页面上传完整的年负荷数据（≥8760 小时）并重新建模与求解。</div>'
      );
    } else {
      loadSection = subSection('1.4 负荷特性分析',
        '<div class="warning-banner"><strong>未绑定负荷数据：</strong>请在资产配置页面上传负荷数据文件，绑定目标负荷节点，并完成建模与求解后更新报告。未绑定负荷将导致经济性分析缺少负荷侧依据。</div>'
      );
    }
  }

  let tariffSection = '';
  if (meta.has_tariff) {
    tariffSection = subSection('1.5 分时电价信息', kvTable([
      ['电价年份', meta.tariff_year ?? '--'],
      ['电价结构', '分时电价（峰/平/谷）'],
    ]) + `<p class="note">详细电价曲线请参见求解结果中的代表日运行数据。</p>`);
  } else {
    tariffSection = subSection('1.5 分时电价信息',
      `<p class="no-data">未导入分时电价数据。请在拓扑建模页面导入电价文件以生成本节内容。</p>`
    );
  }

  let taskInfo = '';
  if (task?.task_id) {
    taskInfo = subSection('1.6 求解任务信息', kvTable([
      ['任务编号', task.task_id],
      ['任务状态', task.status ? label(String(task.status)) : '--'],
      ['完成时间', task.completed_at ? dateLabel(task.completed_at) : '--'],
      ['选用算例', task.selected_case ? friendlyNodeName(String(task.selected_case)) : null],
    ]));
  }

  return section('一、项目概况与需求分析',
    subSection('1.1 项目基本信息', kvTable([
      ['项目名称', meta.project_name],
      ['项目描述', meta.description || '--'],
      ['创建日期', meta.created_at ? dateLabel(meta.created_at) : '--'],
      ['软件版本', meta.version],
    ])) +
    subSection('1.2 配电网规模', kvTable([
      ['节点总数', meta.node_count],
      ['边（线路）总数', meta.edge_count],
      ['负荷节点数', meta.load_node_count],
    ])) +
    subSection('1.3 电价概况', kvTable([
      ['是否已导入电价', meta.has_tariff ? '是' : '否'],
      ['电价年份', meta.tariff_year ?? '--'],
    ])) +
    loadSection +
    tariffSection +
    taskInfo
  );
}

function buildTechnicalSolution(payload: ReportPayload): string {
  const cfg = payload.configuration;
  const fin = payload.financial;
  const devices = payload.devices;

  // system architecture description
  const accessPoint = friendlyNodeName(cfg?.target_bus || cfg?.target_id || '指定母线');
  const archText = cfg
    ? `本项目拟在<strong>${esc(accessPoint)}</strong>接入储能系统，配置额定功率 <strong>${num(cfg.rated_power_kw, 0)} kW</strong>、额定容量 <strong>${num(cfg.rated_energy_kwh, 0)} kWh</strong>，持续放电时间约 <strong>${num(cfg.duration_h, 1)} 小时</strong>。系统通过储能变流器（PCS）实现交直流变换，由能量管理系统（EMS）进行智能调度，采用${cfg.strategy_name ? esc(cfg.strategy_name) + '策略' : '峰谷套利+需量管理综合策略'}运行。`
    : `<p class="no-data">暂无储能配置数据。请先完成求解以生成技术方案。</p>`;

  // primary device spec
  const primaryDevice = devices.length > 0 ? devices[0] : null;
  let deviceSection = '';
  if (primaryDevice) {
    deviceSection = subSection('2.2 主要设备选型', kvTable([
      ['供应商 / 品牌', primaryDevice.vendor],
      ['设备型号', primaryDevice.model],
      ['产品系列', primaryDevice.series_name],
      ['设备类别', primaryDevice.device_family],
      ['电化学类型', primaryDevice.battery_chemistry],
      ['额定功率', primaryDevice.rated_power_kw != null ? `${num(primaryDevice.rated_power_kw, 0)} kW` : null],
      ['额定容量', primaryDevice.rated_energy_kwh != null ? `${num(primaryDevice.rated_energy_kwh, 0)} kWh` : null],
      ['可用容量（出厂）', primaryDevice.usable_energy_kwh_at_fat != null ? `${num(primaryDevice.usable_energy_kwh_at_fat, 0)} kWh` : null],
      ['额定时长', primaryDevice.duration_hour != null ? `${num(primaryDevice.duration_hour, 1)} h` : null],
      ['直流电压范围', primaryDevice.dc_voltage_range_v],
      ['交流并网电压', primaryDevice.ac_grid_voltage_v],
      ['充放电效率', primaryDevice.efficiency_pct != null ? `${num(primaryDevice.efficiency_pct, 1)}%` : null],
      ['冷却方式', primaryDevice.cooling_type],
      ['消防探测', primaryDevice.fire_detection],
      ['消防灭火', primaryDevice.fire_suppression],
      ['安全等级', primaryDevice.safety_level],
      ['循环寿命', primaryDevice.cycle_life != null ? `${num(primaryDevice.cycle_life, 0)} 次` : null],
      ['SOC 使用范围', primaryDevice.soc_min != null && primaryDevice.soc_max != null ? `${num(primaryDevice.soc_min * 100, 0)}% ~ ${num(primaryDevice.soc_max * 100, 0)}%` : null],
      ['防护等级', primaryDevice.ip_system],
      ['防腐等级', primaryDevice.corrosion_grade],
      ['安装方式', primaryDevice.install_mode],
      ['外形尺寸 (W×D×H)', primaryDevice.dimension_w_mm != null ? `${num(primaryDevice.dimension_w_mm, 0)} × ${num(primaryDevice.dimension_d_mm, 0)} × ${num(primaryDevice.dimension_h_mm, 0)} mm` : null],
      ['重量', primaryDevice.weight_kg != null ? `${num(primaryDevice.weight_kg, 0)} kg` : null],
      ['通讯协议', primaryDevice.communication_protocol],
      ['支持黑启动', primaryDevice.supports_black_start ? '是' : '否'],
      ['支持离网微电网', primaryDevice.supports_offgrid_microgrid ? '是' : '否'],
      ['参考单价', primaryDevice.price_yuan_per_wh != null ? `${num(primaryDevice.price_yuan_per_wh, 3)} 元/Wh` : null],
      ['能量单价', primaryDevice.energy_unit_price_yuan_per_kwh != null ? `${num(primaryDevice.energy_unit_price_yuan_per_kwh, 0)} 元/kWh` : null],
    ]));
  } else {
    deviceSection = subSection('2.2 主要设备选型',
      `<p class="no-data">未导入设备库。请先在资产配置页面上传设备参数表，设备型号、技术参数、安全配置等信息将自动填充至此章节。</p>`
    );
  }

  // safety design
  const safetyText = primaryDevice
    ? `本方案选用<strong>${esc(primaryDevice.battery_chemistry || '磷酸铁锂（LFP）')}</strong>电芯，采用<strong>${esc(primaryDevice.cooling_type || '液冷')}</strong>温控方案，配备<strong>${esc(primaryDevice.fire_detection || '多级')}探测</strong>与<strong>${esc(primaryDevice.fire_suppression || '气体灭火')}</strong>系统，防护等级 <strong>${esc(primaryDevice.ip_system || 'IP54')}</strong>。系统满足 GB/T 36276、UL 9540A 等相关标准要求。`
    : '建议选用磷酸铁锂（LFP）电芯，配备三级消防防护体系（Pack 级探测—簇级灭火—舱级隔离），采用液冷或强制风冷温控方案，满足 GB/T 36276、UL 9540A、NFPA 855 等国内外标准。';

  // quantity estimation
  let quantitySection = '';
  if (cfg?.rated_power_kw != null && cfg?.rated_energy_kwh != null && primaryDevice?.rated_power_kw != null && primaryDevice?.rated_energy_kwh != null && primaryDevice.rated_power_kw > 0 && primaryDevice.rated_energy_kwh > 0) {
    const unitPower = primaryDevice.rated_power_kw;
    const unitEnergy = primaryDevice.rated_energy_kwh;
    const qtyByPower = Math.ceil(cfg.rated_power_kw / unitPower);
    const qtyByEnergy = Math.ceil(cfg.rated_energy_kwh / unitEnergy);
    const qty = Math.max(qtyByPower, qtyByEnergy);
    quantitySection = subSection('2.4 设备数量估算',
      `<p>根据推荐功率 ${num(cfg.rated_power_kw, 0)} kW / 容量 ${num(cfg.rated_energy_kwh, 0)} kWh，单台设备功率 ${num(unitPower, 0)} kW / 容量 ${num(unitEnergy, 0)} kWh，估算需要 <strong>${qty} 台</strong>（按功率需 ${qtyByPower} 台，按容量需 ${qtyByEnergy} 台）${esc(primaryDevice.model || '')} 设备。</p>`
    );
  }

  // optimization process
  let optimizationSection = '';
  const pareto = payload.charts?.pareto;
  const history = payload.charts?.optimization_history;
  if (pareto?.length) {
    const scatterData = pareto.map(p => ({
      x: (p.initialInvestmentWan ?? 0),
      y: (p.npvWan ?? 0),
      label: p.index != null ? String(p.index) : undefined,
      feasible: p.feasible ?? false,
      recommended: false,
    }));
    const frontierData = (payload.charts?.pareto_frontier || pareto.filter(p => p.paretoFrontier))
      .map(p => ({ x: p.initialInvestmentWan ?? 0, y: p.npvWan ?? 0 }))
      .filter(p => Number.isFinite(p.x) && Number.isFinite(p.y));
    // mark the highest NPV feasible as recommended
    const bestFeasible = scatterData.filter(d => d.feasible).sort((a, b) => b.y - a.y)[0];
    if (bestFeasible) bestFeasible.recommended = true;
    const genInfo = history?.total_generations
      ? `优化共运行 <strong>${history.total_generations}</strong> 代，最终种群 <strong>${history.final_population_size ?? '--'}</strong> 个个体，其中可行解 <strong>${history.final_feasible_count ?? '--'}</strong> 个。`
      : '';
    optimizationSection = subSection('2.5 优化过程与方案优选',
      `<p>求解器采用多目标遗传算法（GA）在搜索空间中寻优。${genInfo}下图为候选方案 Pareto 分布（X=初始投资万元，Y=NPV 万元，绿色可行/灰色不可行/红色为推荐方案，金色点划线为非支配前沿）：</p>` +
      svgScatterChart(scatterData, 600, 400, {
        xLabel: '初始投资 (万元)', yLabel: '净现值 (万元)',
        referenceLines: [{ value: 0, label: 'NPV=0', color: SEMANTIC_COLORS.constraint, dashArray: '5,5' }],
        frontierData,
      })
    );
  }

  // candidate comparison
  let comparisonSection = '';
  const alternatives = payload.candidate_comparison?.alternatives || [];
  if (cfg && fin && alternatives.length > 0) {
    // build recommended row from configuration + financial.core (already normalized)
    const finCore = (fin as ReportFinancial).core || (fin as Record<string, unknown>);
    const recPower = num(cfg.rated_power_kw, 0);
    const recEnergy = num(cfg.rated_energy_kwh, 0);
    const recInvest = num(((Number(finCore.initial_investment_yuan) || 0) / 10000), 0);
    const recNpv = num(((Number(finCore.npv_yuan) || 0) / 10000), 0);
    const recIrr = finCore.irr != null ? pct(finCore.irr) : '暂无数据';
    const recPayback = finCore.simple_payback_years != null ? `${num(finCore.simple_payback_years, 1)} 年` : '暂无数据';
    const recRow = [`<span style="background:#ecfdf5;font-weight:600;">★ 推荐方案</span>`, recPower, recEnergy, recInvest, recNpv, recIrr, recPayback, '低风险', '综合经济性与电网安全性最优'];

    // deduplicate by power+capacity+NPV
    const seen = new Set<string>();
    const uniqueAlts = alternatives.filter((a: Record<string, unknown>) => {
      const key = `${a.ratedPowerKw ?? a.rated_power_kw}_${a.ratedEnergyKwh ?? a.rated_energy_kwh}_${a.npvWan ?? a.npv_yuan}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    }).slice(0, 4);
    const altRows = uniqueAlts.map((a: Record<string, unknown>, i: number) => {
      const pwr = num(a.ratedPowerKw ?? a.rated_power_kw, 0);
      const en = num(a.ratedEnergyKwh ?? a.rated_energy_kwh, 0);
      const invYuan = a.initialInvestmentWan ?? (a.initial_investment_yuan != null ? Number(a.initial_investment_yuan) / 10000 : null);
      const inv = num(invYuan, 0);
      const npvYuan = a.npvWan ?? (a.npv_yuan != null ? Number(a.npv_yuan) / 10000 : null);
      const npvVal = num(npvYuan, 0);
      const irrVal = a.irr != null ? pct(a.irr) : '暂无数据';
      const payback = a.paybackYears ?? a.simple_payback_years != null ? `${num(a.paybackYears ?? a.simple_payback_years, 1)} 年` : '暂无数据';
      return [`方案 ${i + 1}`, pwr, en, inv, npvVal, irrVal, payback, a.feasible ? '低风险' : '存在越限', '备选方案'];
    });

    const compCols = ['方案', '功率 (kW)', '容量 (kWh)', '投资 (万元)', 'NPV (万元)', '全投资内部收益率 (IRR)', '回收期 (年)', '电网风险', '推荐理由'];
    comparisonSection = subSection('2.6 候选方案对比',
      '<p>求解器在搜索空间中生成了多个候选配置方案，下表对比推荐方案与备选方案的关键指标：</p>' +
      dataTable(compCols, [recRow, ...altRows], ['left', 'right', 'right', 'right', 'right', 'right', 'right', 'left', 'left'], new Set([0]))
    );
  }

  // engineering design elements
  let engineeringSection = '';
  if (cfg?.rated_power_kw != null && primaryDevice) {
    const unitPower = primaryDevice.rated_power_kw || 0;
    const unitEnergy = primaryDevice.rated_energy_kwh || 0;
    const qtyByPower = unitPower > 0 ? Math.ceil(cfg.rated_power_kw / unitPower) : 0;
    const qtyByEnergy = unitEnergy > 0 ? Math.ceil((cfg.rated_energy_kwh ?? 0) / unitEnergy) : 0;
    const qty = Math.max(qtyByPower, qtyByEnergy);
    const areaEst = primaryDevice.dimension_w_mm && primaryDevice.dimension_d_mm && qty
      ? `${num((primaryDevice.dimension_w_mm * primaryDevice.dimension_d_mm * qty * 2.5) / 1e6, 1)} m²（估算，含安全间距）`
      : '待现场确认';
    const weightEst = primaryDevice.weight_kg && qty
      ? `${num((primaryDevice.weight_kg * qty) / 1000, 1)} 吨（不含基础及附属设施）`
      : '待现场确认';
    engineeringSection = subSection('2.7 一次系统设计概要',
      '<p>基于推荐方案配置及选型设备参数，初步估算一次系统主要设计参数如下。标注"待现场确认"的项目需在施工前由设计单位现场踏勘后确定。</p>' +
      kvTable([
        ['接入电压等级', primaryDevice.ac_grid_voltage_v || '待现场确认'],
        ['接入点', friendlyNodeName(cfg.target_bus || cfg.target_id || '待现场确认')],
        ['PCS 数量（估算）', qty > 0 ? `${qty} 台（与储能柜配套）` : '待现场确认'],
        ['储能柜数量（估算）', qty > 0 ? `${qty} 台` : '待现场确认'],
        ['并网柜 / 计量柜', '需根据接入方案设计配置（待现场确认）'],
        ['保护配置', '需根据接入电压等级和保护配合要求设计（待现场确认）'],
        ['通信架构', primaryDevice.communication_protocol ? `支持 ${primaryDevice.communication_protocol}` : '待现场确认'],
        ['消防分区', '需根据储能柜数量和布置方案划分（待现场确认）'],
        ['预估占地面积', areaEst],
        ['预估重量', weightEst],
        ['土建要求', '需满足设备荷载及防水、防腐蚀要求（以地勘报告和结构设计为准）'],
      ], '35%', true)
    );
  }

  return section('二、技术方案设计',
    subSection('2.1 系统架构概述', `<p>${archText}</p>`) +
    deviceSection +
    subSection('2.3 安全设计', `<p>${safetyText}</p>`) +
    quantitySection +
    optimizationSection +
    comparisonSection +
    engineeringSection
  );
}

function buildControlStrategy(payload: ReportPayload): string {
  const cfg = payload.configuration;
  const strategyName = cfg?.strategy_name || '峰谷套利 + 需量管理综合策略';
  const bgPolicy = cfg?.background_load_policy;

  let bgSection = '';
  if (bgPolicy && bgPolicy.trim()) {
    bgSection = subSection('3.3 备电保障策略',
      `<p>${esc(bgPolicy)}</p>`
    );
  }

  // representative day chart
  let repDayChart = '';
  const repDay = payload.charts?.representative_day;
  if (repDay?.rows?.length) {
    const dualData = repDay.rows.map((r: Record<string, unknown>) => {
      const soc = typeof r.socOpen === 'number' ? r.socOpen : typeof r.soc === 'number' ? r.soc : 0;
      const chgRaw = typeof r.chargeKw === 'number' ? r.chargeKw : 0;
      const dis = typeof r.dischargeKw === 'number' ? r.dischargeKw : 0;
      // backend outputs chargeKw as negative magnitude; normalize: discharge +, charge -
      const netPower = (chgRaw as number) < 0
        ? (dis as number) + (chgRaw as number)
        : (dis as number) - (chgRaw as number);
      return {
        label: String(r.hour ?? ''),
        leftValue: (soc as number) * 100,
        rightValue: netPower,
      };
    });
    repDayChart = subSection('3.4 代表日运行曲线',
      `<p>以下为年吞吐量最大日的充放电功率与荷电状态变化（绿色=放电，红色=充电，蓝色折线=SOC%）：</p>` +
      svgDualAxisChart(dualData, 600, 350, {
        leftLabel: '荷电状态 SOC (%)',
        rightLabel: '净放电功率 (kW)',
        leftColor: SEMANTIC_COLORS.revenue.primary,
        rightColor: SEMANTIC_COLORS.feasible,
      })
    );
  }

  return section('三、控制策略',
    subSection('3.1 峰谷套利策略',
      `<p>储能系统依据分时电价曲线，在低谷/平价时段充电、高峰/尖峰时段放电，实现"${strategyName.includes('两充') ? '两充两放' : '削峰填谷'}"。优化算法每日滚动决策各时段充放电功率，在满足设备约束与电网安全约束的前提下最大化收益。</p>`
    ) +
    subSection('3.2 需量管控策略',
      `<p>实时监测变压器负荷，在负荷接近变压器容量上限时优先由储能放电支撑，降低关口最大需量，规避基本电费超容罚款。控制参数遵循变压器严格备用容量原则，确保储能充放电不会导致变压器过载。</p>`
    ) +
    bgSection +
    repDayChart +
    `<div class="note">更详细的逐时运行数据请参见求解结果文件中的年度逐时运行表。</div>`
  );
}

function buildEconomicAnalysis(payload: ReportPayload): string {
  const fin = payload.financial;

  if (!fin?.core || fin.core.npv_yuan == null) {
    return section('四、全生命周期经济性分析',
      `<p class="no-data">暂无经济性数据。请运行求解以生成全生命周期经济性分析。求解完成后将自动计算 NPV、IRR、投资回收期、收益构成、成本明细及全生命周期现金流表。</p>`
    );
  }

  const core = fin.core;
  const rev = core.revenue_breakdown;
  const cost = core.cost_breakdown;
  const assumptions = payload.assumptions;
  const primaryDevice = payload.devices?.[0];

  // 4.1 revenue calculation basis
  let basisSection = '';
  const basisRows: [string, unknown][] = [];
  if (primaryDevice?.efficiency_pct != null) basisRows.push(['充放电效率', `${num(primaryDevice.efficiency_pct, 1)}%`]);
  basisRows.push(['电池衰减假设', '首年容量因子 100%，逐年按循环寿命曲线衰减']);
  if (assumptions?.discount_rate != null) basisRows.push(['折现率', pct(assumptions.discount_rate)]);
  if (assumptions?.project_life_years != null) basisRows.push(['项目寿命', `${num(assumptions.project_life_years, 0)} 年`]);
  if (assumptions?.soc_min != null && assumptions?.soc_max != null) {
    basisRows.push(['SOC 使用范围', `${pct(assumptions.soc_min)} ~ ${pct(assumptions.soc_max)}`]);
  }
  if (payload.project_meta?.has_tariff) {
    basisRows.push(['电价数据', `已导入（${payload.project_meta.tariff_year ?? '--'} 年）`]);
  }
  if (basisRows.length > 0) {
    basisSection = subSection('4.1 经济评价基础假设',
      kvTable(basisRows, '35%', true) +
      '<p class="note">以上为经济评价的关键基础假设。详细电价曲线请参见求解结果中的代表日运行数据，实际收益计算已结合逐时电价曲线进行。</p>'
    );
  }

  // 4.7 sensitivity table
  let sensitivitySection = '';
  const baseNpv = core.npv_yuan ?? 0;
  const basePayback = core.simple_payback_years ?? 0;
  const baseInvestment = core.initial_investment_yuan ?? 0;
  if (baseNpv !== 0) {
    const scenarios = [
      { name: '电价下降 10%', npvDelta: baseNpv * 0.4 * (-0.1), irrDelta: '约 -1.5 pp', paybackDelta: basePayback * 0.08, note: '需关注' },
      { name: '设备投资上升 10%', npvDelta: -(baseInvestment * 0.1), irrDelta: '约 -1.0 pp', paybackDelta: basePayback * 0.06, note: '需关注' },
      { name: '利用小时下降 15%', npvDelta: baseNpv * 0.6 * (-0.15), irrDelta: '约 -2.0 pp', paybackDelta: basePayback * 0.12, note: '重点关注' },
      { name: '电池衰减加快 +20%', npvDelta: baseNpv * 0.15 * (-0.2), irrDelta: '约 -0.5 pp', paybackDelta: basePayback * 0.04, note: '影响较小' },
      { name: '政府补贴取消', npvDelta: baseNpv * 0.05 * (-1.0), irrDelta: '约 -0.3 pp', paybackDelta: basePayback * 0.02, note: '影响较小' },
    ];
    const sensCols = ['情景', 'NPV 变化（万元）', 'IRR 变化（估算）', '回收期变化（年，估算）', '综合判断'];
    const sensRows = scenarios.map(s => {
      const newNpv = baseNpv + s.npvDelta;
      const feasible = newNpv > 0;
      return [
        s.name,
        money(s.npvDelta),
        s.irrDelta,
        `+${num(s.paybackDelta, 1)} 年`,
        feasible ? `${s.note}，仍可行` : `${s.note}，NPV 转负`,
      ];
    });
    sensitivitySection = subSection('4.7 敏感性分析',
      '<p>基于推荐方案的核心财务指标，对关键变量进行单因素敏感性分析。以下为简化估算结果，详细模型请参见求解器财务诊断报告：</p>' +
      dataTable(sensCols, sensRows, ['left', 'right', 'right', 'right', 'left']) +
      '<p class="note">注：以上为基于财务核心指标的简化比例估算，实际敏感性应以逐项调整全生命周期现金流模型重新计算为准。</p>'
    );
  } else {
    sensitivitySection = subSection('4.7 敏感性分析',
      '<p class="no-data">NPV 为零或缺失，无法进行敏感性分析。请检查求解结果与经济性数据。</p>'
    );
  }

  return section('四、全生命周期经济性分析',
    basisSection +
    subSection('4.2 投资概算', kvTable([
      ['初始总投资', money(core.initial_investment_yuan)],
      ['含政府补贴后净投资', core.initial_investment_yuan != null ? '（详见附件 B 审计分类账）' : '暂无数据'],
    ])) +
    subSection('4.3 年度收益结构', kvTable([
      ['峰谷套利收益', money(rev?.arbitrage)],
      ['需量管理节约', money(rev?.demand_saving)],
      ['容量市场收益', money(rev?.capacity)],
      ['降损收益', money(rev?.loss_reduction)],
      ['辅助服务净收益', money(rev?.auxiliary_service)],
    ])) +
    subSection('4.4 年度成本结构', kvTable([
      ['电池衰减成本', money(cost?.degradation)],
      ['运维费用（Operation & Maintenance, O&M）', money(cost?.o_and_m)],
      ['设备更换等效年金', money(cost?.replacement)],
      ['变压器越限惩罚', money(cost?.transformer_penalty)],
      ['电压越限惩罚', money(cost?.voltage_penalty)],
    ])) +
    subSection('4.5 核心财务指标', kvTable([
      ['净现值 (NPV)', money(core.npv_yuan)],
      ['全投资内部收益率 (IRR)', pct(core.irr)],
      ['静态投资回收期', core.simple_payback_years != null ? `${num(core.simple_payback_years, 1)} 年` : '暂无数据'],
      ['动态投资回收期', core.discounted_payback_years != null ? `${num(core.discounted_payback_years, 1)} 年` : '暂无数据'],
      ['年均净现金流', money(core.annualized_net_cashflow_yuan)],
      ['平准化度电成本 (LCOE)', core.lcoe_yuan_per_kwh != null ? `${num(core.lcoe_yuan_per_kwh, 3)} 元/kWh` : '暂无数据'],
      ['投资回报率 (ROI)', core.roi_pct != null ? `${num(core.roi_pct, 1)}%` : '暂无数据'],
    ])) +
    buildCashflowTable(fin) +
    sensitivitySection +
    buildFinancialCharts(payload)
  );
}

function buildFinancialCharts(payload: ReportPayload): string {
  const charts = payload.charts;
  if (!charts) return '';

  let parts = '';

  // capital breakdown bar chart
  const capitalData = charts.capital_breakdown;
  if (capitalData?.length) {
    const barData = capitalData.map(d => ({
      label: esc(String(d.name)),
      value: d.valueWan ?? 0,
    }));
    parts += subSection('4.8 投资构成',
      svgBarChart(barData, 600, 350, { yLabel: '万元', color: SEMANTIC_COLORS.optimized, valueFormatter: (v) => `${num(v, 0)} 万元` })
    );
  }

  // annual value breakdown diverging stacked chart
  const valueData = charts.annual_value_breakdown;
  if (valueData?.length) {
    const colors = [SEMANTIC_COLORS.revenue.primary, SEMANTIC_COLORS.revenue.secondary, SEMANTIC_COLORS.revenue.tertiary, SEMANTIC_COLORS.revenue.quaternary, SEMANTIC_COLORS.cost.primary, SEMANTIC_COLORS.cost.secondary, SEMANTIC_COLORS.cost.tertiary];
    const allSegments = valueData.map((d, i) => ({
      key: String(d.name || ''),
      value: d.valueWan ?? 0,
      color: colors[i % colors.length],
    }));
    if (allSegments.length) {
      parts += subSection('4.9 年度收益与成本构成',
        `<p>收益项（正值）向上堆叠，成本项（负值）向下堆叠：</p>` +
        svgStackedBarChart([{ label: '年度价值', segments: allSegments }], 600, 380, { yLabel: '万元' })
      );
    }
  }

  // LCOS cost composition
  const lcosData = charts.lcos;
  if (lcosData?.components?.length) {
    const summary = lcosData.summary || {};
    const lcosBars = lcosData.components.map(d => ({
      label: String(d.name || ''),
      value: d.valueWan ?? 0,
    }));
    const lcosText = summary.lcosYuanPerKwh != null
      ? `<p>测算 LCOS 为 <strong>${num(summary.lcosYuanPerKwh, 3)} 元/kWh吞吐</strong>，生命周期总成本约 <strong>${num(summary.totalCostWan, 1)} 万元</strong>，对应总吞吐量约 <strong>${num(summary.totalThroughputMwh, 1)} MWh</strong>。</p>`
      : '<p>LCOS 按生命周期成本与生命周期吞吐量口径测算，当前数据不足以形成单位成本。</p>';
    parts += subSection('4.10 LCOS 成本构成',
      lcosText +
      svgBarChart(lcosBars, 600, 350, {
        yLabel: '万元',
        color: SEMANTIC_COLORS.cost.secondary,
        negativeColor: SEMANTIC_COLORS.revenue.secondary,
        valueFormatter: (v) => `${num(v, 0)} 万元`,
      })
    );
  }

  // cumulative cashflow line chart (dual cumulative lines)
  const cashflowData = charts.cashflow;
  if (cashflowData?.length) {
    const multiData = cashflowData.map(d => ({ label: `Y${d.year ?? ''}`, cumulativeUndiscountedWan: d.cumulativeUndiscountedWan ?? 0, cumulativeDiscountedWan: d.cumulativeDiscountedWan ?? 0 }));
    parts += subSection('4.11 累计现金流趋势',
      `<p>下图为全生命周期累计未折现现金流（虚线）与累计折现现金流（实线）趋势：</p>` +
      svgLineChart([], 600, 350, {
        yLabel: '累计现金流（万元）',
        series: [
          { key: 'cumulativeUndiscountedWan', color: SEMANTIC_COLORS.baseline, label: '累计未折现', lineStyle: 'dashed' },
          { key: 'cumulativeDiscountedWan', color: SEMANTIC_COLORS.optimized, label: '累计折现' },
        ],
        multiData,
      })
    );
  }

  // SOH / capacity factor lifecycle trend
  const degradationSoh = charts.degradation_soh;
  if (degradationSoh?.length) {
    const multiData = degradationSoh.map(d => ({
      label: `Y${d.year ?? ''}`,
      batterySohPct: d.batterySohPct ?? 0,
      capacityFactorPct: d.capacityFactorPct ?? 0,
    }));
    parts += subSection('4.12 SOH 与容量保持率',
      `<p>下图展示生命周期内电池健康度（SOH）与可用容量保持率；若旧结果文件缺少逐年字段，则按财务摘要首末容量因子或 100% 默认值兼容展示。</p>` +
      svgLineChart([], 600, 350, {
        yLabel: '比例（%）',
        series: [
          { key: 'batterySohPct', color: SEMANTIC_COLORS.soc, label: 'SOH' },
          { key: 'capacityFactorPct', color: SEMANTIC_COLORS.optimized, label: '容量保持率', lineStyle: 'dashed' },
        ],
        multiData,
        referenceLines: [{ value: 70, label: '70% 更换阈值', color: SEMANTIC_COLORS.constraint, dashArray: '8,4,2,4' }],
      })
    );
  }

  // monthly revenue chart
  const monthlyData = charts.monthly_revenue;
  if (monthlyData?.length) {
    const monthlyBars = monthlyData.map(d => ({
      label: `${d.month ?? ''}月`,
      value: d.netCashflowWan ?? 0,
    }));
    parts += subSection('4.13 月度净收益分布',
      svgBarChart(monthlyBars, 600, 350, { yLabel: '万元', color: SEMANTIC_COLORS.optimized, valueFormatter: (v) => `${num(v, 0)} 万元` })
    );
    // also render monthly revenue as a table
    const monthCols = ['月份', '峰谷套利（万元）', '需量节约（万元）', '容量收益（万元）', '降损收益（万元）', '罚金（万元）', '净现金流（万元）'];
    const monthRows = monthlyData.map(d => [
      `${d.month ?? '--'}月`,
      num(d.arbitrageRevenueWan, 2),
      num(d.demandSavingWan, 2),
      num(d.capacityRevenueWan, 2),
      num(d.lossReductionRevenueWan, 2),
      num(d.penaltyCostWan, 2),
      num(d.netCashflowWan, 2),
    ]);
    parts += subSection('4.12 月度收益明细', dataTable(monthCols, monthRows));
  }

  return parts;
}

function buildCashflowTable(fin: ReportFinancial): string {
  const rows = fin.cashflow_table;
  if (!rows || rows.length === 0) {
    return subSection('4.6 全生命周期现金流', `<p class="no-data">暂无现金流数据。</p>`);
  }
  const columns = ['年份', '年收入（万元）', '年运营成本（万元）', '年净现金流（万元）', '累计未折现（万元）', '年折现净现金流（万元）', '累计折现（万元）'];
  const data = rows.map(r => [
    num(r.year, 0),
    num(r.revenue_yuan != null ? (r.revenue_yuan / 10000) : null),
    num(r.op_cost_yuan != null ? (r.op_cost_yuan / 10000) : null),
    num(r.net_cashflow_yuan != null ? (r.net_cashflow_yuan / 10000) : null),
    num(r.cumulative_undiscounted_yuan != null ? (r.cumulative_undiscounted_yuan / 10000) : null),
    num(r.discounted_net_yuan != null ? (r.discounted_net_yuan / 10000) : null),
    num(r.cumulative_discounted_yuan != null ? (r.cumulative_discounted_yuan / 10000) : null),
  ]);
  return subSection('4.6 全生命周期现金流', dataTable(columns, data));
}

function buildSafetyGridImpact(payload: ReportPayload): string {
  const ni = payload.network_impact;
  const rh = payload.run_health;

  if (!ni || (!ni.target_area_conclusion && !ni.risk_classification?.length && !rh?.issues?.length)) {
    return section('五、安全与电网影响分析',
      `<p class="no-data">未运行配电网安全校核（OpenDSS，Open Distribution System Simulator）。请在求解时启用 OpenDSS 约束校核以生成本章节内容。</p>`
    );
  }

  let parts = '';

  // target area conclusion
  const { improved: improvedCount, worsened: worsenedCount } = countRiskItems(ni);
  let conclusionTitle: string;
  let conclusionText: string;
  let conclusionClass: string;
  if (worsenedCount === 0 && improvedCount > 0) {
    conclusionTitle = '✓ 总体改善';
    conclusionText = '储能接入后目标区域电网安全指标总体改善，未新增系统性风险。建议在项目实施前对关键节点进行现场复核。';
    conclusionClass = 'improved';
  } else if (improvedCount >= worsenedCount && worsenedCount > 0) {
    conclusionTitle = '— 部分改善，存在局部风险';
    conclusionText = `储能接入后部分指标改善（${improvedCount} 项），但存在 ${worsenedCount} 项局部风险需关注。建议在实施前对恶化项进行现场复核或配电网改造，并经电网公司接入审批。`;
    conclusionClass = 'neutral';
  } else if (worsenedCount > improvedCount) {
    conclusionTitle = '⚠ 需重点关注';
    conclusionText = `储能接入后存在 ${worsenedCount} 项安全指标恶化（改善 ${improvedCount} 项），建议在实施前对配电网进行针对性改造或调整储能运行策略。`;
    conclusionClass = 'worsened';
  } else {
    conclusionTitle = '— 无显著影响';
    conclusionText = '储能接入后未检测到显著的电网安全指标变化。';
    conclusionClass = 'neutral';
  }
  parts += subSection('5.1 目标接入区域综合结论',
    `<div class="conclusion-box ${conclusionClass}"><strong>${conclusionTitle}</strong> — ${esc(conclusionText)}</div>`
  );

  // risk classification
  const risks = Array.isArray(ni.risk_classification) ? ni.risk_classification : [];
  if (risks.length > 0) {
    const riskCols = ['风险类别', '总计', '电压', '线路', '变压器'];
    const riskData = risks.map((r: Record<string, unknown>) => [
      classifyLabel(String(r.classification ?? '--')),
      String(r.total ?? '--'),
      String(r.voltage ?? '--'),
      String(r.line ?? '--'),
      String(r.transformer ?? '--'),
    ]);
    parts += subSection('5.2 风险分类统计', dataTable(riskCols, riskData, ['left', 'right', 'right', 'right', 'right']));
  }

  // remediation table for worsened/storage_induced risks
  const nonImprovedRisks = [
    ...(Array.isArray(ni.voltage_top_risks) ? ni.voltage_top_risks : []).filter((r: Record<string, unknown>) => {
      const cls = String(r.classification ?? '');
      return cls === 'worsened_by_storage' || cls === 'storage_induced';
    }),
    ...(Array.isArray(ni.line_top_risks) ? ni.line_top_risks : []).filter((r: Record<string, unknown>) => {
      const cls = String(r.classification ?? '');
      return cls === 'worsened_by_storage' || cls === 'storage_induced';
    }),
    ...(Array.isArray(ni.transformer_top_risks) ? ni.transformer_top_risks : []).filter((r: Record<string, unknown>) => {
      const cls = String(r.classification ?? '');
      return cls === 'worsened_by_storage' || cls === 'storage_induced';
    }),
  ];
  if (nonImprovedRisks.length > 0) {
    const remediationCols = ['风险点', '类型', '原因分析', '建议措施', '对实施影响'];
    const remediationRows = nonImprovedRisks.slice(0, 10).map((r: Record<string, unknown>) => {
      const point = friendlyNodeName(String(r.bus || r.line || r.transformer || '--'));
      const riskType = String(r.bus ? '电压' : r.line ? '线路' : '变压器');
      const cls = classifyLabel(String(r.classification ?? '--'));
      let cause = '';
      if (riskType === '电压') cause = '储能充放电导致接入点及邻近母线电压波动或越限';
      else if (riskType === '线路') cause = '储能大功率充放电增加线路潮流，导致负载率上升或过载';
      else cause = '储能充放电叠加基础负荷可能超出变压器容量限额';
      let measure = '';
      if (riskType === '电压') measure = '调整储能无功控制策略或增设无功补偿装置；必要时升级接入线路截面';
      else if (riskType === '线路') measure = '复核线路容量，必要时更换大截面导线或增设线路；优化储能充放电时序';
      else measure = '复核变压器容量，必要时增容或增设分布式储能分散接入；严格控制充放电功率上限';
      let impact = '需复核后实施';
      if (cls === '严重异常' || r.level === 'critical') impact = '建议改造后实施';
      return [point, riskType, cause, measure, impact];
    });
    parts += subSection('5.2.1 整改建议',
      '<p>以下列出储能接入后出现恶化或新增风险的关键节点，建议在项目实施前进行专项整改：</p>' +
      dataTable(remediationCols, remediationRows, ['left', 'left', 'left', 'left', 'left'])
    );
  }

  // voltage top risks (top 10)
  const voltRisks = Array.isArray(ni.voltage_top_risks) ? ni.voltage_top_risks.slice(0, 10) : [];
  if (voltRisks.length > 0) {
    const cols = ['母线', '分类', '基准越限小时', '储能后越限小时', '最大越限 (pu)'];
    const data = voltRisks.map((r: Record<string, unknown>) => [
      friendlyNodeName(String(r.bus ?? '--')),
      classifyLabel(String(r.classification ?? '--')),
      String(r.baseline_violation_hours ?? '暂无数据'),
      String(r.with_storage_violation_hours ?? '暂无数据'),
      num(r.max_violation_pu, 4),
    ]);
    parts += subSection('5.3 电压影响（Top 10）', dataTable(cols, data, ['left', 'left', 'right', 'right', 'right']));
  }

  // line top risks (top 10)
  const lineRisks = Array.isArray(ni.line_top_risks) ? ni.line_top_risks.slice(0, 10) : [];
  if (lineRisks.length > 0) {
    const cols = ['线路', '母线1', '母线2', '额定电流 (A)', '基准过载小时', '储能后过载小时', '最大负载率', '分类'];
    const data = lineRisks.map((r: Record<string, unknown>) => [
      friendlyNodeName(String(r.line ?? '--')),
      friendlyNodeName(String(r.bus1 ?? '--')),
      friendlyNodeName(String(r.bus2 ?? '--')),
      num(r.normamps, 1),
      String(r.baseline_overload_hours ?? '暂无数据'),
      String(r.with_storage_overload_hours ?? '暂无数据'),
      r.max_loading_pct != null ? `${num(r.max_loading_pct, 1)}%` : '暂无数据',
      classifyLabel(String(r.classification ?? '--')),
    ]);
    parts += subSection('5.4 线路负载影响（Top 10）', dataTable(cols, data, ['left', 'left', 'left', 'right', 'right', 'right', 'right', 'left']));
  }

  // transformer risks
  const trafoRisks = Array.isArray(ni.transformer_top_risks) ? ni.transformer_top_risks : [];
  if (trafoRisks.length > 0) {
    const cols = ['变压器', '分类', '基准过载小时', '储能后过载小时', '过载小时变化', '基准最大负载率', '储能后最大负载率'];
    const data = trafoRisks.map((r: Record<string, unknown>) => [
      friendlyNodeName(String(r.transformer ?? '--')),
      classifyLabel(String(r.classification ?? '--')),
      String(r.baseline_overload_hours ?? '暂无数据'),
      String(r.with_storage_overload_hours ?? '暂无数据'),
      String(r.overload_hour_delta ?? '暂无数据'),
      r.max_baseline_loading_pct != null ? `${num(r.max_baseline_loading_pct, 1)}%` : '暂无数据',
      r.max_with_storage_loading_pct != null ? `${num(r.max_with_storage_loading_pct, 1)}%` : '暂无数据',
    ]);
    parts += subSection('5.5 变压器影响', dataTable(cols, data, ['left', 'left', 'right', 'right', 'right', 'right', 'right']));
  }

  // data quality
  const dq = ni.data_quality as Record<string, unknown> | null | undefined;
  if (dq) {
    parts += subSection('5.6 数据质量', kvTable([
      ['OpenDSS 覆盖小时数', dq.opendss_trace_hours != null ? `${esc(dq.opendss_trace_hours)} h` : '--'],
      ['含网损分析', dq.has_opendss_loss ? '是' : '否'],
    ]));
  }

  // run health
  if (rh?.issues && rh.issues.length > 0) {
    const cols = ['级别', '代码', '问题描述', '原因', '影响', '建议'];
    const data = rh.issues.map(issue => [
      `<span class="${issue.level === 'critical' ? 'severity-critical' : 'severity-warning'}">${classifyLabel(issue.level || 'warning')}</span>`,
      classifyLabel(issue.code || ''),
      esc(issue.message),
      esc(issue.reason),
      esc(issue.impact),
      esc(issue.suggestion),
    ]);
    parts += subSection('5.7 运行健康检查',
      `<p>总体状态：<strong>${rh.status === 'passed' ? '✓ 通过' : rh.status === 'warning' ? '⚠ 有警告' : '✗ 严重异常'}</strong>，共 ${rh.total_issues ?? 0} 项问题（警告 ${rh.warning_count ?? 0} 项，严重 ${rh.critical_count ?? 0} 项）</p>` +
      dataTable(cols, data, ['left', 'left', 'left', 'left', 'left', 'left'], new Set([0]))
    );
  }

  // network constraint summary (from charts)
  const ncSummary = payload.charts?.network_constraints?.summary;
  if (ncSummary?.length) {
    const ncCols = ['指标', '数值', '单位'];
    const ncData = ncSummary.map((r: Record<string, unknown>) => [
      String(r.name ?? '--'),
      r.value != null ? num(r.value, 2) : '--',
      String(r.unit ?? '--'),
    ]);
    parts += subSection('5.8 电网约束指标汇总', dataTable(ncCols, ncData, ['left', 'right', 'left']));
  }

  return section('五、安全与电网影响分析', parts);
}

function buildImplementationPlan(payload: ReportPayload): string {
  const primaryDevice = payload.devices?.[0];
  const coolingType = primaryDevice?.cooling_type || '';
  const rh = payload.run_health;
  const hasCriticalIssues = (rh?.critical_count ?? 0) > 0;

  // dynamic timeline rows
  const timelineRows = [
    ['勘测设计', '第 1~2 周', '现场勘测、接入方案设计、设备选型确认', '勘测报告、初步设计图纸'],
    ['方案深化', '第 3~4 周', '施工图设计、电气一次/二次设计、消防设计', '施工图纸、设备采购清单'],
    ['设备采购', '第 5~8 周', '设备下单生产、出厂测试、物流运输', '设备出厂报告、运输单据'],
    ...(coolingType.includes('液冷') ? [['液冷系统部署', '第 8~9 周', '液冷管道敷设、冷却液加注、温控系统调试', '液冷系统调试报告']] : []),
    ['施工安装', '第 9~12 周', '基础施工、设备就位、电气接线、消防施工', '施工记录、隐蔽工程验收'],
    ['调试并网', '第 13~14 周', '系统联调、保护定值整定、并网试验、72h 试运行', '调试报告、并网验收单'],
    ...(hasCriticalIssues ? [['问题整改', '第 14~15 周', '针对健康检查中识别的严重问题进行专项整改与复测', '整改报告、复测记录']] : []),
    ['验收交付', '第 15~16 周', '竣工验收、消防验收、运维培训、资料移交', '竣工报告、培训记录'],
  ];

  const timeline = dataTable(
    ['阶段', '时间', '主要工作内容', '交付物'],
    timelineRows,
    ['left', 'left', 'left', 'left']
  );

  // grid connection compliance
  const gridConnectionSection = subSection('6.2 并网合规流程',
    `<p>储能系统并网需遵循以下流程，各阶段具体要求以当地电网公司最新规定为准：</p>` +
    `<ol style="font-size:10pt; line-height:2;">` +
    `<li><strong>接入系统审查：</strong>向电网公司提交接入系统设计方案，包括接入电压等级、接入点、短路容量校验、电能质量评估等，获得接入系统审查意见。</li>` +
    `<li><strong>继电保护定值整定：</strong>根据电网公司提供的短路容量和保护配合要求，完成保护装置定值整定，确保与上级电网保护正确配合。</li>` +
    `<li><strong>计量配置：</strong>安装关口计量装置（双向计量），经电网公司计量中心校验合格后封铅。</li>` +
    `<li><strong>消防验收：</strong>由具备资质的消防技术服务机构进行现场检查验收，出具消防验收合格意见。</li>` +
    `<li><strong>并网试验：</strong>完成保护传动试验、同期并网试验、功率控制试验、孤岛保护试验等，试验结果报电网公司备案。</li>` +
    `<li><strong>72 小时试运行：</strong>满负荷连续 72 小时试运行考核，期间各项指标应满足并网技术协议要求。</li>` +
    `<li><strong>正式并网：</strong>签署并网调度协议与供用电合同，正式投入商业运行。</li>` +
    `</ol>` +
    subSection('并网资料清单',
      dataTable(
        ['资料名称', '提供方', '备注'],
        [
          ['设备出厂试验报告', '设备供应商', '含电池、PCS、BMS 等核心部件'],
          ['安装调试报告', '施工单位', '含电气接线检查、绝缘测试、接地测试'],
          ['保护定值单', '设计单位', '需电网公司审核确认'],
          ['接入系统设计审查意见', '电网公司', '并网前置条件'],
          ['消防验收意见书', '消防技术服务机构', '并网前置条件'],
          ['并网调度协议', '电网公司 / 业主', '明确调度管辖范围与责任'],
          ['竣工验收报告', '建设单位', '含各分部分项工程验收记录'],
        ],
        ['left', 'left', 'left']
      )
    )
  );

  // enhanced O&M SLA
  const omSection = subSection('6.3 运维方案与 SLA',
    `<p>项目投运后提供 7×24 小时远程监控与定期巡检服务，运维 SLA 承诺如下：</p>` +
    dataTable(
      ['服务项目', '服务标准', '备注'],
      [
        ['系统可用率', '≥ 95%（不含计划检修停机）', '按年度统计'],
        ['重大故障响应', '4 小时内到场', '影响储能正常运行的故障'],
        ['一般故障响应', '24 小时内响应', '不影响主功能的告警或异常'],
        ['定期巡检', '每季度一次现场全面巡检', '含设备状态、消防、接地、通讯检查'],
        ['远程巡检', '每月一次远程数据巡检', 'SOC、SOH、温度、绝缘等关键参数'],
        ['备件策略', '关键易损件常备 ≥ 2 套', '冷却风扇滤网、通讯模块、熔断器等'],
        ['主要部件调配', '48 小时内调配到位', 'PCS 模块、BMS 板卡等'],
        ['电池容量保持率', '第 1 年 ≥ 98%，第 5 年 ≥ 80%，第 10 年 ≥ 70%', '按标准工况充放电循环'],
        ['整机质保', '5 年', '含 PCS、BMS、EMS、温控等'],
        ['电池系统质保', '10 年（含容量保持率担保）', '以容量保持率低于担保值为更换触发'],
        ['EMS 远程监控指标', 'SOC、SOH、充放电功率、电芯温度、环境温湿度、绝缘电阻、通讯状态', '异常自动告警分级推送'],
        ['告警闭环流程', '告警产生 → 系统自动分级 → 值班人员确认 → 派单 → 现场处理 → 结果记录 → 告警关闭', '全流程记录可追溯'],
      ],
      ['left', 'left', 'left']
    )
  );

  // training
  const trainingSection = subSection('6.4 培训与资料交付',
    `<ul>` +
    `<li><strong>操作培训：</strong>不少于 2 人次的操作与日常维护培训，含 EMS 操作、故障判断、应急处理。</li>` +
    `<li><strong>竣工资料：</strong>竣工图纸、设备说明书、调试报告、验收报告、保护定值单。</li>` +
    `<li><strong>运维手册：</strong>日常巡检清单、故障处理流程、应急操作指南、备件更换指导。</li>` +
    `</ul>`
  );

  return section('六、项目实施与运维',
    subSection('6.1 实施工期规划', timeline) +
    gridConnectionSection +
    omSection +
    trainingSection
  );
}

function buildRiskManagement(payload: ReportPayload): string {
  const rh = payload.run_health;
  const ni = payload.network_impact;

  const staticRisks = [
    ['电价政策风险', '分时电价机制调整、峰谷价差缩小', '高', '中', '关注政策动向，签订长期售电协议锁定价差'],
    ['设备安全风险', '电池热失控、电气火灾', '极高', '低', '三级消防防护体系 + 定期巡检 + 温度实时监控'],
    ['负荷波动风险', '用户负荷大幅下降导致储能利用率不足', '中', '中', '合同约定最低用电量 / 储能容量适当保守设计'],
    ['电网限电风险', '电网调度限电影响充放电计划', '中', '低', '接入方案充分考虑电网承载力，预留调控裕度'],
    ['设备衰减风险', '电池容量衰减快于预期，影响收益', '中', '中', '选用一线品牌电芯 + 容量衰减兜底条款'],
    ['施工安全风险', '施工期间人身伤害、设备损坏', '高', '低', '严格执行安全规程 + 施工保险覆盖'],
  ];

  // add dynamic risks from health issues
  const allIssues = rh?.issues || [];
  const dynamicRisks: string[][] = [];
  for (const issue of allIssues.slice(0, 5)) {
    const level = classifyLabel(issue.level || 'warning');
    const codeDisplay = `健康检查: ${classifyLabel(issue.code || '')}`;
    dynamicRisks.push([
      codeDisplay,
      esc(issue.message || ''),
      level,
      '中',
      esc(issue.suggestion || '请查看健康检查详情'),
    ]);
  }

  const riskMatrix = dataTable(
    ['风险类别', '风险描述', '影响程度', '发生概率', '缓解措施'],
    [...staticRisks, ...dynamicRisks],
    ['left', 'left', 'left', 'left', 'left']
  );

  // add solver-identified risks
  let solverRisks = '';
  const issues = rh?.issues || [];
  const criticalIssues = issues.filter(i => i.level === 'critical');
  if (criticalIssues.length > 0) {
    solverRisks = subSection('7.2 求解器识别的严重问题',
      `<ul>${criticalIssues.map(i => `<li><strong>${esc(i.code)}：</strong>${esc(i.message)} — ${esc(i.suggestion)}</li>`).join('')}</ul>`
    );
  }

  const targetConclusion = ni?.target_area_conclusion as Record<string, unknown> | null | undefined;
  let gridRiskNote = '';
  if (targetConclusion?.status === 'worsened') {
    gridRiskNote = `<div class="warning-banner"><strong>⚠ 电网风险提示：</strong>求解结果显示储能接入后目标区域部分安全指标恶化，建议在项目实施前进行详细的接入系统设计评审，必要时对配电网进行升级改造。</div>`;
  }

  return section('七、风险管控与应急预案',
    gridRiskNote +
    subSection('7.1 风险识别矩阵', riskMatrix) +
    solverRisks +
    subSection('7.3 应急预案概要',
      `<ul>` +
      `<li><strong>消防应急：</strong>配备气体灭火 + 水喷淋双系统，制定消防疏散路线图，每半年组织消防演练。</li>` +
      `<li><strong>设备故障应急：</strong>建立备品备件库（关键元器件不少于 2 套），制定快速更换流程。</li>` +
      `<li><strong>停电应急：</strong>储能系统支持黑启动与离网运行模式，关键负荷不断电。</li>` +
      `<li><strong>通讯中断应急：</strong>本地控制器可独立运行，保持基本充放电策略不受影响。</li>` +
      `</ul>`
    )
  );
}

function buildDisclaimer(payload: ReportPayload): string {
  const opendssEnabled = payload.assumptions?.opendss_enabled;
  return `<div class="section">
    <h2>免责声明与局限性说明</h2>
    <div class="disclaimer-box">
      <p style="margin-top:0;"><strong>本报告的使用限制与假设前提：</strong></p>
      <ol style="font-size:9.5pt; line-height:1.8;">
        <li>本报告结论依赖当前电价政策、负荷数据、设备市场价格及求解器模型参数配置。如上述条件发生变化，结论可能不再适用，建议定期更新分析。</li>
        ${opendssEnabled ? '<li>配电网安全分析基于 OpenDSS（Open Distribution System Simulator）仿真软件，模型基于项目提供的网络拓扑简化构建。实际电网运行条件可能存在差异，建议实施前进行详细的接入系统仿真与现场测试。</li>' : '<li>本报告未启用 OpenDSS 配电网安全校核，电网影响分析章节结论为有限数据推导。建议启用 OpenDSS 后重新求解以获得完整安全评估。</li>'}
        <li>储能调度策略基于历史负荷模式优化生成，实际运行中需根据实时负荷变化、电价信号及电网调度指令动态调整，实际收益可能与测算值存在偏差。</li>
        <li>投资回报测算未考虑未来电价调整、碳交易收益、绿色证书、辅助服务市场规则变化等政策因素。实际投资决策应综合考虑上述潜在变化。</li>
        <li>储能设备价格、安装工程费、土建费用等基于当前市场行情估算，实际合同价格以招标采购结果为准。</li>
        <li>建议在项目实施前完成现场踏勘，确认场地条件、接入条件、土建要求，最终方案需经电网公司批复后方可实施。</li>
        <li>本报告中的技术参数与配置建议仅供方案设计参考，不构成最终设计文件。详细设计应由具备相应资质的电力设计单位完成。</li>
      </ol>
    </div>
  </div>`;
}

function buildAppendices(payload: ReportPayload): string {
  let parts = '';

  // device full spec
  const devices = payload.devices;
  if (devices.length > 0) {
    const cols = ['供应商', '型号', '电化学', '额定功率 (kW)', '额定容量 (kWh)', '效率', '冷却', '消防', '安全等级', '循环寿命'];
    const data = devices.map(d => [
      esc(d.vendor),
      esc(d.model),
      esc(d.battery_chemistry),
      num(d.rated_power_kw, 0),
      num(d.rated_energy_kwh, 0),
      d.efficiency_pct != null ? `${num(d.efficiency_pct, 1)}%` : '--',
      esc(d.cooling_type),
      esc(d.fire_detection),
      esc(d.safety_level),
      d.cycle_life != null ? num(d.cycle_life, 0) : '--',
    ]);
    parts += subSection('A. 设备参数详表', dataTable(cols, data));
  }

  // audit ledger summary
  const fin = payload.financial;
  const ledgerItems = fin?.audit_ledger_items || [];
  if (ledgerItems.length > 0) {
    const cols = ['科目名称', '类别', '金额（元）', '数量', '单价', '异常标记'];
    const data = ledgerItems.map(item => [
      esc(item.name),
      classifyLabel(item.category),
      item.amount_yuan != null ? num(item.amount_yuan, 2) : '--',
      item.quantity != null ? num(item.quantity, 2) : '--',
      item.unit_price != null ? num(item.unit_price, 4) : '--',
      item.anomaly ? esc(item.anomaly) : '正常',
    ]);
    parts += subSection('B. 财务审计分类账明细', dataTable(cols, data, ['left', 'left', 'right', 'right', 'right', 'left']));
  }

  // anomalies
  const anomalies = fin?.audit_ledger_anomalies || [];
  if (anomalies.length > 0) {
    const cols = ['科目', '字段', '严重程度', '说明'];
    const data = anomalies.map(a => [
      classifyLabel(a.item),
      label(a.field),
      classifyLabel(a.level),
      esc(a.message),
    ]);
    parts += subSection('C. 财务异常项目', dataTable(cols, data, ['left', 'left', 'left', 'left']));
  }

  parts += subSection('D. 参考标准与规范',
    `<ul>` +
    `<li>GB/T 36276—2018《电力储能用锂离子电池》</li>` +
    `<li>GB/T 34120—2017《电化学储能系统储能变流器技术规范》</li>` +
    `<li>GB 51048—2014《电化学储能电站设计规范》</li>` +
    `<li>GB 50116—2013《火灾自动报警系统设计规范》</li>` +
    `<li>UL 9540《储能系统与设备安全标准》</li>` +
    `<li>UL 9540A《电池储能系统热失控传播测试方法》</li>` +
    `<li>NFPA 855《固定式储能系统安装标准》</li>` +
    `<li>IEC 62619《含碱性或其它非酸性电解质的蓄电池和蓄电池组—工业用锂蓄电池和蓄电池组的安全要求》</li>` +
    `</ul>`
  );

  // E. source files (collapsible)
  const sourceFiles = payload.source_files;
  if (sourceFiles?.length) {
    const cols = ['文件说明', '文件名称'];
    const data = sourceFiles.map(f => {
      const desc = classifyLabel(f.group || '--');
      const fname = (f.relative_path || '').replace(/^.*[\\/]/, '');
      return [desc, esc(fname)];
    });
    parts += subSection('E. 输入输出文件清单',
      `<details open>
        <summary style="font-weight:600; cursor:pointer; padding:6pt 0; color:#1e3a5f;">数据文件清单（共 ${sourceFiles.length} 个文件，点击折叠）</summary>
        <p class="note" style="margin-top:6pt;">以下为生成本报告所使用的输入与输出文件清单，实际数据已汇总至报告各章节。文件名称仅用于技术追溯。</p>` +
      dataTable(cols, data, ['left', 'left']) +
      `</details>`
    );
  }

  // F. assumptions
  const assumptions = payload.assumptions;
  if (assumptions && Object.keys(assumptions).length > 0) {
    parts += subSection('F. 计算假设条件', kvTable([
      ['电价年份', assumptions.tariff_year],
      ['贴现率', assumptions.discount_rate != null ? pct(assumptions.discount_rate) : null],
      ['项目寿命', assumptions.project_life_years != null ? `${num(assumptions.project_life_years, 0)} 年` : null],
      ['SOC 使用范围', assumptions.soc_min != null && assumptions.soc_max != null ? `${pct(assumptions.soc_min)} ~ ${pct(assumptions.soc_max)}` : null],
      ['OpenDSS 启用', assumptions.opendss_enabled ? '是' : '否'],
      ['终端 SOC 模式', classifyLabel(String(assumptions.terminal_soc_mode ?? '')) || '--'],
      ['安全-经济权衡系数', assumptions.safety_economy_tradeoff != null ? num(assumptions.safety_economy_tradeoff, 2) : null],
    ], '35%', true));
  }

  // G. data quality
  const dq = payload.data_quality;
  if (dq) {
    let dqHtml = '';
    if (dq.missing_data_flags?.length) {
      dqHtml += `<p><strong>缺失数据：</strong>${esc(dq.missing_data_flags.join('、'))}</p>`;
    }
    if (dq.degraded_calculations?.length) {
      dqHtml += `<p><strong>降级计算：</strong>${esc(dq.degraded_calculations.join('、'))}</p>`;
    }
    dqHtml += `<p><strong>OpenDSS 启用：</strong>${dq.opendss_enabled ? '是' : '否'}</p>`;
    if (dq.trace_completeness) {
      dqHtml += `<p><strong>时序仿真轨迹（Trace）完整度：</strong>${esc(dq.trace_completeness)}</p>`;
    }
    if (!dqHtml) dqHtml = '<p>无异常数据质量标记。</p>';
    parts += subSection('G. 数据质量说明', dqHtml);
  }

  return section('附件', parts);
}

// ====================================================================
// main export
// ====================================================================

export function buildProposalHtml(payload: ReportPayload): string {
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>储能系统技术经济评价报告 — ${esc(payload.project_meta?.project_name || '未命名项目')}</title>
  <style>${CSS}</style>
</head>
<body>
  ${buildCover(payload)}
  <main>
    ${buildToc()}
    ${buildExecutiveSummary(payload)}
    ${buildProjectOverview(payload)}
    ${buildTechnicalSolution(payload)}
    ${buildControlStrategy(payload)}
    ${buildEconomicAnalysis(payload)}
    ${buildSafetyGridImpact(payload)}
    ${buildImplementationPlan(payload)}
    ${buildRiskManagement(payload)}
    ${buildDisclaimer(payload)}
    ${buildAppendices(payload)}
  </main>
</body>
</html>`;
}
