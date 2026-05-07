import { http } from './http';
import type { DashboardPayload } from '../types/api';

export type ProjectListItem = {
  project_id: string;
  project_name: string;
  description?: string | null;
  created_at?: string;
};

export type CreateProjectRequest = {
  project_name?: string;
  name?: string;
  description?: string;
};

export type CreateProjectResponse = {
  success: boolean;
  project: {
    project_id: string;
    project_name: string;
    description?: string | null;
    created_at?: string;
  };
  project_file_path?: string;
};

export type DeleteProjectResponse = {
  success: boolean;
  project_id: string;
  deleted_path?: string;
};

export async function listProjects() {
  return http<{ success: boolean; projects: ProjectListItem[] }>('/api/projects');
}

export async function createProject(payload: CreateProjectRequest) {
  const projectName = payload.project_name ?? payload.name ?? '';
  return http<CreateProjectResponse>('/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      project_name: projectName,
      description: payload.description,
    }),
  });
}

export async function getProjectDashboard(projectId: string) {
  return http<{ success: boolean; dashboard: DashboardPayload }>(`/api/project/${projectId}/dashboard`);
}

export async function deleteProject(projectId: string) {
  return http<DeleteProjectResponse>(`/api/project/${encodeURIComponent(projectId)}`, {
    method: 'DELETE',
  });
}
