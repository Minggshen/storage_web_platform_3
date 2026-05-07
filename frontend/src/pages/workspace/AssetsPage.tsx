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
import { Button } from '@/components/ui/button';

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

function Row(props: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-border py-2">
      <span className="text-muted-foreground">{props.label}</span>
      <strong className="min-w-0 text-right break-words">{props.value}</strong>
    </div>
  );
}

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
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-[1280px]">
        <div className="mb-4">
          <Link to="/projects" className="font-semibold text-primary no-underline hover:underline">
            &larr; 返回项目列表
          </Link>
        </div>

        {/* Page Header */}
        <div className="mb-5 rounded-2xl border border-border bg-card p-5">
          <div className="mb-2 text-[13px] text-muted-foreground">资产绑定</div>
          <h1 className="m-0 text-[32px] font-extrabold tracking-tight text-foreground">资产与文件绑定</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            上传电价表、设备策略库以及 runtime 文件，并查看当前绑定状态。
          </p>
          <div className="mt-3 text-sm text-muted-foreground">项目 ID：{projectId}</div>
        </div>

        {/* Action buttons */}
        <div className="mb-5 flex gap-3 flex-wrap">
          <Button variant="outline" size="sm" asChild>
            <Link to={`/projects/${projectId}/overview`}>返回项目总览</Link>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link to={`/projects/${projectId}/build`}>进入构建校验</Link>
          </Button>
          <Button size="sm" onClick={loadDashboard} disabled={loading || uploading}>
            {loading ? '刷新中...' : '刷新状态'}
          </Button>
        </div>

        {/* Error / Success messages */}
        {error ? (
          <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3.5 text-sm text-red-600">
            错误：{error}
          </div>
        ) : null}
        {message ? (
          <div className="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3.5 text-sm text-emerald-600">
            {message}
          </div>
        ) : null}

        {/* Main grid */}
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
          {/* Status */}
          <section className="rounded-2xl border border-border bg-card p-5">
            <h2 className="mb-4 mt-0 text-[22px] font-bold text-foreground">当前状态</h2>
            <Row label="电价表" value={dashboard?.has_tariff ? '已配置' : '未配置'} />
            <Row label="设备库" value={dashboard?.has_device_library ? '已配置' : '未配置'} />
            <Row
              label="已绑定 runtime 负荷数"
              value={`${dashboard?.runtime_bound_load_count ?? 0} / ${dashboard?.load_node_count ?? 0}`}
            />
          </section>

          {/* Tariff upload */}
          <section className="rounded-2xl border border-border bg-card p-5">
            <h2 className="mb-4 mt-0 text-[22px] font-bold text-foreground">上传电价表</h2>
            <input
              type="file"
              accept=".xlsx,.xls,.csv"
              className="text-sm text-muted-foreground"
              onChange={(e) => setTariffFile(e.target.files?.[0] ?? null)}
            />
            <div className="mt-3">
              <Button size="sm" onClick={onUploadTariff} disabled={!tariffFile || uploading}>
                上传电价表
              </Button>
            </div>
          </section>

          {/* Device library upload */}
          <section className="rounded-2xl border border-border bg-card p-5">
            <h2 className="mb-4 mt-0 text-[22px] font-bold text-foreground">上传设备策略库</h2>
            <input
              type="file"
              accept=".xlsx,.xls,.csv"
              className="text-sm text-muted-foreground"
              onChange={(e) => setLibraryFile(e.target.files?.[0] ?? null)}
            />
            <div className="mt-3">
              <Button size="sm" onClick={onUploadLibrary} disabled={!libraryFile || uploading}>
                上传设备库
              </Button>
            </div>
          </section>

          {/* Runtime upload */}
          <section className="rounded-2xl border border-border bg-card p-5">
            <h2 className="mb-4 mt-0 text-[22px] font-bold text-foreground">上传 runtime 文件</h2>

            <div className="grid gap-4 items-start" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
              {/* Runtime status */}
              <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-3.5">
                {selectedRuntimeNode ? (
                  <>
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-bold text-foreground">当前节点 runtime 状态</div>
                        <div className="mt-1 text-xs leading-relaxed text-foreground/70 break-words">
                          {selectedRuntimeNode.label}
                        </div>
                      </div>
                      <span
                        className={`inline-flex shrink-0 items-center justify-center rounded-full border px-2.5 py-0.5 text-xs font-bold ${
                          selectedRuntimeBound
                            ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-600'
                            : 'border-amber-500/40 bg-amber-500/10 text-amber-600'
                        }`}
                      >
                        {selectedRuntimeBound ? '已完成绑定' : '未完成绑定'}
                      </span>
                    </div>
                    <div className="mt-3 grid gap-2.5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
                      <RuntimeInfo label="绑定 year_map" value={selectedRuntimeNode.runtimeBinding?.yearMapFileName || '未绑定'} />
                      <RuntimeInfo label="绑定 model_library" value={selectedRuntimeNode.runtimeBinding?.modelLibraryFileName || '未绑定'} />
                      <RuntimeInfo label="已上传 year_map" value={selectedRuntimeNode.currentRuntimeFiles?.yearMapFileName || '未上传'} />
                      <RuntimeInfo label="已上传 model_library" value={selectedRuntimeNode.currentRuntimeFiles?.modelLibraryFileName || '未上传'} />
                    </div>
                    <div className="mt-2.5 text-xs leading-relaxed text-muted-foreground">
                      选择不同负荷节点时，这里会同步显示该节点当前已绑定的 runtime 文件。
                    </div>
                  </>
                ) : (
                  <>
                    <div className="text-sm font-bold text-foreground">当前节点 runtime 状态</div>
                    <div className="mt-2 text-[13px] leading-relaxed text-muted-foreground">
                      请选择一个负荷节点后查看其 runtime 绑定情况。
                    </div>
                  </>
                )}
              </div>

              {/* Runtime upload controls */}
              <div className="min-w-0">
                <div className="mb-2">
                  <label className="mb-1.5 block text-[13px] text-muted-foreground">负荷节点</label>
                  <select
                    value={runtimeNodeId}
                    onChange={(e) => setRuntimeNodeId(e.target.value)}
                    className="w-full rounded-xl border border-border bg-card px-3 py-2.5 text-sm box-border"
                  >
                    <option value="">请选择负荷节点</option>
                    {loadNodes.map((node) => (
                      <option key={node.id} value={node.id}>
                        {node.label}
                      </option>
                    ))}
                  </select>
                  {loadNodes.length === 0 ? (
                    <div className="mt-2 text-[13px] font-semibold text-amber-600">
                      当前拓扑没有负荷节点，请先在拓扑建模页添加并保存负荷节点。
                    </div>
                  ) : null}
                </div>

                <div className="mt-3.5 grid gap-3.5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
                  <div className="min-w-0">
                    <label className="mb-1.5 mt-2 block text-[13px] text-muted-foreground">
                      runtime_year_model_map.csv
                    </label>
                    <input
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

                  <div className="min-w-0">
                    <label className="mb-1.5 mt-2 block text-[13px] text-muted-foreground">
                      runtime_model_library.csv
                    </label>
                    <input
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
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function RuntimeInfo({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-card px-3 py-2.5 min-w-0">
      <div className="text-xs leading-tight text-muted-foreground">{label}</div>
      <div className="mt-1 text-[13px] font-semibold leading-relaxed text-foreground break-words">
        {value}
      </div>
    </div>
  );
}

export { AssetsPage };
export default AssetsPage;
