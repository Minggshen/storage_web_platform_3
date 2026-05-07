import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { deleteProject, listProjects } from '../../services/projects';

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
    <div style={{ padding: 24, background: '#f8fafc', minHeight: '100vh' }}>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        <div
          style={{
            background: '#ffffff',
            border: '1px solid #e5e7eb',
            borderRadius: 16,
            padding: 20,
            marginBottom: 20,
          }}
        >
          <div style={{ fontSize: 13, color: '#64748b', marginBottom: 8 }}>项目入口</div>
          <h1 style={{ margin: 0, fontSize: 32 }}>项目列表</h1>
          <div style={{ color: '#64748b', marginTop: 8 }}>
            选择已有项目，或创建新的前后端联调项目。
          </div>
        </div>

        <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
          <Link to="/projects/new" style={primaryLinkStyle}>
            新建项目
          </Link>
          <button onClick={loadProjects} disabled={loading} style={secondaryBtnStyle}>
            {loading ? '刷新中...' : '刷新列表'}
          </button>
        </div>

        {error ? (
          <div
            style={{
              background: '#fef2f2',
              border: '1px solid #fecaca',
              color: '#b91c1c',
              borderRadius: 12,
              padding: 14,
              marginBottom: 16,
            }}
          >
            加载失败：{error}
          </div>
        ) : null}

        <div
          style={{
            background: '#ffffff',
            border: '1px solid #e5e7eb',
            borderRadius: 16,
            padding: 20,
          }}
        >
          <h2 style={{ marginTop: 0, fontSize: 24 }}>全部项目</h2>

          {!projects.length ? (
            <div style={{ color: '#64748b' }}>暂无项目。</div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }}>
                <thead>
                  <tr>
                    <th style={thStyle}>项目名称</th>
                    <th style={thStyle}>项目编号</th>
                    <th style={thStyle}>创建时间</th>
                    <th style={thStyle}>描述</th>
                    <th style={thStyle}>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {projects.map((item) => (
                    <tr key={item.project_id}>
                      <td style={tdStyle}>{item.project_name}</td>
                      <td style={tdStyle}>{item.project_id}</td>
                      <td style={tdStyle}>{formatProjectTime(item.created_at)}</td>
                      <td style={tdStyle}>{item.description ?? '--'}</td>
                      <td style={tdStyle}>
                        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                          <Link
                            to={`/projects/${item.project_id}/overview`}
                            style={{ color: '#2563eb', textDecoration: 'none', fontWeight: 600 }}
                          >
                            进入项目
                          </Link>
                          <button
                            type="button"
                            onClick={() => handleDeleteProject(item)}
                            disabled={deletingProjectId === item.project_id}
                            style={dangerBtnStyle}
                          >
                            {deletingProjectId === item.project_id ? '删除中...' : '删除'}
                          </button>
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

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: '10px 12px',
  borderBottom: '1px solid #e5e7eb',
  color: '#64748b',
  fontWeight: 600,
  background: '#f8fafc',
};

const tdStyle: React.CSSProperties = {
  padding: '12px',
  borderBottom: '1px solid #f1f5f9',
  verticalAlign: 'top',
};

const primaryLinkStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '10px 14px',
  background: '#111827',
  color: '#ffffff',
  textDecoration: 'none',
  borderRadius: 12,
  fontWeight: 700,
};

const secondaryBtnStyle: React.CSSProperties = {
  padding: '10px 14px',
  borderRadius: 12,
  border: '1px solid #d1d5db',
  background: '#ffffff',
  color: '#111827',
  fontWeight: 600,
  cursor: 'pointer',
};

const dangerBtnStyle: React.CSSProperties = {
  padding: '7px 10px',
  borderRadius: 10,
  border: '1px solid #fecaca',
  background: '#fff1f2',
  color: '#b91c1c',
  fontWeight: 700,
  cursor: 'pointer',
};

export { ProjectsPage };
export default ProjectsPage;
