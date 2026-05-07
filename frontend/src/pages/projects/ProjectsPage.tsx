import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { deleteProject, listProjects } from '../../services/projects';
import { Button } from '@/components/ui/button';

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

  async function handleDeleteProject(item: ProjectListItem) {
    const projectLabel = `${item.project_name || '未命名项目'}（${item.project_id}）`;
    const confirmed = window.confirm(
      `将永久删除项目 ${projectLabel} 下的全部数据，包括拓扑、资产、构建产物和求解结果。\n\n该操作不可恢复。是否继续？`,
    );
    if (!confirmed) return;

    const typed = window.prompt(`请输入项目编号确认删除：${item.project_id}`);
    if (typed !== item.project_id) {
      setError('项目编号确认不匹配，已取消删除。');
      return;
    }

    setDeletingProjectId(item.project_id);
    setError(null);
    try {
      await deleteProject(item.project_id);
      setProjects((prev) => prev.filter((project) => project.project_id !== item.project_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeletingProjectId(null);
    }
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
        {error ? (
          <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3.5 text-sm text-red-600">
            加载失败：{error}
          </div>
        ) : null}

        {/* Project table */}
        <div className="rounded-2xl border border-border bg-card p-5">
          <h2 className="mt-0 text-2xl font-bold text-foreground">全部项目</h2>

          {!projects.length ? (
            <div className="text-muted-foreground">暂无项目。</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] border-collapse">
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
                            onClick={() => handleDeleteProject(item)}
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
    </div>
  );
}

export { ProjectsPage };
export default ProjectsPage;
