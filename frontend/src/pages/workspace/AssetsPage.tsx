import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { getProjectDashboard } from '../../services/projects';
import {
  listProjectAssets,
  uploadTariffFile,
  uploadDeviceLibraryFile,
  uploadRuntimeFile,
} from '../../services/assets';
import { fetchProjectTopology } from '../../services/topology';

type DashboardPayload = {
  project_id: string;
  project_name?: string;
  description?: string | null;
  load_node_count?: number;
  runtime_bound_load_count?: number;
  has_tariff?: boolean;
  has_device_library?: boolean;
};

type LoadNodeOption = {
  id: string;
  label: string;
  nodeId?: string | number | null;
  category?: string;
  runtimeBinding?: {
    yearMapFileName?: string;
    modelLibraryFileName?: string;
  };
  currentRuntimeFiles?: {
    yearMapFileName?: string;
    modelLibraryFileName?: string;
  };
};

function AssetsPage() {
  const { projectId = '' } = useParams();

  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);
  const [loadNodes, setLoadNodes] = useState<LoadNodeOption[]>([]);

  const [tariffFile, setTariffFile] = useState<File | null>(null);
  const [libraryFile, setLibraryFile] = useState<File | null>(null);
  const [runtimeNodeId, setRuntimeNodeId] = useState('');
  const [yearMapFile, setYearMapFile] = useState<File | null>(null);
  const [modelLibraryFile, setModelLibraryFile] = useState<File | null>(null);
  const selectedRuntimeNode = loadNodes.find((node) => node.id === runtimeNodeId) ?? null;
  const selectedRuntimeBound = Boolean(
    selectedRuntimeNode?.runtimeBinding?.yearMapFileName &&
      selectedRuntimeNode?.runtimeBinding?.modelLibraryFileName,
  );

  async function loadDashboard() {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const [res, topology, assets] = await Promise.all([
        getProjectDashboard(projectId),
        fetchProjectTopology(projectId),
        listProjectAssets(projectId),
      ]);
      setDashboard(res.dashboard);
      const options = topology.nodes
        .filter((node) => String(node.type) === 'load')
        .map((node) => {
          const params = typeof node.params === 'object' && node.params !== null
            ? (node.params as Record<string, unknown>)
            : {};
          const runtimeBinding = typeof node.runtime_binding === 'object' && node.runtime_binding !== null
            ? (node.runtime_binding as Record<string, unknown>)
            : {};
          const id = String(node.id ?? '');
          const name = String(node.name ?? id);
          const numericNodeId = params.node_id as string | number | null | undefined;
          const category = typeof params.category === 'string' ? params.category : undefined;
          const currentRuntimeFiles = assets.reduce(
            (acc, asset) => {
              const metadata =
                typeof asset.metadata === 'object' && asset.metadata !== null
                  ? (asset.metadata as Record<string, unknown>)
                  : {};
              if (
                String(metadata.category ?? '') !== 'runtime' ||
                String(metadata.subfolder ?? '') !== id ||
                metadata.is_current !== true
              ) {
                return acc;
              }
              const fileName = typeof asset.file_name === 'string' ? asset.file_name : undefined;
              if (String(metadata.runtime_kind ?? '') === 'year_map') {
                acc.yearMapFileName = fileName;
              }
              if (String(metadata.runtime_kind ?? '') === 'model_library') {
                acc.modelLibraryFileName = fileName;
              }
              return acc;
            },
            {} as { yearMapFileName?: string; modelLibraryFileName?: string },
          );
          return {
            id,
            label: `${name} (${id}${numericNodeId ? ` / node_id=${numericNodeId}` : ''})`,
            nodeId: numericNodeId,
            category,
            runtimeBinding: {
              yearMapFileName:
                typeof runtimeBinding.year_map_file_name === 'string'
                  ? runtimeBinding.year_map_file_name
                  : undefined,
              modelLibraryFileName:
                typeof runtimeBinding.model_library_file_name === 'string'
                  ? runtimeBinding.model_library_file_name
                  : undefined,
            },
            currentRuntimeFiles,
          };
        })
        .filter((node) => node.id);
      setLoadNodes(options);
      setRuntimeNodeId((current) => {
        if (current && options.some((node) => node.id === current)) return current;
        return options[0]?.id ?? '';
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setDashboard(null);
      setLoadNodes([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDashboard();
  }, [projectId]);

  async function onUploadTariff() {
    if (!projectId || !tariffFile) return;
    setUploading(true);
    setError(null);
    setMessage(null);
    try {
      await uploadTariffFile(projectId, tariffFile);
      setMessage('电价表上传成功。');
      setTariffFile(null);
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  }

  async function onUploadLibrary() {
    if (!projectId || !libraryFile) return;
    setUploading(true);
    setError(null);
    setMessage(null);
    try {
      await uploadDeviceLibraryFile(projectId, libraryFile);
      setMessage('设备策略库上传成功。');
      setLibraryFile(null);
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  }

  async function onUploadRuntime(kind: 'year_map' | 'model_library') {
    if (!projectId) return;

    const file = kind === 'year_map' ? yearMapFile : modelLibraryFile;
    if (!file) return;

    setUploading(true);
    setError(null);
    setMessage(null);
    try {
      await uploadRuntimeFile(projectId, runtimeNodeId, kind, file);
      setMessage(
        kind === 'year_map'
          ? 'runtime_year_model_map 上传成功。'
          : 'runtime_model_library 上传成功。',
      );
      if (kind === 'year_map') {
        setYearMapFile(null);
      } else {
        setModelLibraryFile(null);
      }
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  }

  return (
    <div style={{ padding: 24, background: '#f8fafc', minHeight: '100vh' }}>
      <div style={{ maxWidth: 1280, margin: '0 auto' }}>
        <div style={{ marginBottom: 16 }}>
          <Link
            to="/projects"
            style={{ color: '#2563eb', textDecoration: 'none', fontWeight: 600 }}
          >
            ← 返回项目列表
          </Link>
        </div>

        <div style={heroStyle}>
          <div style={{ fontSize: 13, color: '#64748b', marginBottom: 8 }}>资产绑定</div>
          <h1 style={{ margin: 0, fontSize: 32 }}>资产与文件绑定</h1>
          <div style={{ color: '#64748b', marginTop: 8 }}>
            上传电价表、设备策略库以及 runtime 文件，并查看当前绑定状态。
          </div>
          <div style={{ color: '#64748b', marginTop: 12 }}>项目 ID：{projectId}</div>
        </div>

        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 20 }}>
          <Link to={`/projects/${projectId}/overview`} style={navBtnStyle}>
            返回项目总览
          </Link>
          <Link to={`/projects/${projectId}/build`} style={navBtnStyle}>
            进入构建校验
          </Link>
          <button onClick={loadDashboard} disabled={loading || uploading} style={primaryBtnStyle}>
            {loading ? '刷新中...' : '刷新状态'}
          </button>
        </div>

        {error ? <div style={errorStyle}>错误：{error}</div> : null}
        {message ? <div style={successStyle}>{message}</div> : null}

        <div style={gridStyle}>
          <section style={cardStyle}>
            <h2 style={cardTitleStyle}>当前状态</h2>
            <Row label="电价表" value={dashboard?.has_tariff ? '已配置' : '未配置'} />
            <Row label="设备库" value={dashboard?.has_device_library ? '已配置' : '未配置'} />
            <Row
              label="已绑定 runtime 负荷数"
              value={`${dashboard?.runtime_bound_load_count ?? 0} / ${dashboard?.load_node_count ?? 0}`}
            />
          </section>

          <section style={cardStyle}>
            <h2 style={cardTitleStyle}>上传电价表</h2>
            <input
              type="file"
              accept=".xlsx,.xls,.csv"
              onChange={(e) => setTariffFile(e.target.files?.[0] ?? null)}
            />
            <div style={{ marginTop: 12 }}>
              <button
                onClick={onUploadTariff}
                disabled={!tariffFile || uploading}
                style={primaryBtnStyle}
              >
                上传电价表
              </button>
            </div>
          </section>

          <section style={cardStyle}>
            <h2 style={cardTitleStyle}>上传设备策略库</h2>
            <input
              type="file"
              accept=".xlsx,.xls,.csv"
              onChange={(e) => setLibraryFile(e.target.files?.[0] ?? null)}
            />
            <div style={{ marginTop: 12 }}>
              <button
                onClick={onUploadLibrary}
                disabled={!libraryFile || uploading}
                style={primaryBtnStyle}
              >
                上传设备库
              </button>
            </div>
          </section>

          <section style={cardStyle}>
            <h2 style={cardTitleStyle}>上传 runtime 文件</h2>

            <div style={runtimeWorkbenchGridStyle}>
              <div style={runtimeStatusCardStyle}>
                {selectedRuntimeNode ? (
                  <>
                    <div style={runtimeStatusHeaderStyle}>
                      <div style={{ minWidth: 0 }}>
                        <div style={runtimeStatusTitleStyle}>当前节点 runtime 状态</div>
                        <div style={runtimeStatusNodeStyle}>{selectedRuntimeNode.label}</div>
                      </div>
                      <span
                        style={
                          selectedRuntimeBound ? runtimeBoundBadgeStyle : runtimePendingBadgeStyle
                        }
                      >
                        {selectedRuntimeBound ? '已完成绑定' : '未完成绑定'}
                      </span>
                    </div>
                    <div style={runtimeInfoGridStyle}>
                      <div style={runtimeInfoItemStyle}>
                        <div style={runtimeInfoLabelStyle}>绑定 year_map</div>
                        <div style={runtimeInfoValueStyle}>
                          {selectedRuntimeNode.runtimeBinding?.yearMapFileName || '未绑定'}
                        </div>
                      </div>
                      <div style={runtimeInfoItemStyle}>
                        <div style={runtimeInfoLabelStyle}>绑定 model_library</div>
                        <div style={runtimeInfoValueStyle}>
                          {selectedRuntimeNode.runtimeBinding?.modelLibraryFileName || '未绑定'}
                        </div>
                      </div>
                      <div style={runtimeInfoItemStyle}>
                        <div style={runtimeInfoLabelStyle}>已上传 year_map</div>
                        <div style={runtimeInfoValueStyle}>
                          {selectedRuntimeNode.currentRuntimeFiles?.yearMapFileName || '未上传'}
                        </div>
                      </div>
                      <div style={runtimeInfoItemStyle}>
                        <div style={runtimeInfoLabelStyle}>已上传 model_library</div>
                        <div style={runtimeInfoValueStyle}>
                          {selectedRuntimeNode.currentRuntimeFiles?.modelLibraryFileName || '未上传'}
                        </div>
                      </div>
                    </div>
                    <div style={{ marginTop: 10, color: '#64748b', fontSize: 12, lineHeight: 1.5 }}>
                      选择不同负荷节点时，这里会同步显示该节点当前已绑定的 runtime 文件。
                    </div>
                  </>
                ) : (
                  <>
                    <div style={runtimeStatusTitleStyle}>当前节点 runtime 状态</div>
                    <div style={{ marginTop: 8, color: '#64748b', fontSize: 13, lineHeight: 1.5 }}>
                      请选择一个负荷节点后查看其 runtime 绑定情况。
                    </div>
                  </>
                )}
              </div>

              <div style={runtimeControlPanelStyle}>
                <label style={{ ...labelStyle, marginTop: 0 }}>负荷节点</label>
                <select
                  value={runtimeNodeId}
                  onChange={(e) => setRuntimeNodeId(e.target.value)}
                  style={inputStyle}
                >
                  <option value="">请选择负荷节点</option>
                  {loadNodes.map((node) => (
                    <option key={node.id} value={node.id}>
                      {node.label}
                    </option>
                  ))}
                </select>
                {loadNodes.length === 0 ? (
                  <div style={{ marginTop: 8, color: '#b45309', fontSize: 13 }}>
                    当前拓扑没有负荷节点，请先在拓扑建模页添加并保存负荷节点。
                  </div>
                ) : null}

                <div style={runtimeUploadGridStyle}>
                  <div style={runtimeUploadBlockStyle}>
                    <label style={labelStyle}>runtime_year_model_map.csv</label>
                    <input
                      type="file"
                      accept=".csv"
                      onChange={(e) => setYearMapFile(e.target.files?.[0] ?? null)}
                    />
                    <div style={{ marginTop: 10 }}>
                      <button
                        onClick={() => onUploadRuntime('year_map')}
                        disabled={!runtimeNodeId || !yearMapFile || uploading}
                        style={primaryBtnStyle}
                      >
                        上传 year_map
                      </button>
                    </div>
                  </div>

                  <div style={runtimeUploadBlockStyle}>
                    <label style={labelStyle}>runtime_model_library.csv</label>
                    <input
                      type="file"
                      accept=".csv"
                      onChange={(e) => setModelLibraryFile(e.target.files?.[0] ?? null)}
                    />
                    <div style={{ marginTop: 10 }}>
                      <button
                        onClick={() => onUploadRuntime('model_library')}
                        disabled={!runtimeNodeId || !modelLibraryFile || uploading}
                        style={primaryBtnStyle}
                      >
                        上传 model_library
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function Row(props: { label: string; value: React.ReactNode }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        gap: 16,
        padding: '8px 0',
        borderBottom: '1px solid #e5e7eb',
      }}
    >
      <span style={{ color: '#64748b' }}>{props.label}</span>
      <strong style={{ minWidth: 0, textAlign: 'right', overflowWrap: 'anywhere' }}>{props.value}</strong>
    </div>
  );
}

const heroStyle: React.CSSProperties = {
  background: '#ffffff',
  border: '1px solid #e5e7eb',
  borderRadius: 16,
  padding: 20,
  marginBottom: 20,
};

const gridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
  gap: 16,
};

const cardStyle: React.CSSProperties = {
  background: '#ffffff',
  border: '1px solid #e5e7eb',
  borderRadius: 16,
  padding: 20,
};

const cardTitleStyle: React.CSSProperties = {
  margin: '0 0 16px 0',
  fontSize: 22,
};

const navBtnStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '10px 14px',
  background: '#ffffff',
  color: '#111827',
  textDecoration: 'none',
  border: '1px solid #d1d5db',
  borderRadius: 12,
  fontWeight: 600,
};

