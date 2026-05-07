import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createProject } from '../../services/projects';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';

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
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-[880px]">
        {/* Breadcrumb */}
        <div className="mb-4">
          <Link to="/projects" className="font-semibold text-primary no-underline hover:underline">
            &larr; 返回项目列表
          </Link>
        </div>

        {/* Form card */}
        <div className="rounded-2xl border border-border bg-card p-6">
          <div className="mb-2 text-[13px] text-muted-foreground">项目创建</div>
          <h1 className="m-0 text-[32px] font-extrabold tracking-tight text-foreground">新建项目</h1>
          <p className="mt-2 mb-5 text-sm text-muted-foreground">
            创建一个新的配电网储能优化前后端联调项目。
          </p>

          {error ? (
            <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3.5 text-sm text-red-600">
              创建失败：{error}
            </div>
          ) : null}

          <form onSubmit={onSubmit}>
            <div className="mb-4">
              <Label htmlFor="project-name" className="mb-2 block text-sm font-semibold">
                项目名称
              </Label>
              <Input
                id="project-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="请输入项目名称"
              />
            </div>

            <div className="mb-5">
              <Label htmlFor="project-desc" className="mb-2 block text-sm font-semibold">
                项目说明
              </Label>
              <Textarea
                id="project-desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="请输入项目说明"
                className="min-h-[120px]"
              />
            </div>

            <div className="flex gap-3">
              <Button type="submit" disabled={submitting || !name.trim()}>
                {submitting ? '创建中...' : '创建项目'}
              </Button>
              <Button variant="outline" asChild>
                <Link to="/projects">取消</Link>
              </Button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export { ProjectCreatePage };
export default ProjectCreatePage;
