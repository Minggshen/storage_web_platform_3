import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

import { getProjectDashboard } from '../../services/projects';
import {
  listProjectAssets,
  uploadTariffFile,
  uploadDeviceLibraryFile,
  uploadRuntimeFile,
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

  const boundCount = dashboard?.runtime_bound_load_count ?? 0;
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
            <input
              id="tariff-file-input"
              type="file"
              accept=".xlsx,.xls,.csv"
              className="text-sm text-muted-foreground"
              onChange={(e) => setTariffFile(e.target.files?.[0] ?? null)}
            />
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
            <input
              id="device-library-file-input"
              type="file"
              accept=".xlsx,.xls,.csv"
              className="text-sm text-muted-foreground"
              onChange={(e) => setLibraryFile(e.target.files?.[0] ?? null)}
            />
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
            <StepBadge step={3} label="Runtime 文件绑定" />
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                boundCount > 0
                  ? 'border border-emerald-500/30 bg-emerald-500/10 text-emerald-600'
                  : 'border border-amber-500/30 bg-amber-500/10 text-amber-600'
              }`}
            >
              {boundCount}/{totalLoadNodes} 节点已绑定
            </span>
          </div>

          <div className="grid gap-5" style={{ gridTemplateColumns: '1fr 1fr' }}>
            {/* Left: node selector + binding status */}
            <div>
              <label htmlFor="runtime-node-select" className="mb-1.5 block text-sm font-semibold text-muted-foreground">
                选择负荷节点
              </label>
              <select
                id="runtime-node-select"
                value={runtimeNodeId}
                onChange={(e) => setRuntimeNodeId(e.target.value)}
                className="w-full rounded-xl border border-border bg-card px-3 py-2.5 text-sm"
              >
                <option value="">请选择负荷节点</option>
                {loadNodes.map((node) => (
                  <option key={node.id} value={node.id}>
                    {node.label}
                  </option>
                ))}
              </select>
              {loadNodes.length === 0 ? (
                <div className="mt-2 text-xs font-semibold text-amber-600">
                  当前拓扑没有负荷节点，请先在拓扑建模页添加并保存负荷节点。
                </div>
              ) : null}

              {/* Binding status */}
              {selectedRuntimeNode ? (
                <div className="mt-4 rounded-xl border border-border bg-muted/30 p-3.5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-bold text-foreground">当前节点绑定状态</div>
                      <div className="mt-1 text-xs text-muted-foreground break-words">
                        {selectedRuntimeNode.label}
                      </div>
                    </div>
                    <span
                      className={`inline-flex shrink-0 items-center rounded-full border px-2.5 py-0.5 text-xs font-bold ${
                        selectedRuntimeBound
                          ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-600'
                          : 'border-amber-500/40 bg-amber-500/10 text-amber-600'
                      }`}
                    >
                      {selectedRuntimeBound ? '已完成绑定' : '未完成绑定'}
                    </span>
                  </div>
                  <div className="mt-3 grid gap-2.5" style={{ gridTemplateColumns: '1fr 1fr' }}>
                    <RuntimeInfo label="绑定 year_map" value={selectedRuntimeNode.runtimeBinding?.yearMapFileName || '未绑定'} />
                    <RuntimeInfo label="绑定 model_library" value={selectedRuntimeNode.runtimeBinding?.modelLibraryFileName || '未绑定'} />
                    <RuntimeInfo label="已上传 year_map" value={selectedRuntimeNode.currentRuntimeFiles?.yearMapFileName || '未上传'} />
                    <RuntimeInfo label="已上传 model_library" value={selectedRuntimeNode.currentRuntimeFiles?.modelLibraryFileName || '未上传'} />
                  </div>
                </div>
              ) : (
                <div className="mt-4 rounded-xl border border-border bg-muted/30 p-3.5">
                  <div className="text-sm font-bold text-foreground">当前节点绑定状态</div>
                  <div className="mt-2 text-xs text-muted-foreground">
                    请选择一个负荷节点后查看其 runtime 绑定情况。
                  </div>
                </div>
              )}
            </div>

            {/* Right: upload controls */}
            <div>
              <div className="mb-4">
                <label htmlFor="runtime-file-input-1" className="mb-1.5 block text-sm font-semibold text-muted-foreground">
                  runtime_year_model_map.csv
                </label>
                <input
                  id="runtime-file-input-1"
                  type="file"
                  accept=".csv"
                  className="text-sm text-muted-foreground"
                  onChange={(e) => setYearMapFile(e.target.files?.[0] ?? null)}
                />
                <div className="mt-2.5">
                  <Button size="sm" onClick={() => onUploadRuntime('year_map')} disabled={!runtimeNodeId || !yearMapFile || uploading}>
                    上传 year_map
                  </Button>
                </div>
              </div>

              <div>
                <label htmlFor="runtime-file-input-2" className="mb-1.5 block text-sm font-semibold text-muted-foreground">
                  runtime_model_library.csv
                </label>
                <input
                  id="runtime-file-input-2"
                  type="file"
                  accept=".csv"
                  className="text-sm text-muted-foreground"
                  onChange={(e) => setModelLibraryFile(e.target.files?.[0] ?? null)}
                />
                <div className="mt-2.5">
                  <Button size="sm" onClick={() => onUploadRuntime('model_library')} disabled={!runtimeNodeId || !modelLibraryFile || uploading}>
                    上传 model_library
                  </Button>
                </div>
              </div>
            </div>
          </div>

          <p className="mt-4 text-xs text-muted-foreground">
            每个负荷节点需要分别绑定 year_map 和 model_library。切换节点后状态自动更新。节点列表来自拓扑建模中的负荷节点。
          </p>
        </section>

        {/* Refresh */}
        <div className="text-center">
          <button
            onClick={loadDashboard}
            disabled={loading || uploading}
            className="rounded-xl border border-border bg-card px-4 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
          >
            {loading ? '刷新中...' : '刷新状态'}
          </button>
        </div>
      </div>
    </div>
  );
}

function RuntimeInfo({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-card px-3 py-2.5 min-w-0">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-[13px] font-semibold text-foreground break-words">
        {value}
      </div>
    </div>
  );
}

export { AssetsPage };
export default AssetsPage;
