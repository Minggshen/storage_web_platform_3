import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  fetchBuildManifest,
  fetchBuildPreview,
  fetchGridHealth,
  triggerBuild,
  type BuildManifest,
  type BuildPreviewResponse,
  type GridHealthResponse,
} from '../../services/build';
import { Button } from '@/components/ui/button';

export default function BuildPage() {
  const { projectId = '' } = useParams();
  const [loading, setLoading] = useState(false);
  const [building, setBuilding] = useState(false);
  const [checkingHealth, setCheckingHealth] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<BuildPreviewResponse | null>(null);
  const [manifest, setManifest] = useState<BuildManifest | null>(null);
  const [gridHealth, setGridHealth] = useState<GridHealthResponse | null>(null);
  const [serviceLineFilter, setServiceLineFilter] = useState<'all' | 'large' | 'small'>('all');

  async function loadAll() {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const [previewData, manifestData] = await Promise.allSettled([
        fetchBuildPreview(projectId),
        fetchBuildManifest(projectId),
      ]);
      if (previewData.status === 'fulfilled') setPreview(previewData.value);
      if (manifestData.status === 'fulfilled') setManifest(manifestData.value);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function onBuild() {
    if (!projectId) return;
    setBuilding(true);
    setError(null);
    try {
      const result = await triggerBuild(projectId);
      setManifest(result.manifest);
      const previewData = await fetchBuildPreview(projectId);
      setPreview(previewData);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBuilding(false);
    }
  }

  async function onCheckHealth() {
    if (!projectId) return;
    setCheckingHealth(true);
    setError(null);
    try {
      const result = await fetchGridHealth(projectId);
      setGridHealth(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCheckingHealth(false);
    }
  }

  useEffect(() => {
    void loadAll();
  }, [projectId]);

  const workspace = manifest?.solver_workspace;
  const compileSummary = manifest?.dss_compile_summary;
  const structuralChecks = compileSummary?.structural_checks;
  const compileProbe = compileSummary?.opendss_probe;
  const autoServiceLines = (compileSummary?.line_summary ?? [])
    .filter((item) => Boolean(item.auto_service_line))
    .sort((a, b) => String(a.name ?? a.id ?? '').localeCompare(String(b.name ?? b.id ?? ''), 'zh-CN'));
  const filteredAutoServiceLines = autoServiceLines.filter((item) => {
    const sizeClass = classifyServiceLineSize(autoServiceLines, item.normamps);
    if (serviceLineFilter === 'large') return sizeClass === 'large';
    if (serviceLineFilter === 'small') return sizeClass === 'small';
    return true;
  });
  const capacityProblemLines = (compileSummary?.line_summary ?? [])
    .filter((item) => item.capacity_check_status === 'insufficient')
    .sort((a, b) => String(a.name ?? a.id ?? '').localeCompare(String(b.name ?? b.id ?? ''), 'zh-CN'));
  const warnings = preview?.summary.warnings ?? manifest?.warnings ?? [];
  const errors = preview?.summary.errors ?? manifest?.errors ?? [];
  const workspaceWarnings = workspace?.warnings ?? [];
  const workspaceErrors = workspace?.errors ?? [];

  return (
    <div className="min-h-screen bg-background p-5">
      <div className="mx-auto max-w-[1600px]">
        <div className="mb-4">
          <Link to="/projects" className="font-semibold text-primary no-underline hover:underline">
            &larr; 返回项目列表
          </Link>
        </div>

        {/* Hero */}
        <section className="mb-4 rounded-2xl border border-border bg-card p-5">
          <div className="mb-2 text-xs text-muted-foreground">构建与校验</div>
          <h1 className="m-0 text-[30px] font-extrabold tracking-tight text-foreground">Build 阶段 Solver Workspace 生成</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            将前端可视化拓扑、资产绑定与运行输入编译为求解器可直接调用的工作目录。
          </p>
          <div className="mt-2.5 text-sm text-muted-foreground">项目 ID：{projectId}</div>
        </section>

        {/* Action buttons */}
        <div className="mb-4 flex gap-3 flex-wrap">
          <Button variant="outline" size="sm" asChild>
            <Link to={`/projects/${projectId}/topology`}>返回拓扑建模</Link>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link to={`/projects/${projectId}/solver`}>进入计算运行</Link>
          </Button>
          <Button variant="outline" size="sm" onClick={() => void loadAll()} disabled={loading}>
            {loading ? '刷新中...' : '刷新'}
          </Button>
          <Button variant="outline" size="sm" onClick={() => void onCheckHealth()} disabled={checkingHealth}>
            {checkingHealth ? '检查中...' : '电网健康检查'}
          </Button>
          <Button size="sm" onClick={() => void onBuild()} disabled={building}>
            {building ? '构建中...' : '生成 Solver Workspace'}
          </Button>
        </div>

        {error ? (
          <div className="mb-3 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-600">
            错误：{error}
          </div>
        ) : null}

        {/* Stat cards */}
        <div className="mb-4 grid grid-cols-4 gap-4">
          <StatCard title="ready_for_build" value={String(preview?.summary.ready_for_build ?? manifest?.ready_for_build ?? false)} />
          <StatCard title="warnings" value={String(warnings.length)} />
          <StatCard title="errors" value={String(errors.length)} />
          <StatCard title="ready_for_solver" value={String(workspace?.ready_for_solver ?? false)} />
        </div>

        {/* Preview + Workspace */}
        <div className="mb-4 grid gap-4 items-start" style={{ gridTemplateColumns: '1.2fr 1fr' }}>
          {/* Build Preview */}
          <section className="rounded-2xl border border-border bg-card p-4">
            <h2 className="mb-3.5 mt-0 text-xl font-bold text-foreground">构建预览</h2>
            {preview ? (
              <>
                <SummaryRow label="项目名称" value={preview.summary.project_name} />
                <SummaryRow label="节点数" value={String(preview.summary.node_count)} />
                <SummaryRow label="线路数" value={String(preview.summary.edge_count)} />
                <SummaryRow label="电源节点" value={String(preview.summary.grid_count ?? 0)} />
                <SummaryRow label="主变节点" value={String(preview.summary.transformer_count ?? 0)} />
                <SummaryRow label="负荷节点" value={String(preview.summary.load_count ?? 0)} />
                <SummaryRow label="闭合线路" value={String(preview.summary.active_edge_count ?? 0)} />
                <SummaryRow label="未连通节点" value={String(preview.summary.disconnected_count ?? 0)} />
                <SummaryRow label="可构建" value={String(preview.summary.ready_for_build)} />
              </>
            ) : (
              <div className="text-muted-foreground">暂无预览数据。</div>
            )}
            <div className="mt-4"><MiniTitle>Warnings</MiniTitle>
              {warnings.length ? <ul className="m-0 pl-4.5 text-foreground/80 leading-relaxed">{warnings.map((item) => <li key={item}>{item}</li>)}</ul> : <div className="text-muted-foreground">无。</div>}
            </div>
            <div className="mt-3"><MiniTitle>Errors</MiniTitle>
              {errors.length ? <ul className="m-0 pl-4.5 text-foreground/80 leading-relaxed">{errors.map((item) => <li key={item}>{item}</li>)}</ul> : <div className="text-muted-foreground">无。</div>}
            </div>
          </section>

          {/* Solver Workspace */}
          <section className="rounded-2xl border border-border bg-card p-4">
            <h2 className="mb-3.5 mt-0 text-xl font-bold text-foreground">求解器工作目录</h2>
            {manifest ? (
              <>
                <SummaryRow label="DSS 目录" value={manifest.dss_dir} />
                <SummaryRow label="Master.dss" value={manifest.dss_master_path} />
                <SummaryRow label="workspace" value={workspace?.workspace_dir ?? '--'} />
                <SummaryRow label="ready_for_solver" value={String(workspace?.ready_for_solver ?? false)} />
                <SummaryRow label="registry 行数" value={String(workspace?.registry_row_count ?? 0)} />
                <div className="mt-4"><MiniTitle>生成文件</MiniTitle>
                  {manifest.dss_files?.length ? <ul className="m-0 pl-4.5 text-foreground/80 leading-relaxed">{manifest.dss_files.map((item) => <li key={item}>{item}</li>)}</ul> : <div className="text-muted-foreground">暂无文件。</div>}
                </div>
                <div className="mt-4"><MiniTitle>Solver 输入</MiniTitle>
                  <SummaryRow label="node_registry.xlsx" value={workspace?.registry_path ?? '--'} />
                  <SummaryRow label="设备策略库" value={workspace?.strategy_library_path ?? '--'} />
                  <SummaryRow label="电价文件" value={workspace?.tariff_path ?? '--'} />
                  <SummaryRow label="CLI 参数" value={workspace?.solver_command?.args?.join(' ') ?? '--'} />
                </div>
                <div className="mt-4"><MiniTitle>Workspace Warnings</MiniTitle>
                  {workspaceWarnings.length ? <ul className="m-0 pl-4.5 text-foreground/80 leading-relaxed">{workspaceWarnings.map((item) => <li key={item}>{item}</li>)}</ul> : <div className="text-muted-foreground">无。</div>}
                </div>
                <div className="mt-3"><MiniTitle>Workspace Errors</MiniTitle>
                  {workspaceErrors.length ? <ul className="m-0 pl-4.5 text-foreground/80 leading-relaxed">{workspaceErrors.map((item) => <li key={item}>{item}</li>)}</ul> : <div className="text-muted-foreground">无。</div>}
                </div>
              </>
            ) : (
              <div className="text-muted-foreground">尚未生成 build manifest。</div>
            )}
          </section>
        </div>

        {/* DSS Structure Checks + OpenDSS Probe */}
        <div className="mb-4 grid grid-cols-2 gap-4">
          <section className="rounded-2xl border border-border bg-card p-4">
            <div className="mb-3.5 flex items-center justify-between gap-3">
              <h2 className="m-0 text-xl font-bold text-foreground">DSS 结构自检</h2>
              <LocalBadge
                tone={structuralChecks?.passed ? 'good' : 'warn'}
                text={structuralChecks ? (structuralChecks.passed ? '通过' : '存在问题') : '未生成'}
              />
            </div>
            {structuralChecks ? (
              <>
                <div className="mb-3 grid grid-cols-3 gap-3">
                  <MiniMetric label="检查项" value={String(structuralChecks.checks?.length ?? 0)} />
                  <MiniMetric label="Warnings" value={String(structuralChecks.warnings?.length ?? 0)} />
                  <MiniMetric label="Errors" value={String(structuralChecks.errors?.length ?? 0)} />
                </div>
                {(structuralChecks.checks ?? []).length ? (
                  <div className="flex flex-col gap-2.5">
                    {(structuralChecks.checks ?? []).map((item, i) => (
                      <div key={`${item.name ?? 'check'}_${i}`} className="grid gap-2.5 items-start rounded-xl border border-border bg-muted/30 p-3" style={{ gridTemplateColumns: 'auto 1fr' }}>
                        <LocalBadge tone={item.status === 'pass' ? 'good' : 'warn'} text={item.status === 'pass' ? 'PASS' : 'FAIL'} />
                        <div className="min-w-0">
                          <div className="font-bold text-foreground">{item.name ?? `check_${i + 1}`}</div>
                          <div className="mt-0.5 text-sm text-muted-foreground break-words">{item.detail ?? '--'}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : <div className="text-muted-foreground">暂无结构检查项。</div>}
                <div className="mt-4"><MiniTitle>结构 Warnings</MiniTitle>
                  {structuralChecks.warnings?.length ? <ul className="m-0 pl-4.5 text-foreground/80 leading-relaxed">{structuralChecks.warnings.map((item) => <li key={item}>{item}</li>)}</ul> : <div className="text-muted-foreground">无。</div>}
                </div>
                <div className="mt-3"><MiniTitle>结构 Errors</MiniTitle>
                  {structuralChecks.errors?.length ? <ul className="m-0 pl-4.5 text-foreground/80 leading-relaxed">{structuralChecks.errors.map((item) => <li key={item}>{item}</li>)}</ul> : <div className="text-muted-foreground">无。</div>}
                </div>
              </>
            ) : (
              <div className="text-muted-foreground">尚未生成 dss_compile_summary。</div>
            )}
          </section>

          <section className="rounded-2xl border border-border bg-card p-4">
            <div className="mb-3.5 flex items-center justify-between gap-3">
              <h2 className="m-0 text-xl font-bold text-foreground">OpenDSS 实编译探测</h2>
              <LocalBadge tone={probeTone(compileProbe?.status)} text={probeLabel(compileProbe?.status)} />
            </div>
            {compileProbe ? (
              <>
                <SummaryRow label="探测模式" value={compileProbe.mode ?? '--'} />
                <SummaryRow label="引擎" value={compileProbe.engine ?? '--'} />
                <SummaryRow label="已尝试" value={String(Boolean(compileProbe.attempted))} />
                <SummaryRow label="Compile 成功" value={String(Boolean(compileProbe.compile_succeeded))} />
                <SummaryRow label="Solve 已执行" value={String(Boolean(compileProbe.solve_executed))} />
                <SummaryRow label="潮流收敛" value={String(Boolean(compileProbe.solve_converged))} />
                <SummaryRow label="Circuit 名称" value={compileProbe.circuit_name ?? '--'} />
                <SummaryRow label="Bus 数" value={String(compileProbe.bus_count ?? 0)} />
                <SummaryRow label="Line 数" value={String(compileProbe.line_count ?? 0)} />
                <SummaryRow label="Load 数" value={String(compileProbe.load_count ?? 0)} />
                <SummaryRow label="说明" value={compileProbe.message ?? '--'} />
                <div className="mt-4"><MiniTitle>Compile Result</MiniTitle><MonoBlock text={compileProbe.compile_result || '空'} /></div>
                <div className="mt-3"><MiniTitle>Solve Result</MiniTitle><MonoBlock text={compileProbe.solve_result || '空'} /></div>
                {compileProbe.stderr_tail ? <div className="mt-3"><MiniTitle>stderr</MiniTitle><MonoBlock text={compileProbe.stderr_tail} /></div> : null}
              </>
            ) : (
              <div className="text-muted-foreground">尚未生成 probe 结果。</div>
            )}
          </section>
        </div>

        {/* Grid Health */}
        {gridHealth ? (
          <section className="mb-4 rounded-2xl border border-border bg-card p-4">
            <div className="mb-3.5 flex items-center justify-between gap-3">
              <h2 className="m-0 text-xl font-bold text-foreground">电网健康检查</h2>
              <LocalBadge tone={gridHealth.grid_health.passed ? 'good' : 'warn'} text={gridHealth.grid_health.passed ? '通过' : '存在问题'} />
            </div>
            <div className="mb-3 grid grid-cols-3 gap-3">
              <MiniMetric label="变压器数" value={String(gridHealth.grid_health.summary.transformer_count)} />
              <MiniMetric label="过载变压器" value={String(trunc(gridHealth.grid_health.summary.overloaded_transformer_count))} />
              <MiniMetric label="总负荷 kW" value={String(Math.round(gridHealth.grid_health.summary.total_load_kw))} />
              <MiniMetric label="总负荷 kvar" value={String(Math.round(gridHealth.grid_health.summary.total_load_kvar))} />
            </div>
            {gridHealth.grid_health.checks.length ? (
              <div className="mt-4"><MiniTitle>检查项</MiniTitle>
                <div className="flex flex-col gap-2.5">
                  {gridHealth.grid_health.checks.map((item, i) => (
                    <div key={`${item.name}_${i}`} className="grid gap-2.5 items-start rounded-xl border border-border bg-muted/30 p-3" style={{ gridTemplateColumns: 'auto 1fr' }}>
                      <LocalBadge tone={item.status === 'pass' ? 'good' : 'warn'} text={item.status === 'pass' ? 'PASS' : 'FAIL'} />
                      <div className="min-w-0">
                        <div className="font-bold text-foreground">{item.name}</div>
                        <div className="mt-0.5 text-sm text-muted-foreground break-words">{item.detail}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            {gridHealth.grid_health.warnings.length ? <div className="mt-4"><MiniTitle>Warnings</MiniTitle><ul className="m-0 pl-4.5 text-foreground/80 leading-relaxed">{gridHealth.grid_health.warnings.map((item, i) => <li key={i}>{item}</li>)}</ul></div> : null}
            {gridHealth.grid_health.errors.length ? <div className="mt-4"><MiniTitle>Errors</MiniTitle><ul className="m-0 pl-4.5 text-foreground/80 leading-relaxed">{gridHealth.grid_health.errors.map((item, i) => <li key={i}>{item}</li>)}</ul></div> : null}
            {gridHealth.grid_health.recommendations.length ? (
              <div className="mt-4"><MiniTitle>改进建议</MiniTitle>
                <div className="flex flex-col gap-3">
                  {gridHealth.grid_health.recommendations.map((rec, i) => (
                    <div key={i} className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3">
                      <div className="mb-1.5 font-bold text-amber-900">
                        {rec.type === 'transformer_overload' ? '\u26A0\uFE0F 变压器过载' : rec.type === 'tap_adjustment' ? '\uD83D\uDD27 分接头调整' : rec.type === 'reactive_compensation' ? '\u26A1 无功补偿' : '\uD83D\uDCA1 建议'}
                        {rec.node_id ? ` - ${rec.node_id}` : ''}
                      </div>
                      <div className="leading-relaxed text-amber-900/80">{rec.message}</div>
                      {rec.rated_kva !== undefined && rec.load_kva !== undefined && rec.loading_pct !== undefined ? (
                        <div className="mt-2 text-xs text-amber-900/70">
                          额定: {Math.round(rec.rated_kva)} kVA | 实际: {Math.round(rec.load_kva)} kVA | 负载率: {rec.loading_pct.toFixed(1)}%
                        </div>
                      ) : null}
                      {rec.current_tap !== undefined && rec.recommended_tap !== undefined ? (
                        <div className="mt-2 text-xs text-amber-900/70">
                          当前分接头: {rec.current_tap} &rarr; 建议: {rec.recommended_tap}
                        </div>
                      ) : null}
                      {rec.total_load_kvar !== undefined && rec.recommended_kvar !== undefined ? (
                        <div className="mt-2 text-xs text-amber-900/70">
                          总无功负荷: {Math.round(rec.total_load_kvar)} kvar | 建议补偿: {Math.round(rec.recommended_kvar)} kvar
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </section>
        ) : null}

        {/* Auto Service Lines */}
        <section className="mb-4 rounded-2xl border border-border bg-card p-4">
          <div className="mb-3.5 flex items-center justify-between gap-3">
            <h2 className="m-0 text-xl font-bold text-foreground">自动估算接入线</h2>
            <LocalBadge tone={autoServiceLines.length ? 'good' : 'neutral'} text={autoServiceLines.length ? `${autoServiceLines.length} 条` : '暂无'} />
          </div>
          <div className="mb-3 text-sm text-muted-foreground leading-relaxed">
            这里列出"用户配变低压侧到负荷/资源接入点"的自动估算结果。系统会综合参考用户配变容量和接入规模，给出额定电流与应急电流。
          </div>
          {autoServiceLines.length ? (
            <div className="mb-3 flex gap-2 items-center flex-wrap">
              <button type="button" onClick={() => setServiceLineFilter('all')} className={serviceLineFilter === 'all' ? 'inline-flex items-center justify-center rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-xs font-semibold text-blue-600' : 'inline-flex items-center justify-center rounded-full border border-border bg-card px-3 py-2 text-xs font-semibold text-foreground/80 cursor-pointer'}>全部</button>
              <button type="button" onClick={() => setServiceLineFilter('large')} className={serviceLineFilter === 'large' ? 'inline-flex items-center justify-center rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-xs font-semibold text-blue-600' : 'inline-flex items-center justify-center rounded-full border border-border bg-card px-3 py-2 text-xs font-semibold text-foreground/80 cursor-pointer'}>仅看偏大</button>
              <button type="button" onClick={() => setServiceLineFilter('small')} className={serviceLineFilter === 'small' ? 'inline-flex items-center justify-center rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-xs font-semibold text-blue-600' : 'inline-flex items-center justify-center rounded-full border border-border bg-card px-3 py-2 text-xs font-semibold text-foreground/80 cursor-pointer'}>仅看偏小</button>
              <span className="text-xs text-muted-foreground self-center">偏大/偏小按本项目自动接入线额定电流的前 20% / 后 20% 相对筛选。</span>
            </div>
          ) : null}
          {filteredAutoServiceLines.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[860px] border-collapse">
                <thead>
                  <tr>
                    {['线路','相对分组','起止母线','线路/等值方式','额定电流','应急电流','等值阻抗','估算依据'].map((h) => (
                      <th key={h} className="text-left text-xs text-muted-foreground bg-muted/50 border-b border-border px-3 py-2.5 whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredAutoServiceLines.map((item) => (
                    <tr key={String(item.id ?? item.name ?? `${item.from_bus}_${item.to_bus}`)}>
                      <Cell>{String(item.name ?? item.id ?? '--')}</Cell>
                      <Cell>{serviceLineSizeLabel(classifyServiceLineSize(autoServiceLines, item.normamps))}</Cell>
                      <Cell>{`${item.from_bus ?? '--'} -> ${item.to_bus ?? '--'}`}</Cell>
                      <Cell>{item.service_cable_name ? `${item.service_cable_name} \u00D7 ${item.service_cable_parallel ?? 1}` : String(item.linecode ?? '--')}</Cell>
                      <Cell>{formatAmp(item.normamps)}</Cell>
                      <Cell>{formatAmp(item.emergamps)}</Cell>
                      <Cell>{formatOhmPerKm(item.service_equivalent_r1_ohm_per_km, item.service_equivalent_x1_ohm_per_km)}</Cell>
                      <Cell>{`配变 ${formatKva(item.service_transformer_kva)} / 接入规模 ${formatKva(item.service_resource_kva)} / ${formatKv(item.service_secondary_kv)}`}</Cell>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-muted-foreground">
              {autoServiceLines.length ? '当前筛选条件下没有匹配的自动接入线。' : '当前 build 摘要里没有识别到自动估算的低压接入线。'}
            </div>
          )}
        </section>

        {/* Capacity Recommendations */}
        <section className="mb-4 rounded-2xl border border-border bg-card p-4">
          <div className="mb-3.5 flex items-center justify-between gap-3">
            <h2 className="m-0 text-xl font-bold text-foreground">线路承载能力建议</h2>
            <LocalBadge tone={capacityProblemLines.length ? 'warn' : 'good'} text={capacityProblemLines.length ? `${capacityProblemLines.length} 条需关注` : '未发现超额定'} />
          </div>
          <div className="mb-3 text-sm text-muted-foreground leading-relaxed">
            该表按拓扑方向汇总下游配变/负荷容量，估算线路额定电流是否够用；实际最终是否过载仍以 OpenDSS 潮流结果为准。
          </div>
          {capacityProblemLines.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[860px] border-collapse">
                <thead>
                  <tr>
                    {['线路','起止母线','电压等级','当前额定','估算需求','建议'].map((h) => (
                      <th key={h} className="text-left text-xs text-muted-foreground bg-muted/50 border-b border-border px-3 py-2.5 whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {capacityProblemLines.map((item) => (
                    <tr key={String(item.id ?? item.name ?? `${item.from_bus}_${item.to_bus}`)}>
                      <Cell>{String(item.name ?? item.id ?? '--')}</Cell>
                      <Cell>{`${item.from_bus ?? '--'} -> ${item.to_bus ?? '--'}`}</Cell>
                      <Cell>{formatKv(item.line_voltage_kv)}</Cell>
                      <Cell>{formatAmp(item.normamps)}</Cell>
                      <Cell>{formatAmp(item.estimated_required_current_a)}</Cell>
                      <Cell>{`${formatAmp(item.recommended_current_a)} / ${item.recommended_linecode ?? '--'}`}</Cell>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="text-muted-foreground">当前 build 摘要未发现额定电流低于下游容量估算值的线路。</div>}
        </section>

        {/* Textarea previews */}
        <div className="grid grid-cols-2 gap-4">
          <section className="rounded-2xl border border-border bg-card p-4">
            <h2 className="mb-3.5 mt-0 text-xl font-bold text-foreground">Master.dss 预览</h2>
            <textarea value={manifest?.dss_master_preview ?? ''} readOnly spellCheck={false} className="w-full min-h-[360px] rounded-xl border border-border bg-muted/30 p-3 font-mono text-xs leading-relaxed resize-y box-border overscroll-contain" />
          </section>
          <section className="rounded-2xl border border-border bg-card p-4">
            <h2 className="mb-3.5 mt-0 text-xl font-bold text-foreground">dss_compile_summary.json</h2>
            <textarea value={manifest ? JSON.stringify(manifest.dss_compile_summary ?? {}, null, 2) : ''} readOnly spellCheck={false} className="w-full min-h-[360px] rounded-xl border border-border bg-muted/30 p-3 font-mono text-xs leading-relaxed resize-y box-border overscroll-contain" />
          </section>
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ──

function Cell({ children }: { children: React.ReactNode }) {
  return <td className="text-[13px] text-foreground border-b border-muted px-3 py-2.5 align-top">{children}</td>;
}

function MiniTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-2 mt-0 text-[15px] font-semibold text-foreground">{children}</h3>;
}

function StatCard(props: { title: string; value: string }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4">
      <div className="mb-2.5 text-[13px] text-muted-foreground">{props.title}</div>
      <div className="text-xl font-extrabold text-foreground">{props.value}</div>
    </div>
  );
}

function SummaryRow(props: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3 border-b border-border py-2">
      <span className="text-muted-foreground min-w-[120px]">{props.label}</span>
      <strong className="text-right break-all">{props.value}</strong>
    </div>
  );
}

function MiniMetric(props: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-muted/30 p-3">
      <div className="text-xs text-muted-foreground">{props.label}</div>
      <div className="mt-1.5 text-lg font-extrabold text-foreground">{props.value}</div>
    </div>
  );
}

function MonoBlock({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-border bg-muted/30 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap break-words">
      {text}
    </div>
  );
}

function LocalBadge(props: { tone: 'good' | 'warn' | 'neutral'; text: string }) {
  return (
    <span className={
      props.tone === 'good'
        ? 'inline-flex items-center justify-center min-w-[58px] h-7 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 text-xs font-bold text-emerald-600 box-border'
        : props.tone === 'warn'
          ? 'inline-flex items-center justify-center min-w-[58px] h-7 rounded-full border border-red-500/30 bg-red-500/10 px-2.5 text-xs font-bold text-red-600 box-border'
          : 'inline-flex items-center justify-center min-w-[58px] h-7 rounded-full border border-border bg-muted px-2.5 text-xs font-bold text-muted-foreground box-border'
    }>
      {props.text}
    </span>
  );
}

// ── Utility functions (unchanged) ──

function probeTone(status?: string): 'good' | 'warn' | 'neutral' {
  if (status === 'passed') return 'good';
  if (status === 'failed') return 'warn';
  return 'neutral';
}

function probeLabel(status?: string): string {
  if (status === 'passed') return '通过';
  if (status === 'failed') return '失败';
  if (status === 'skipped') return '已跳过';
  return '未生成';
}

function formatAmp(value?: number | null) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return '--';
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 10000 ? 1 : 2)} kA`;
  return `${Math.round(value)} A`;
}

function formatKva(value?: number | null) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return '--';
  return `${Math.round(value)} kVA`;
}

function formatKv(value?: number | null) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return '--';
  return `${value.toFixed(value < 1 ? 3 : 2)} kV`;
}

function formatOhmPerKm(r1?: number | null, x1?: number | null) {
  const hasR = typeof r1 === 'number' && Number.isFinite(r1);
  const hasX = typeof x1 === 'number' && Number.isFinite(x1);
  if (!hasR && !hasX) return '--';
  return `R1 ${hasR ? r1.toFixed(5) : '--'} / X1 ${hasX ? x1.toFixed(5) : '--'} \u03A9/km`;
}

function classifyServiceLineSize(rows: Array<{ normamps?: number | null }>, current?: number | null): 'large' | 'small' | 'normal' {
  const value = typeof current === 'number' && Number.isFinite(current) ? current : null;
  if (value === null) return 'normal';
  const samples = rows.map((item) => item.normamps).filter((item): item is number => typeof item === 'number' && Number.isFinite(item)).sort((a, b) => a - b);
  if (!samples.length) return 'normal';
  const lowerIndex = Math.floor((samples.length - 1) * 0.2);
  const upperIndex = Math.ceil((samples.length - 1) * 0.8);
  const lower = samples[Math.max(0, lowerIndex)];
  const upper = samples[Math.min(samples.length - 1, upperIndex)];
  if (value <= lower) return 'small';
  if (value >= upper) return 'large';
  return 'normal';
}

function serviceLineSizeLabel(level: 'large' | 'small' | 'normal') {
  if (level === 'large') return '项目内偏大';
  if (level === 'small') return '项目内偏小';
  return '项目内常规';
}

function trunc(v: number) { return String(v); }