const primaryBtnStyle: React.CSSProperties = {
  padding: '10px 14px',
  borderRadius: 12,
  border: '1px solid #111827',
  background: '#111827',
  color: '#ffffff',
  fontWeight: 700,
  cursor: 'pointer',
};

const errorStyle: React.CSSProperties = {
  background: '#fef2f2',
  border: '1px solid #fecaca',
  color: '#b91c1c',
  borderRadius: 12,
  padding: 14,
  marginBottom: 16,
};

const successStyle: React.CSSProperties = {
  background: '#f0fdf4',
  border: '1px solid #bbf7d0',
  color: '#166534',
  borderRadius: 12,
  padding: 14,
  marginBottom: 16,
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 13,
  color: '#64748b',
  marginTop: 8,
  marginBottom: 6,
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  border: '1px solid #d1d5db',
  borderRadius: 10,
  padding: '10px 12px',
};

const runtimeStatusCardStyle: React.CSSProperties = {
  padding: 14,
  borderRadius: 12,
  border: '1px solid #dbeafe',
  background: '#f8fbff',
};

const runtimeWorkbenchGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
  gap: 16,
  alignItems: 'start',
};

const runtimeControlPanelStyle: React.CSSProperties = {
  minWidth: 0,
};

const runtimeStatusHeaderStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'flex-start',
  gap: 12,
};

