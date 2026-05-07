import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createProject } from '../../services/projects';

function ProjectCreatePage() {
  const navigate = useNavigate();

  const [name, setName] = useState('前端联调测试项目');
  const [description, setDescription] = useState('用于测试前端工作流页面');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const res = await createProject({
        name: name.trim(),
        description: description.trim(),
      });

      const projectId = res.project?.project_id;
      if (!projectId) {
        throw new Error('创建成功，但未返回 project_id');
      }

      navigate(`/projects/${projectId}/overview`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ padding: 24, background: '#f8fafc', minHeight: '100vh' }}>
      <div style={{ maxWidth: 880, margin: '0 auto' }}>
        <div style={{ marginBottom: 16 }}>
          <Link
            to="/projects"
            style={{ color: '#2563eb', textDecoration: 'none', fontWeight: 600 }}
          >
            ← 返回项目列表
          </Link>
        </div>

        <div
          style={{
            background: '#ffffff',
            border: '1px solid #e5e7eb',
            borderRadius: 16,
            padding: 24,
          }}
        >
          <div style={{ fontSize: 13, color: '#64748b', marginBottom: 8 }}>项目创建</div>
          <h1 style={{ margin: 0, fontSize: 32 }}>新建项目</h1>
          <div style={{ color: '#64748b', marginTop: 8, marginBottom: 20 }}>
            创建一个新的配电网储能优化前后端联调项目。
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
              创建失败：{error}
            </div>
          ) : null}

          <form onSubmit={onSubmit}>
            <div style={{ marginBottom: 16 }}>
              <label style={labelStyle}>项目名称</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                style={inputStyle}
                placeholder="请输入项目名称"
              />
            </div>

            <div style={{ marginBottom: 20 }}>
              <label style={labelStyle}>项目说明</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                style={textareaStyle}
                placeholder="请输入项目说明"
              />
            </div>

            <div style={{ display: 'flex', gap: 12 }}>
              <button type="submit" disabled={submitting || !name.trim()} style={primaryBtnStyle}>
                {submitting ? '创建中...' : '创建项目'}
              </button>
              <Link to="/projects" style={secondaryLinkStyle}>
                取消
              </Link>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 14,
  color: '#374151',
  marginBottom: 8,
  fontWeight: 600,
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  border: '1px solid #d1d5db',
  borderRadius: 12,
  padding: '12px 14px',
  fontSize: 14,
};

const textareaStyle: React.CSSProperties = {
  width: '100%',
  minHeight: 120,
  boxSizing: 'border-box',
  border: '1px solid #d1d5db',
  borderRadius: 12,
  padding: '12px 14px',
  fontSize: 14,
  resize: 'vertical',
};

const primaryBtnStyle: React.CSSProperties = {
  padding: '10px 16px',
  borderRadius: 12,
  border: '1px solid #111827',
  background: '#111827',
  color: '#ffffff',
  fontWeight: 700,
  cursor: 'pointer',
};

const secondaryLinkStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '10px 16px',
  borderRadius: 12,
  border: '1px solid #d1d5db',
  background: '#ffffff',
  color: '#111827',
  textDecoration: 'none',
  fontWeight: 600,
};

export { ProjectCreatePage };
export default ProjectCreatePage;