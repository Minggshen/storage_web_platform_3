import { http, API_BASE } from './http';
import type {
  ReportPayload,
  ResultChartsResponse,
  ResultFilePreviewResponse,
  ResultFilesResponse,
  SolverSummaryResponse,
  SolverTask,
} from '../types/api';

export type SolverRunOptions = {
  task_name?: string;
  output_subdir_name?: string;
  population_size?: number;
  generations?: number;
  solver_tier?: 'fast' | 'standard' | 'delivery';
  target_id?: string;
  initial_soc?: number;
  terminal_soc_mode?: string;
  fixed_terminal_soc_target?: number;
  daily_terminal_soc_tolerance?: number;
  safety_economy_tradeoff?: number;
  economic_weight_npv?: number;
  economic_weight_irr?: number;
  economic_weight_payback?: number;
  economic_weight_investment?: number;
  safety_weight_transformer?: number;
  safety_weight_voltage?: number;
  safety_weight_line?: number;
  safety_weight_cycle?: number;
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

export type DeletedSolverTask = {
  project_id: string;
  task_id: string;
  task_dir?: string;
  status_before_delete?: string;
  deleted_bytes?: number;
  deleted_file_count?: number;
  deleted_dir_count?: number;
  deleted_scope?: string;
  preserved_scope?: string[];
};

export async function deleteSolverTask(projectId: string, taskId: string): Promise<DeletedSolverTask> {
  const encodedTaskId = encodeURIComponent(taskId);
  const data = await http<{ success: boolean; deleted_task: DeletedSolverTask }>(
    `/api/solver/project/${projectId}/task/${encodedTaskId}`,
    { method: 'DELETE' },
  );
  return data.deleted_task;
}

function taskQuery(taskId?: string) {
  return taskId ? `?task_id=${encodeURIComponent(taskId)}` : '';
}

export async function fetchSolverSummary(projectId: string, taskId?: string) {
  return http<SolverSummaryResponse>(`/api/solver/project/${projectId}/summary${taskQuery(taskId)}`);
}

export async function fetchReportData(projectId: string, taskId?: string): Promise<ReportPayload> {
  const data = await http<{ success: boolean; project_id: string; payload: ReportPayload }>(
    `/api/solver/project/${projectId}/report-data${taskQuery(taskId)}`,
  );
  return data.payload;
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
