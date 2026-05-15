import { http } from './http';
import type {
  ResultChartsResponse,
  ResultFilePreviewResponse,
  ResultFilesResponse,
  SolverSummaryResponse,
  SolverTask,
} from '../types/api';

export type SolverRunOptions = {
  task_name?: string;
  disable_plots?: boolean;
  output_subdir_name?: string;
  population_size?: number;
  generations?: number;
  target_id?: string;
  enable_opendss_oracle?: boolean;
  initial_soc?: number;
  terminal_soc_mode?: string;
  fixed_terminal_soc_target?: number;
  daily_terminal_soc_tolerance?: number;
  safety_economy_tradeoff?: number;
};

export async function fetchLatestSolverTask(projectId: string): Promise<SolverTask | null> {
  const data = await http<{ success: boolean; project_id: string; task: SolverTask | null }>(
    `/api/solver/project/${projectId}/latest`,
  );
  return data.task;
}

export async function fetchSolverTasks(projectId: string): Promise<SolverTask[]> {
  const data = await http<{ success: boolean; project_id: string; tasks: SolverTask[] }>(
    `/api/solver/project/${projectId}/tasks`,
  );
  return Array.isArray(data.tasks) ? data.tasks : [];
}

export async function fetchTaskLogs(taskId: string, projectId?: string): Promise<SolverTask> {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
  const data = await http<{ success: boolean; task: SolverTask }>(`/api/solver/task/${taskId}/logs${query}`);
  return data.task;
}

export async function cancelSolverTask(projectId: string, taskId: string): Promise<SolverTask> {
  const data = await http<{ success: boolean; task: SolverTask }>(
    `/api/solver/project/${projectId}/task/${taskId}/cancel`,
    { method: 'POST' },
  );
  return data.task;
}

function taskQuery(taskId?: string) {
  return taskId ? `?task_id=${encodeURIComponent(taskId)}` : '';
}

export async function fetchSolverSummary(projectId: string, taskId?: string) {
  return http<SolverSummaryResponse>(`/api/solver/project/${projectId}/summary${taskQuery(taskId)}`);
}

export async function fetchResultCharts(projectId: string, taskId?: string) {
  return http<ResultChartsResponse>(`/api/solver/project/${projectId}/charts${taskQuery(taskId)}`);
}

export async function fetchResultFiles(projectId: string, taskId?: string) {
  return http<ResultFilesResponse>(`/api/solver/project/${projectId}/result-files${taskQuery(taskId)}`);
}

export async function fetchResultFilePreview(projectId: string, relativePath: string, group?: string, taskId?: string) {
  const query = new URLSearchParams({ relative_path: relativePath });
  if (group) query.set('group', group);
  if (taskId) query.set('task_id', taskId);
  return http<ResultFilePreviewResponse>(`/api/solver/project/${projectId}/result-file?${query.toString()}`);
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';

export function getResultFileDownloadUrl(projectId: string, relativePath: string, group?: string, taskId?: string) {
  const query = new URLSearchParams({ relative_path: relativePath });
  if (group) query.set('group', group);
  if (taskId) query.set('task_id', taskId);
  return `${API_BASE}/api/solver/project/${projectId}/result-file/download?${query.toString()}`;
}

export async function rerunSolver(projectId: string, options: SolverRunOptions = {}) {
  return http<{ success: boolean; task: SolverTask }>(`/api/solver/project/${projectId}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      task_name: 'ui_rerun_check',
      output_subdir_name: 'integrated_optimization',
      ...options,
    }),
  });
}
