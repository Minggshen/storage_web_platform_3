import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { deleteProject, listProjects } from '../../services/projects';
import { Button } from '@/components/ui/button';
import { ErrorBanner } from '@/components/common/ErrorBanner';

type ProjectListItem = {
  project_id: string;
  project_name: string;
  description?: string | null;
  created_at?: string;
};

function formatProjectTime(value?: string) {
  if (!value) return '--';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString('zh-CN', { hour12: false });
}

function ProjectsPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ProjectListItem | null>(null);
  const [confirmInput, setConfirmInput] = useState('');

  async function loadProjects() {
    setLoading(true);
    setError(null);
    try {
      const res = await listProjects();
      setProjects(Array.isArray(res.projects) ? res.projects : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setProjects([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadProjects();
  }, []);

  async function executeDelete() {
    if (!deleteTarget) return;
    if (confirmInput !== deleteTarget.project_id) {
      setError('项目编号确认不匹配，已取消删除。');
      setDeleteTarget(null);
      setConfirmInput('');
      return;
    }
    setDeletingProjectId(deleteTarget.project_id);
    setError(null);
    setDeleteTarget(null);
    setConfirmInput('');
    try {
      await deleteProject(deleteTarget.project_id);
      setProjects((prev) => prev.filter((project) => project.project_id !== deleteTarget.project_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeletingProjectId(null);
    }
  }

  function openDeleteConfirm(item: ProjectListItem) {
    setError(null);
    setDeleteTarget(item);
    setConfirmInput('');
  }

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-[1200px]">
        {/* Hero */}
        <div className="mb-5 rounded-2xl border border-border bg-card p-5">
          <div className="mb-2 text-[13px] text-muted-foreground">项目入口</div>
          <h1 className="m-0 text-[32px] font-extrabold tracking-tight text-foreground">项目列表</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            选择已有项目，或创建新的前后端联调项目。
          </p>
        </div>

        {/* Actions */}
        <div className="mb-5 flex gap-3">
          <Button asChild>
            <Link to="/projects/new">新建项目</Link>
          </Button>
          <Button variant="outline" onClick={loadProjects} disabled={loading}>
            {loading ? '刷新中...' : '刷新列表'}
          </Button>
        </div>

        {/* Error */}
        {error && <ErrorBanner message={error} />}

        {/* Project table */}
        <div className="rounded-2xl border border-border bg-card p-5">
          <h2 className="mt-0 text-2xl font-bold text-foreground">全部项目</h2>

          {!projects.length ? (
            <div className="text-muted-foreground">暂无项目。</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] border-collapse" aria-label="项目列表">
                <thead>
                  <tr>
                    <th className="border-b border-border bg-muted/50 px-3 py-2.5 text-left text-sm font-semibold text-muted-foreground">
                      项目名称
                    </th>
                    <th className="border-b border-border bg-muted/50 px-3 py-2.5 text-left text-sm font-semibold text-muted-foreground">
                      项目编号
                    </th>
                    <th className="border-b border-border bg-muted/50 px-3 py-2.5 text-left text-sm font-semibold text-muted-foreground">
                      创建时间
                    </th>
                    <th className="border-b border-border bg-muted/50 px-3 py-2.5 text-left text-sm font-semibold text-muted-foreground">
                      描述
                    </th>
                    <th className="border-b border-border bg-muted/50 px-3 py-2.5 text-left text-sm font-semibold text-muted-foreground">
                      操作
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {projects.map((item) => (
                    <tr key={item.project_id}>
                      <td className="border-b border-muted px-3 py-3 align-top text-sm text-foreground">
                        {item.project_name}
                      </td>
                      <td className="border-b border-muted px-3 py-3 align-top text-sm text-muted-foreground">
                        {item.project_id}
                      </td>
                      <td className="border-b border-muted px-3 py-3 align-top text-sm text-muted-foreground">
                        {formatProjectTime(item.created_at)}
                      </td>
                      <td className="border-b border-muted px-3 py-3 align-top text-sm text-muted-foreground">
                        {item.description ?? '--'}
                      </td>
                      <td className="border-b border-muted px-3 py-3 align-top">
                        <div className="flex items-center gap-2.5 flex-wrap">
                          <Link
                            to={`/projects/${item.project_id}/overview`}
                            className="font-semibold text-primary no-underline hover:underline"
                          >
                            进入项目
                          </Link>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-red-600 hover:bg-red-500/10 hover:text-red-600"
                            onClick={() => openDeleteConfirm(item)}
                            disabled={deletingProjectId === item.project_id}
                          >
                            {deletingProjectId === item.project_id ? '删除中...' : '删除'}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Delete confirmation dialog */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" onClick={() => setDeleteTarget(null)} />
          <div
            role="alertdialog"
            aria-modal="true"
            aria-label="确认删除项目"
            className="relative z-10 w-full max-w-md rounded-2xl border bg-background p-6 shadow-xl"
          >
            <h2 className="mb-2 text-lg font-bold text-foreground">确认删除项目</h2>
            <p className="mb-2 text-sm text-muted-foreground">
              将永久删除项目 {deleteTarget.project_name || '未命名项目'}（{deleteTarget.project_id}）下的全部数据，包括拓扑、资产、构建产物和求解结果。
            </p>
            <p className="mb-4 text-sm font-semibold text-red-600">该操作不可恢复。</p>
            <label htmlFor="delete-confirm-input" className="mb-1.5 block text-sm font-medium">
              请输入项目编号确认：{deleteTarget.project_id}
            </label>
            <input
              id="delete-confirm-input"
              type="text"
              value={confirmInput}
              onChange={(e) => setConfirmInput(e.target.value)}
              className="mb-5 w-full rounded-xl border bg-background px-3 py-2 text-sm"
              onKeyDown={(e) => { if (e.key === 'Enter') executeDelete(); }}
            />
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setDeleteTarget(null)}
                className="rounded-xl border bg-background px-4 py-2 text-sm font-medium hover:bg-muted transition-colors"
              >
                取消
              </button>
              <button
                type="button"
                onClick={executeDelete}
                disabled={confirmInput !== deleteTarget.project_id}
                className="rounded-xl bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export { ProjectsPage };
export default ProjectsPage;
