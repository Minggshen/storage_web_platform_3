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

      if (previewData.status === 'fulfilled') {
        setPreview(previewData.value);
      }

      if (manifestData.status === 'fulfilled') {
        setManifest(manifestData.value);
      }
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    <div style={{ padding: 20, background: '#f8fafc', minHeight: '100vh' }}>
      <div style={{ maxWidth: 1600, margin: '0 auto' }}>
        <div style={{ marginBottom: 16 }}>
          <Link to="/projects" style={{ color: '#2563eb', textDecoration: 'none', fontWeight: 600 }}>
            ← 返回项目列表
          </Link>
        </div>

        <section style={heroStyle}>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 8 }}>构建与校验</div>
          <h1 style={{ margin: 0, fontSize: 30 }}>Build 阶段 Solver Workspace 生成</h1>
          <div style={{ color: '#6b7280', marginTop: 8 }}>
            将前端可视化拓扑、资产绑定与运行输入编译为求解器可直接调用的工作目录。
          </div>
          <div style={{ color: '#6b7280', marginTop: 10 }}>项目 ID：{projectId}</div>
        </section>

        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
          <Link to={`/projects/${projectId}/topology`} style={secondaryBtnStyle}>
            返回拓扑建模
          </Link>
          <Link to={`/projects/${projectId}/solver`} style={secondaryBtnStyle}>
            进入计算运行
          </Link>
          <button type="button" style={secondaryBtnStyle} onClick={() => void loadAll()} disabled={loading}>
            {loading ? '刷新中...' : '刷新'}
          </button>
          <button type="button" style={secondaryBtnStyle} onClick={() => void onCheckHealth()} disabled={checkingHealth}>
            {checkingHealth ? '检查中...' : '电网健康检查'}
          </button>
          <button type="button" style={primaryBtnStyle} onClick={() => void onBuild()} disabled={building}>
            {building ? '构建中...' : '生成 Solver Workspace'}
          </button>
        </div>

        {error ? <div style={errorStyle}>错误：{error}</div> : null}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 16, marginBottom: 16 }}>
          <StatCard title="ready_for_build" value={String(preview?.summary.ready_for_build ?? manifest?.ready_for_build ?? false)} />
          <StatCard title="warnings" value={String(warnings.length)} />
          <StatCard title="errors" value={String(errors.length)} />
          <StatCard title="ready_for_solver" value={String(workspace?.ready_for_solver ?? false)} />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 16, alignItems: 'start' }}>
          <section style={cardStyle}>
            <h2 style={sectionTitleStyle}>构建预览</h2>
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
              <div style={{ color: '#6b7280' }}>暂无预览数据。</div>
            )}

            <div style={{ marginTop: 16 }}>
              <h3 style={miniTitleStyle}>Warnings</h3>
              {warnings.length ? (
                <ul style={listStyle}>
                  {warnings.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : (
                <div style={{ color: '#64748b' }}>无。</div>
              )}
            </div>

            <div style={{ marginTop: 12 }}>
              <h3 style={miniTitleStyle}>Errors</h3>
              {errors.length ? (
                <ul style={listStyle}>
                  {errors.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : (
                <div style={{ color: '#64748b' }}>无。</div>
              )}
            </div>
          </section>

          <section style={cardStyle}>
            <h2 style={sectionTitleStyle}>求解器工作目录</h2>
            {manifest ? (
              <>
                <SummaryRow label="DSS 目录" value={manifest.dss_dir} />
                <SummaryRow label="Master.dss" value={manifest.dss_master_path} />
                <SummaryRow label="workspace" value={workspace?.workspace_dir ?? '--'} />
                <SummaryRow label="ready_for_solver" value={String(workspace?.ready_for_solver ?? false)} />
                <SummaryRow label="registry 行数" value={String(workspace?.registry_row_count ?? 0)} />

                <div style={{ marginTop: 16 }}>
                  <h3 style={miniTitleStyle}>生成文件</h3>
                  {manifest.dss_files?.length ? (
                    <ul style={listStyle}>
                      {manifest.dss_files.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <div style={{ color: '#64748b' }}>暂无文件。</div>
                  )}
                </div>

                <div style={{ marginTop: 16 }}>
                  <h3 style={miniTitleStyle}>Solver 输入</h3>
                  <SummaryRow label="node_registry.xlsx" value={workspace?.registry_path ?? '--'} />
                  <SummaryRow label="设备策略库" value={workspace?.strategy_library_path ?? '--'} />
                  <SummaryRow label="电价文件" value={workspace?.tariff_path ?? '--'} />
                  <SummaryRow label="CLI 参数" value={workspace?.solver_command?.args?.join(' ') ?? '--'} />
                </div>

                <div style={{ marginTop: 16 }}>
                  <h3 style={miniTitleStyle}>Workspace Warnings</h3>
                  {workspaceWarnings.length ? (
                    <ul style={listStyle}>
                      {workspaceWarnings.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <div style={{ color: '#64748b' }}>无。</div>
                  )}
                </div>

                <div style={{ marginTop: 12 }}>
                  <h3 style={miniTitleStyle}>Workspace Errors</h3>
                  {workspaceErrors.length ? (
                    <ul style={listStyle}>
                      {workspaceErrors.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <div style={{ color: '#64748b' }}>无。</div>
                  )}
                </div>
              </>
            ) : (
              <div style={{ color: '#6b7280' }}>尚未生成 build manifest。</div>
            )}
          </section>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 16 }}>
          <section style={cardStyle}>
            <div style={sectionHeaderStyle}>
              <h2 style={{ ...sectionTitleStyle, margin: 0 }}>DSS 结构自检</h2>
              <StatusBadge
                tone={structuralChecks?.passed ? 'good' : 'warn'}
                text={structuralChecks ? (structuralChecks.passed ? '通过' : '存在问题') : '未生成'}
              />
            </div>

            {structuralChecks ? (
              <>
                <div style={metricRowStyle}>
                  <MiniMetric label="检查项" value={String(structuralChecks.checks?.length ?? 0)} />
                  <MiniMetric label="Warnings" value={String(structuralChecks.warnings?.length ?? 0)} />
                  <MiniMetric label="Errors" value={String(structuralChecks.errors?.length ?? 0)} />
                </div>

                <div style={{ marginTop: 12 }}>
                  {(structuralChecks.checks ?? []).length ? (
                    <div style={checkListStyle}>
                      {(structuralChecks.checks ?? []).map((item, index) => (
                        <div key={`${item.name ?? 'check'}_${index}`} style={checkRowStyle}>
                          <StatusBadge tone={item.status === 'pass' ? 'good' : 'warn'} text={item.status === 'pass' ? 'PASS' : 'FAIL'} />
                          <div style={{ minWidth: 0 }}>
                            <div style={{ fontWeight: 700 }}>{item.name ?? `check_${index + 1}`}</div>
                            <div style={{ color: '#64748b', marginTop: 2, overflowWrap: 'anywhere' }}>{item.detail ?? '--'}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ color: '#64748b' }}>暂无结构检查项。</div>
                  )}
                </div>

                <div style={{ marginTop: 16 }}>
                  <h3 style={miniTitleStyle}>结构 Warnings</h3>
                  {structuralChecks.warnings?.length ? (
                    <ul style={listStyle}>
                      {structuralChecks.warnings.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <div style={{ color: '#64748b' }}>无。</div>
                  )}
                </div>

                <div style={{ marginTop: 12 }}>
                  <h3 style={miniTitleStyle}>结构 Errors</h3>
                  {structuralChecks.errors?.length ? (
                    <ul style={listStyle}>
                      {structuralChecks.errors.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <div style={{ color: '#64748b' }}>无。</div>
                  )}
                </div>
              </>
            ) : (
              <div style={{ color: '#64748b' }}>尚未生成 dss_compile_summary。</div>
            )}
          </section>

          <section style={cardStyle}>
            <div style={sectionHeaderStyle}>
              <h2 style={{ ...sectionTitleStyle, margin: 0 }}>OpenDSS 实编译探测</h2>
              <StatusBadge tone={probeTone(compileProbe?.status)} text={probeLabel(compileProbe?.status)} />
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

                <div style={{ marginTop: 16 }}>
                  <h3 style={miniTitleStyle}>Compile Result</h3>
                  <div style={monoBlockStyle}>{compileProbe.compile_result || '空'}</div>
                </div>

                <div style={{ marginTop: 12 }}>
                  <h3 style={miniTitleStyle}>Solve Result</h3>
                  <div style={monoBlockStyle}>{compileProbe.solve_result || '空'}</div>
                </div>

                {compileProbe.stderr_tail ? (
                  <div style={{ marginTop: 12 }}>
                    <h3 style={miniTitleStyle}>stderr</h3>
                    <div style={monoBlockStyle}>{compileProbe.stderr_tail}</div>
                  </div>
                ) : null}
              </>
            ) : (
              <div style={{ color: '#64748b' }}>尚未生成 probe 结果。</div>
            )}
          </section>
        </div>

        {gridHealth ? (
          <section style={{ ...cardStyle, marginTop: 16 }}>
            <div style={sectionHeaderStyle}>
              <h2 style={{ ...sectionTitleStyle, margin: 0 }}>电网健康检查</h2>
              <StatusBadge
                tone={gridHealth.grid_health.passed ? 'good' : 'warn'}
                text={gridHealth.grid_health.passed ? '通过' : '存在问题'}
              />
            </div>

            <div style={metricRowStyle}>
              <MiniMetric label="变压器数" value={String(gridHealth.grid_health.summary.transformer_count)} />
              <MiniMetric label="过载变压器" value={String(gridHealth.grid_health.summary.overloaded_transformer_count)} />
              <MiniMetric label="总负荷 kW" value={String(Math.round(gridHealth.grid_health.summary.total_load_kw))} />
              <MiniMetric label="总负荷 kvar" value={String(Math.round(gridHealth.grid_health.summary.total_load_kvar))} />
            </div>

            {gridHealth.grid_health.checks.length ? (
              <div style={{ marginTop: 16 }}>
                <h3 style={miniTitleStyle}>检查项</h3>
                <div style={checkListStyle}>
                  {gridHealth.grid_health.checks.map((item, index) => (
                    <div key={`${item.name}_${index}`} style={checkRowStyle}>
                      <StatusBadge tone={item.status === 'pass' ? 'good' : 'warn'} text={item.status === 'pass' ? 'PASS' : 'FAIL'} />
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontWeight: 700 }}>{item.name}</div>
                        <div style={{ color: '#64748b', marginTop: 2, overflowWrap: 'anywhere' }}>{item.detail}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {gridHealth.grid_health.warnings.length ? (
              <div style={{ marginTop: 16 }}>
                <h3 style={miniTitleStyle}>Warnings</h3>
                <ul style={listStyle}>
                  {gridHealth.grid_health.warnings.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {gridHealth.grid_health.errors.length ? (
              <div style={{ marginTop: 16 }}>
                <h3 style={miniTitleStyle}>Errors</h3>
                <ul style={listStyle}>
                  {gridHealth.grid_health.errors.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {gridHealth.grid_health.recommendations.length ? (
              <div style={{ marginTop: 16 }}>
                <h3 style={miniTitleStyle}>改进建议</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {gridHealth.grid_health.recommendations.map((rec, index) => (
                    <div key={index} style={{ border: '1px solid #e5e7eb', borderRadius: 12, padding: 12, background: '#fffbeb' }}>
                      <div style={{ fontWeight: 700, color: '#92400e', marginBottom: 6 }}>
                        {rec.type === 'transformer_overload' ? '⚠️ 变压器过载' : 
                         rec.type === 'tap_adjustment' ? '🔧 分接头调整' : 
                         rec.type === 'reactive_compensation' ? '⚡ 无功补偿' : '💡 建议'}
                        {rec.node_id ? ` - ${rec.node_id}` : ''}
                      </div>
                      <div style={{ color: '#78350f', lineHeight: 1.6 }}>{rec.message}</div>
                      {rec.rated_kva !== undefined && rec.load_kva !== undefined && rec.loading_pct !== undefined ? (
                        <div style={{ marginTop: 8, fontSize: 12, color: '#78350f' }}>
                          额定: {Math.round(rec.rated_kva)} kVA | 实际: {Math.round(rec.load_kva)} kVA | 负载率: {rec.loading_pct.toFixed(1)}%
                        </div>
                      ) : null}
                      {rec.current_tap !== undefined && rec.recommended_tap !== undefined ? (
                        <div style={{ marginTop: 8, fontSize: 12, color: '#78350f' }}>
                          当前分接头: {rec.current_tap} → 建议: {rec.recommended_tap}
                        </div>
                      ) : null}
                      {rec.total_load_kvar !== undefined && rec.recommended_kvar !== undefined ? (
                        <div style={{ marginTop: 8, fontSize: 12, color: '#78350f' }}>
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

        <section style={{ ...cardStyle, marginTop: 16 }}>
          <div style={sectionHeaderStyle}>
            <h2 style={{ ...sectionTitleStyle, margin: 0 }}>自动估算接入线</h2>
            <StatusBadge
              tone={autoServiceLines.length ? 'good' : 'neutral'}
              text={autoServiceLines.length ? `${autoServiceLines.length} 条` : '暂无'}
            />
          </div>

          <div style={{ color: '#64748b', marginBottom: 12, lineHeight: 1.5 }}>
            这里列出“用户配变低压侧到负荷/资源接入点”的自动估算结果。系统会综合参考用户配变容量和接入规模，给出额定电流与应急电流。
          </div>

          {autoServiceLines.length ? (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              <button
                type="button"
                onClick={() => setServiceLineFilter('all')}
                style={serviceLineFilter === 'all' ? activeFilterBtnStyle : filterBtnStyle}
              >
                全部
              </button>
              <button
                type="button"
                onClick={() => setServiceLineFilter('large')}
                style={serviceLineFilter === 'large' ? activeFilterBtnStyle : filterBtnStyle}
              >
                仅看偏大
              </button>
              <button
                type="button"
                onClick={() => setServiceLineFilter('small')}
                style={serviceLineFilter === 'small' ? activeFilterBtnStyle : filterBtnStyle}
              >
                仅看偏小
              </button>
              <div style={{ color: '#64748b', fontSize: 12, alignSelf: 'center' }}>
                偏大/偏小按本项目自动接入线额定电流的前 20% / 后 20% 相对筛选。
              </div>
            </div>
          ) : null}

          {filteredAutoServiceLines.length ? (
            <div style={{ overflowX: 'auto' }}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={tableHeadCellStyle}>线路</th>
                    <th style={tableHeadCellStyle}>相对分组</th>
                    <th style={tableHeadCellStyle}>起止母线</th>
                    <th style={tableHeadCellStyle}>线路/等值方式</th>
                    <th style={tableHeadCellStyle}>额定电流</th>
                    <th style={tableHeadCellStyle}>应急电流</th>
                    <th style={tableHeadCellStyle}>等值阻抗</th>
                    <th style={tableHeadCellStyle}>估算依据</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAutoServiceLines.map((item) => (
                    <tr key={String(item.id ?? item.name ?? `${item.from_bus}_${item.to_bus}`)}>
                      <td style={tableBodyCellStyle}>{String(item.name ?? item.id ?? '--')}</td>
                      <td style={tableBodyCellStyle}>{serviceLineSizeLabel(classifyServiceLineSize(autoServiceLines, item.normamps))}</td>
                      <td style={tableBodyCellStyle}>{`${item.from_bus ?? '--'} -> ${item.to_bus ?? '--'}`}</td>
                      <td style={tableBodyCellStyle}>
                        {item.service_cable_name
                          ? `${item.service_cable_name} × ${item.service_cable_parallel ?? 1}`
                          : String(item.linecode ?? '--')}
                      </td>
                      <td style={tableBodyCellStyle}>{formatAmp(item.normamps)}</td>
                      <td style={tableBodyCellStyle}>{formatAmp(item.emergamps)}</td>
                      <td style={tableBodyCellStyle}>
                        {formatOhmPerKm(item.service_equivalent_r1_ohm_per_km, item.service_equivalent_x1_ohm_per_km)}
                      </td>
                      <td style={tableBodyCellStyle}>
                        {`配变 ${formatKva(item.service_transformer_kva)} / 接入规模 ${formatKva(item.service_resource_kva)} / ${formatKv(item.service_secondary_kv)}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ color: '#64748b' }}>
              {autoServiceLines.length
                ? '当前筛选条件下没有匹配的自动接入线。'
                : '当前 build 摘要里没有识别到自动估算的低压接入线。'}
            </div>
          )}
        </section>

        <section style={{ ...cardStyle, marginTop: 16 }}>
          <div style={sectionHeaderStyle}>
            <h2 style={{ ...sectionTitleStyle, margin: 0 }}>线路承载能力建议</h2>
            <StatusBadge
              tone={capacityProblemLines.length ? 'warn' : 'good'}
              text={capacityProblemLines.length ? `${capacityProblemLines.length} 条需关注` : '未发现超额定'}
            />
          </div>
          <div style={{ color: '#64748b', marginBottom: 12, lineHeight: 1.5 }}>
            该表按拓扑方向汇总下游配变/负荷容量，估算线路额定电流是否够用；实际最终是否过载仍以 OpenDSS 潮流结果为准。
          </div>
          {capacityProblemLines.length ? (
            <div style={{ overflowX: 'auto' }}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={tableHeadCellStyle}>线路</th>
                    <th style={tableHeadCellStyle}>起止母线</th>
                    <th style={tableHeadCellStyle}>电压等级</th>
                    <th style={tableHeadCellStyle}>当前额定</th>
                    <th style={tableHeadCellStyle}>估算需求</th>
                    <th style={tableHeadCellStyle}>建议</th>
                  </tr>
                </thead>
                <tbody>
                  {capacityProblemLines.map((item) => (
                    <tr key={String(item.id ?? item.name ?? `${item.from_bus}_${item.to_bus}`)}>
                      <td style={tableBodyCellStyle}>{String(item.name ?? item.id ?? '--')}</td>
                      <td style={tableBodyCellStyle}>{`${item.from_bus ?? '--'} -> ${item.to_bus ?? '--'}`}</td>
                      <td style={tableBodyCellStyle}>{formatKv(item.line_voltage_kv)}</td>
                      <td style={tableBodyCellStyle}>{formatAmp(item.normamps)}</td>
                      <td style={tableBodyCellStyle}>{formatAmp(item.estimated_required_current_a)}</td>
                      <td style={tableBodyCellStyle}>
                        {`${formatAmp(item.recommended_current_a)} / ${item.recommended_linecode ?? '--'}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ color: '#64748b' }}>当前 build 摘要未发现额定电流低于下游容量估算值的线路。</div>
          )}
        </section>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 16 }}>
          <section style={cardStyle}>
            <h2 style={sectionTitleStyle}>Master.dss 预览</h2>
            <textarea
              value={manifest?.dss_master_preview ?? ''}
              readOnly
              spellCheck={false}
              style={previewAreaStyle}
            />
          </section>

          <section style={cardStyle}>
            <h2 style={sectionTitleStyle}>dss_compile_summary.json</h2>
            <textarea
              value={manifest ? JSON.stringify(manifest.dss_compile_summary ?? {}, null, 2) : ''}
              readOnly
              spellCheck={false}
              style={previewAreaStyle}
            />
          </section>
        </div>
      </div>
    </div>
  );
}

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

function StatCard(props: { title: string; value: string }) {
  return (
    <div style={statCardStyle}>
      <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 10 }}>{props.title}</div>
      <div style={{ fontSize: 20, fontWeight: 800 }}>{props.value}</div>
    </div>
  );
}

function SummaryRow(props: { label: string; value: string }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        gap: 12,
        padding: '8px 0',
        borderBottom: '1px solid #e5e7eb',
      }}
    >
      <span style={{ color: '#6b7280', minWidth: 120 }}>{props.label}</span>
      <strong style={{ textAlign: 'right', wordBreak: 'break-all' }}>{props.value}</strong>
    </div>
  );
}

function MiniMetric(props: { label: string; value: string }) {
  return (
    <div style={miniMetricStyle}>
      <div style={{ fontSize: 12, color: '#64748b' }}>{props.label}</div>
      <div style={{ marginTop: 6, fontWeight: 800, fontSize: 18 }}>{props.value}</div>
    </div>
  );
}

function StatusBadge(props: { tone: 'good' | 'warn' | 'neutral'; text: string }) {
  const style =
    props.tone === 'good'
      ? badgeGoodStyle
      : props.tone === 'warn'
        ? badgeWarnStyle
        : badgeNeutralStyle;
  return <span style={style}>{props.text}</span>;
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
  return `R1 ${hasR ? r1.toFixed(5) : '--'} / X1 ${hasX ? x1.toFixed(5) : '--'} Ω/km`;
}

function classifyServiceLineSize(
  rows: Array<{ normamps?: number | null }>,
  current?: number | null,
): 'large' | 'small' | 'normal' {
  const value = typeof current === 'number' && Number.isFinite(current) ? current : null;
  if (value === null) return 'normal';
  const samples = rows
    .map((item) => item.normamps)
    .filter((item): item is number => typeof item === 'number' && Number.isFinite(item))
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

function serviceLineSizeLabel(level: 'large' | 'small' | 'normal') {
  if (level === 'large') return '项目内偏大';
  if (level === 'small') return '项目内偏小';
  return '项目内常规';
}

const heroStyle: React.CSSProperties = {
  background: '#ffffff',
  border: '1px solid #e5e7eb',
  borderRadius: 16,
  padding: 20,
  marginBottom: 16,
};

const cardStyle: React.CSSProperties = {
  background: '#ffffff',
  border: '1px solid #e5e7eb',
  borderRadius: 16,
  padding: 16,
};

const statCardStyle: React.CSSProperties = {
  background: '#ffffff',
  border: '1px solid #e5e7eb',
  borderRadius: 16,
  padding: 16,
};

const sectionTitleStyle: React.CSSProperties = {
  margin: '0 0 14px 0',
  fontSize: 20,
};

const miniTitleStyle: React.CSSProperties = {
  margin: '0 0 8px 0',
  fontSize: 15,
};

const listStyle: React.CSSProperties = {
  margin: 0,
  paddingLeft: 18,
  color: '#334155',
  lineHeight: 1.7,
};

const sectionHeaderStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 12,
  marginBottom: 14,
};

const metricRowStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
  gap: 12,
};

const miniMetricStyle: React.CSSProperties = {
  border: '1px solid #e5e7eb',
  borderRadius: 12,
  padding: 12,
  background: '#f8fafc',
};

const checkListStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 10,
};

const checkRowStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'auto 1fr',
  gap: 10,
  alignItems: 'start',
  border: '1px solid #e5e7eb',
  borderRadius: 12,
  padding: 12,
  background: '#f8fafc',
};

const badgeBaseStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  minWidth: 58,
  height: 28,
  padding: '0 10px',
  borderRadius: 999,
  fontSize: 12,
  fontWeight: 700,
  boxSizing: 'border-box',
};

const badgeGoodStyle: React.CSSProperties = {
  ...badgeBaseStyle,
  background: '#dcfce7',
  color: '#166534',
  border: '1px solid #86efac',
};

const badgeWarnStyle: React.CSSProperties = {
  ...badgeBaseStyle,
  background: '#fee2e2',
  color: '#b91c1c',
  border: '1px solid #fca5a5',
};

const badgeNeutralStyle: React.CSSProperties = {
  ...badgeBaseStyle,
  background: '#e5e7eb',
  color: '#374151',
  border: '1px solid #d1d5db',
};

const monoBlockStyle: React.CSSProperties = {
  border: '1px solid #d1d5db',
  borderRadius: 12,
  padding: 12,
  fontFamily: 'Consolas, Menlo, Monaco, monospace',
  fontSize: 12,
  lineHeight: 1.5,
  background: '#f8fafc',
  whiteSpace: 'pre-wrap',
  overflowWrap: 'anywhere',
};

const primaryBtnStyle: React.CSSProperties = {
  padding: '10px 14px',
  borderRadius: 10,
  border: '1px solid #111827',
  background: '#0f172a',
  color: '#ffffff',
  fontWeight: 700,
  cursor: 'pointer',
};

const secondaryBtnStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '10px 14px',
  borderRadius: 10,
  border: '1px solid #d1d5db',
  background: '#ffffff',
  color: '#111827',
  textDecoration: 'none',
  fontWeight: 600,
  cursor: 'pointer',
};

const filterBtnStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '8px 12px',
  borderRadius: 999,
  border: '1px solid #d1d5db',
  background: '#ffffff',
  color: '#334155',
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
};

const activeFilterBtnStyle: React.CSSProperties = {
  ...filterBtnStyle,
  border: '1px solid #93c5fd',
  background: '#dbeafe',
  color: '#1d4ed8',
};

const errorStyle: React.CSSProperties = {
  background: '#fef2f2',
  border: '1px solid #fecaca',
  color: '#b91c1c',
  borderRadius: 12,
  padding: 12,
  marginBottom: 12,
};

const previewAreaStyle: React.CSSProperties = {
  width: '100%',
  minHeight: 360,
  boxSizing: 'border-box',
  border: '1px solid #d1d5db',
  borderRadius: 12,
  padding: 12,
  fontFamily: 'Consolas, Menlo, Monaco, monospace',
  fontSize: 12,
  lineHeight: 1.5,
  resize: 'vertical',
  background: '#f8fafc',
};

const tableStyle: React.CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  minWidth: 860,
};

const tableHeadCellStyle: React.CSSProperties = {
  textAlign: 'left',
  fontSize: 12,
  color: '#475569',
  background: '#f8fafc',
  borderBottom: '1px solid #e5e7eb',
  padding: '10px 12px',
  whiteSpace: 'nowrap',
};

const tableBodyCellStyle: React.CSSProperties = {
  fontSize: 13,
  color: '#0f172a',
  borderBottom: '1px solid #eef2f7',
  padding: '10px 12px',
  verticalAlign: 'top',
};
