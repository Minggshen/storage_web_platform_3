import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';

import { getProjectDashboard } from '../../services/projects';
import {
  listProjectAssets,
  uploadTariffFile,
  uploadDeviceLibraryFile,
  uploadRawLoadData,
  listUploadedNodes,
  deleteRawLoadData,
  processRuntime,
  listPreviewFiles,
  fetchPreviewContent,
} from '../../services/assets';
import { fetchProjectTopology } from '../../services/topology';
import { Button } from '@/components/ui/button';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import StepBadge from '@/components/common/StepBadge';

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
  // Step 3 - 原始数据上传
  const [rawNodeId, setRawNodeId] = useState('');
  const [rawFile, setRawFile] = useState<File | null>(null);
  const [rawUploading, setRawUploading] = useState(false);
  const [uploadedNodeIds, setUploadedNodeIds] = useState<string[]>([]);
  const [processedNodeIds, setProcessedNodeIds] = useState<string[]>([]);

  // Step 3 - 处理日志
  const [processing, setProcessing] = useState(false);
  const [logLines, setLogLines] = useState<Array<{ id: number; node: string; message: string; type: 'progress' | 'done' | 'error' }>>([]);
  const [processProgress, setProcessProgress] = useState({ current: 0, total: 0 });
  const [processAbort, setProcessAbort] = useState<AbortController | null>(null);

  // Step 3 - 文件预览
  const [previewNodeId, setPreviewNodeId] = useState('');
  const [previewFile, setPreviewFile] = useState<{ name: string; type: string } | null>(null);
  const [previewFiles, setPreviewFiles] = useState<Array<{ name: string; type: string; url: string }>>([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewContent, setPreviewContent] = useState<{
    kind: 'image' | 'csv' | 'text';
    imageUrl?: string;
    columns?: string[];
    rows?: Array<Record<string, string>>;
    textContent?: string;
  } | null>(null);
  const logIdRef = useRef(0);

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

  useEffect(() => {
    if (projectId) refreshUploadedNodes();
  }, [projectId, loadNodes]);

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

  async function refreshUploadedNodes() {
    if (!projectId) return;
    try {
      const data = await listUploadedNodes(projectId);
      setUploadedNodeIds(data.uploaded_nodes);
      setProcessedNodeIds(data.processed_nodes);
    } catch {}
  }

  async function onUploadRawData() {
    if (!projectId || !rawNodeId || !rawFile) return;
    setRawUploading(true);
    setError(null);
    try {
      await uploadRawLoadData(projectId, rawNodeId, rawFile);
      setRawFile(null);
      await refreshUploadedNodes();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRawUploading(false);
    }
  }

  async function onDeleteRawData(nodeId: string) {
    if (!projectId) return;
    try {
      await deleteRawLoadData(projectId, nodeId);
      await refreshUploadedNodes();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  function onStartProcessing() {
    if (!projectId || processing) return;
    const nodeIds = uploadedNodeIds.filter((id) => !processedNodeIds.includes(id));
    if (nodeIds.length === 0) return;
    setProcessing(true);
    setLogLines([]);
    setProcessProgress({ current: 0, total: nodeIds.length });

    const ctrl = processRuntime(
      projectId,
      nodeIds,
      (event) => {
        const line = {
          id: ++logIdRef.current,
          node: String(event.node || ''),
          message: String(event.message || ''),
          type: (event.type as 'progress' | 'done' | 'error') || 'progress',
        };
        setLogLines((prev) => [...prev.slice(-49), line]);
        if (event.type === 'done' || event.type === 'error') {
          setProcessProgress((p) => ({ ...p, current: (event.current as number) || p.current }));
        }
      },
      async () => {
        setProcessing(false);
        setProcessAbort(null);
        await refreshUploadedNodes();
        await loadDashboard();
      },
      (err) => {
        setError(err.message);
        setProcessing(false);
        setProcessAbort(null);
      },
    );
    setProcessAbort(ctrl);
  }

  async function onSelectPreviewNode(nodeId: string) {
    setPreviewNodeId(nodeId);
    setPreviewFile(null);
    setPreviewContent(null);
    if (!nodeId || !projectId) return;
    setPreviewLoading(true);
    try {
      const data = await listPreviewFiles(projectId, nodeId);
      setPreviewFiles(data.files);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPreviewLoading(false);
    }
  }

  async function onSelectPreviewFile(file: { name: string; type: string }) {
    setPreviewFile(file);
    if (!projectId || !previewNodeId) return;
    setPreviewLoading(true);
    try {
      const result = await fetchPreviewContent(projectId, previewNodeId, file.name);
      if (result instanceof Blob) {
        setPreviewContent({ kind: 'image', imageUrl: URL.createObjectURL(result) });
      } else if ('content' in result && result.content) {
        setPreviewContent({ kind: 'text', textContent: result.content });
      } else if ('rows' in result && result.rows) {
        setPreviewContent({
          kind: 'csv',
          columns: result.columns,
          rows: result.rows,
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPreviewLoading(false);
    }
  }

  const totalLoadNodes = dashboard?.load_node_count ?? 0;

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto">

        {error && <ErrorBanner message={error} />}
        {message ? (
          <div className="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3.5 text-sm text-emerald-600">
            {message}
          </div>
        ) : null}

        {/* Step 1: Tariff */}
        <section className="mb-5 rounded-2xl border border-border bg-card p-5">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <StepBadge step={1} label="电价表配置" />
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                dashboard?.has_tariff
                  ? 'border border-emerald-500/30 bg-emerald-500/10 text-emerald-600'
                  : 'border border-amber-500/30 bg-amber-500/10 text-amber-600'
              }`}
            >
              {dashboard?.has_tariff ? '已配置 ✓' : '未配置 ✗'}
            </span>
          </div>
          <div className="flex items-center gap-4 flex-wrap">
            <span className="text-sm text-muted-foreground">
              当前：{dashboard?.has_tariff ? '已上传电价表文件' : '尚未上传'}
            </span>
            <label className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted/50 h-7 px-3 text-sm font-medium cursor-pointer hover:bg-muted transition-colors">
              <span className="text-base">📁</span> 选择文件
              <input
                id="tariff-file-input"
                type="file"
                accept=".xlsx,.xls,.csv"
                className="hidden"
                onChange={(e) => setTariffFile(e.target.files?.[0] ?? null)}
              />
            </label>
            {tariffFile && <span className="text-xs text-muted-foreground truncate max-w-[160px]">{tariffFile.name}</span>}
            <Button size="sm" onClick={onUploadTariff} disabled={!tariffFile || uploading}>
              上传电价表
            </Button>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            支持 .xlsx .xls .csv 格式。电价表用于全年经济性评估中的电费计算。
          </p>
        </section>

        {/* Step 2: Device Library */}
        <section className="mb-5 rounded-2xl border border-border bg-card p-5">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <StepBadge step={2} label="设备策略库配置" />
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                dashboard?.has_device_library
                  ? 'border border-emerald-500/30 bg-emerald-500/10 text-emerald-600'
                  : 'border border-amber-500/30 bg-amber-500/10 text-amber-600'
              }`}
            >
              {dashboard?.has_device_library ? '已配置 ✓' : '未配置 ✗'}
            </span>
          </div>
          <div className="flex items-center gap-4 flex-wrap">
            <span className="text-sm text-muted-foreground">
              当前：{dashboard?.has_device_library ? '已上传设备策略库文件' : '尚未上传'}
            </span>
            <label className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted/50 h-7 px-3 text-sm font-medium cursor-pointer hover:bg-muted transition-colors">
              <span className="text-base">📁</span> 选择文件
              <input
                id="device-library-file-input"
                type="file"
                accept=".xlsx,.xls,.csv"
                className="hidden"
                onChange={(e) => setLibraryFile(e.target.files?.[0] ?? null)}
              />
            </label>
            {libraryFile && <span className="text-xs text-muted-foreground truncate max-w-[160px]">{libraryFile.name}</span>}
            <Button size="sm" onClick={onUploadLibrary} disabled={!libraryFile || uploading}>
              上传设备库
            </Button>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            包含储能设备型号、功率/容量组合、价格、效率等参数，用于 GA 搜索空间定义。
          </p>
        </section>

        {/* Step 3: Runtime Files */}
        <section className="mb-5 rounded-2xl border border-border bg-card p-5">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <StepBadge step={3} label="负荷数据导入" />
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                uploadedNodeIds.length === totalLoadNodes && processedNodeIds.length === totalLoadNodes
                  ? 'border border-emerald-500/30 bg-emerald-500/10 text-emerald-600'
                  : 'border border-amber-500/30 bg-amber-500/10 text-amber-600'
              }`}
            >
              已上传 {uploadedNodeIds.length}/{totalLoadNodes} · 已处理 {processedNodeIds.length}/{totalLoadNodes}
            </span>
          </div>

          {/* ── ① 上传原始数据 ── */}
          <div className="mt-4 rounded-xl border border-border bg-muted/20 p-4">
            <div className="mb-2 text-sm font-semibold text-foreground">① 上传原始数据</div>
            <div className="flex items-center gap-3 flex-wrap">
              <select
                value={rawNodeId}
                onChange={(e) => setRawNodeId(e.target.value)}
                className="rounded-xl border border-border bg-card px-3 py-2 text-sm"
              >
                <option value="">选择负荷节点</option>
                {loadNodes
                  .filter((n) => !uploadedNodeIds.includes(n.id))
                  .map((n) => (
                    <option key={n.id} value={n.id}>{n.label}</option>
                  ))}
              </select>
              <label className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted/50 h-7 px-3 text-sm font-medium cursor-pointer hover:bg-muted transition-colors">
                <span className="text-base">📁</span> 选择文件
                <input
                  type="file"
                  accept=".xlsx,.xls"
                  className="hidden"
                  onChange={(e) => setRawFile(e.target.files?.[0] ?? null)}
                />
              </label>
              {rawFile && <span className="text-xs text-muted-foreground truncate max-w-[160px]">{rawFile.name}</span>}
              <Button size="sm" onClick={onUploadRawData} disabled={!rawNodeId || !rawFile || rawUploading}>
                上传
              </Button>
            </div>
            {uploadedNodeIds.length > 0 && (
              <div className="mt-3 flex items-center gap-3 flex-wrap">
                <span className="text-xs text-muted-foreground">
                  已上传：{uploadedNodeIds.map((id) => (
                    <span key={id} className="mr-1.5 mb-0.5 inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 pl-2 pr-1 py-0.5 text-[10px] font-semibold text-emerald-600">
                      {id} ✓
                      <button
                        type="button"
                        className="inline-flex h-4 w-4 items-center justify-center rounded-full text-muted-foreground hover:bg-red-500/20 hover:text-red-600 transition-colors"
                        title={`删除 ${id} 的上传文件`}
                        onClick={() => onDeleteRawData(id)}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </span>
                <Button size="sm" onClick={onStartProcessing} disabled={processing || uploadedNodeIds.length === 0}>
                  {processing ? '处理中...' : '一键处理 →'}
                </Button>
                {processing && processAbort && (
                  <Button size="sm" variant="outline" onClick={() => { processAbort.abort(); setProcessing(false); }}>
                    取消
                  </Button>
                )}
              </div>
            )}
            {uploadedNodeIds.length > 0 && (
              <div className="mt-3 text-xs text-muted-foreground">
                待处理：{uploadedNodeIds.filter((id) => !processedNodeIds.includes(id)).join(', ') || '无'}
              </div>
            )}
          </div>

          {/* ── ② 处理日志 ── */}
          {logLines.length > 0 && (
            <div className="mt-4 rounded-xl border border-border bg-muted/20 p-4">
              <div className="mb-2 text-sm font-semibold text-foreground">② 处理日志</div>
              {processProgress.total > 0 && (
                <div className="mb-3 h-2 w-full rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full bg-primary transition-all duration-300"
                    style={{ width: `${Math.round((processProgress.current / processProgress.total) * 100)}%` }}
                  />
                </div>
              )}
              <div className="max-h-48 overflow-y-auto space-y-0.5 text-xs font-mono">
                {logLines.map((line) => (
                  <div
                    key={line.id}
                    className={
                      line.type === 'error' ? 'text-red-600' :
                      line.type === 'done' ? 'text-emerald-600' :
                      'text-muted-foreground'
                    }
                  >
                    [{line.type === 'error' ? '✗' : line.type === 'done' ? '✓' : '·'}] {line.node}: {line.message}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── ③ 文件预览 ── */}
          <div className="mt-4 rounded-xl border border-border bg-muted/20 p-4">
            <div className="mb-2 text-sm font-semibold text-foreground">③ 文件预览</div>
            <div className="flex items-center gap-3 flex-wrap mb-3">
              <select
                value={previewNodeId}
                onChange={(e) => onSelectPreviewNode(e.target.value)}
                className="rounded-xl border border-border bg-card px-3 py-2 text-sm"
              >
                <option value="">选择节点</option>
                {processedNodeIds.map((id) => (
                  <option key={id} value={id}>{id}</option>
                ))}
              </select>
              <select
                value={previewFile?.name || ''}
                onChange={(e) => {
                  const f = previewFiles.find((pf) => pf.name === e.target.value);
                  if (f) onSelectPreviewFile(f);
                }}
                className="rounded-xl border border-border bg-card px-3 py-2 text-sm"
                disabled={!previewNodeId || previewFiles.length === 0}
              >
                <option value="">选择文件</option>
                {previewFiles.map((f) => (
                  <option key={f.name} value={f.name}>{f.name} ({f.type})</option>
                ))}
              </select>
            </div>
            {previewLoading ? (
              <div className="text-xs text-muted-foreground">加载中...</div>
            ) : previewContent ? (
              previewContent.kind === 'image' ? (
                <img src={previewContent.imageUrl} alt="预览" className="max-w-full max-h-96 rounded-xl border" />
              ) : previewContent.kind === 'csv' ? (
                <div className="max-h-80 overflow-auto rounded-xl border">
                  <table className="w-full text-xs">
                    <thead className="bg-muted/50 sticky top-0">
                      <tr>
                        {previewContent.columns?.map((col) => (
                          <th key={col} className="px-2 py-1.5 text-left font-semibold whitespace-nowrap">{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {previewContent.rows?.slice(0, 100).map((row, i) => (
                        <tr key={i} className="border-t border-border/50">
                          {previewContent.columns?.map((col) => (
                            <td key={col} className="px-2 py-1 whitespace-nowrap">{row[col]}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {previewContent.rows && previewContent.rows.length > 100 && (
                    <div className="px-2 py-1 text-xs text-muted-foreground">
                      显示前 100 行，共 {previewContent.rows.length} 行
                    </div>
                  )}
                </div>
              ) : (
                <pre className="max-h-80 overflow-auto rounded-xl border bg-muted/30 p-3 text-xs">{previewContent.textContent}</pre>
              )
            ) : (
              <div className="text-xs text-muted-foreground">选择已处理的节点和文件后预览</div>
            )}
          </div>

          <p className="mt-4 text-xs text-muted-foreground">
            上传原始负荷 Excel（两列：时间 + 负荷），脚本将自动根据节点类型（居民/工业/商业）选择建模算法生成 runtime 文件。
          </p>
        </section>

        {/* Refresh */}
        <div className="text-center">
          <button
            onClick={loadDashboard}
            disabled={loading || uploading}
            className="rounded-xl border border-border bg-muted/50 px-4 py-2 text-xs font-semibold text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            {loading ? '刷新中...' : '刷新状态'}
          </button>
        </div>
      </div>
    </div>
  );
}

export { AssetsPage };
export default AssetsPage;