const runtimeStatusTitleStyle: React.CSSProperties = {
  fontSize: 14,
  fontWeight: 700,
  color: '#0f172a',
};

const runtimeStatusNodeStyle: React.CSSProperties = {
  marginTop: 4,
  color: '#475569',
  fontSize: 12,
  lineHeight: 1.4,
  overflowWrap: 'anywhere',
};

const runtimeBoundBadgeStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  minHeight: 24,
  padding: '0 10px',
  borderRadius: 999,
  background: '#dcfce7',
  border: '1px solid #86efac',
  color: '#166534',
  fontSize: 12,
  fontWeight: 700,
  flexShrink: 0,
};

const runtimePendingBadgeStyle: React.CSSProperties = {
  ...runtimeBoundBadgeStyle,
  background: '#fff7ed',
  border: '1px solid #fdba74',
  color: '#9a3412',
};

const runtimeInfoGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
  gap: 10,
  marginTop: 12,
};

const runtimeInfoItemStyle: React.CSSProperties = {
  padding: '10px 12px',
  borderRadius: 10,
  background: '#ffffff',
  border: '1px solid #e2e8f0',
  minWidth: 0,
};

const runtimeInfoLabelStyle: React.CSSProperties = {
  color: '#64748b',
  fontSize: 12,
  lineHeight: 1.3,
};

const runtimeInfoValueStyle: React.CSSProperties = {
  marginTop: 4,
  color: '#0f172a',
  fontSize: 13,
  fontWeight: 600,
  lineHeight: 1.4,
  overflowWrap: 'anywhere',
};

const runtimeUploadGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
  gap: 14,
  marginTop: 14,
};

const runtimeUploadBlockStyle: React.CSSProperties = {
  minWidth: 0,
};

export { AssetsPage };
export default AssetsPage;
