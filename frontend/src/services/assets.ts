import { http, API_BASE } from './http';

export type ProjectAsset = {
  file_id: string;
  file_name?: string | null;
  source_type?: string | null;
  metadata?: Record<string, unknown>;
};

async function parseJsonResponse(response: Response) {
  const text = await response.text();
  if (!response.ok) {
    throw new Error(text || `HTTP ${response.status}`);
  }
  return text ? JSON.parse(text) : { success: true };
}

async function postFormWithFallback(paths: string[], formData: FormData) {
  let lastError = '上传失败。';

  for (const path of paths) {
    try {
      const response = await fetch(`${API_BASE}${path}`, {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        return await parseJsonResponse(response);
      }

      const text = await response.text();
      lastError = text || `HTTP ${response.status}`;
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
    }
  }

  throw new Error(lastError);
}

export async function uploadTariffFile(projectId: string, file: File) {
  const formData = new FormData();
  formData.append('file', file);

  return postFormWithFallback(
    [
      `/api/assets/project/${projectId}/tariff/upload`,
      `/api/assets/project/${projectId}/tariff`,
      `/api/project/${projectId}/tariff/upload`,
    ],
    formData,
  );
}

export async function uploadDeviceLibraryFile(projectId: string, file: File) {
  const formData = new FormData();
  formData.append('file', file);

  return postFormWithFallback(
    [
      `/api/assets/project/${projectId}/device-library/upload`,
      `/api/assets/project/${projectId}/device-library`,
      `/api/project/${projectId}/device-library/upload`,
    ],
    formData,
  );
}

export async function uploadRuntimeFile(
  projectId: string,
  nodeId: string,
  kind: 'year_map' | 'model_library',
  file: File,
) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('node_id', nodeId);
  formData.append('kind', kind);

  return postFormWithFallback(
    [
      `/api/assets/project/${projectId}/runtime/upload`,
      `/api/assets/project/${projectId}/runtime`,
      `/api/project/${projectId}/runtime/upload`,
    ],
    formData,
  );
}

export async function listProjectAssets(projectId: string): Promise<ProjectAsset[]> {
  const data = await http<{ assets?: ProjectAsset[] }>(`/api/assets/project/${projectId}`);
  return Array.isArray(data?.assets) ? (data.assets as ProjectAsset[]) : [];
}

export async function uploadRawLoadData(
  projectId: string,
  nodeId: string,
  file: File,
): Promise<{ success: boolean; node_id: string; file_name: string; stored_path: string }> {
  const form = new FormData();
  form.append('project_id', projectId);
  form.append('node_id', nodeId);
  form.append('file', file);
  const res = await fetch(`${API_BASE}/api/assets/raw-load-data/upload`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listUploadedNodes(
  projectId: string,
): Promise<{ uploaded_nodes: string[]; processed_nodes: string[] }> {
  return http(`/api/assets/raw-load-data/uploaded/${projectId}`);
}

export async function deleteRawLoadData(
  projectId: string,
  nodeId: string,
): Promise<{ success: boolean; deleted: boolean }> {
  return http(`/api/assets/raw-load-data/${projectId}/${nodeId}`, { method: 'DELETE' });
}

export function processRuntime(
  projectId: string,
  nodeIds: string[],
  onEvent: (event: Record<string, unknown>) => void,
  onDone: () => void,
  onError: (err: Error) => void,
): AbortController {
  const controller = new AbortController();
  const body = JSON.stringify({ project_id: projectId, node_ids: nodeIds });

  fetch(`${API_BASE}/api/assets/process-runtime`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    signal: controller.signal,
  }).then(async (res) => {
    if (!res.ok) { onError(new Error(await res.text())); return; }
    const reader = res.body?.getReader();
    if (!reader) { onDone(); return; }
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try { onEvent(JSON.parse(line.slice(6))); } catch { /* malformed SSE line, skip */ }
        }
      }
    }
    onDone();
  }).catch((err) => {
    if (err.name !== 'AbortError') onError(err);
  });

  return controller;
}

export async function listPreviewFiles(
  projectId: string,
  nodeId: string,
): Promise<{ node_id: string; files: Array<{ name: string; type: string; url: string }> }> {
  return http(`/api/assets/preview/${projectId}/${nodeId}`);
}

export async function fetchPreviewContent(
  projectId: string,
  nodeId: string,
  fileName: string,
): Promise<{ file_name?: string; columns?: string[]; rows?: Array<Record<string, string>>; content?: string } | Blob> {
  const url = `${API_BASE}/api/assets/preview/${projectId}/${nodeId}/${fileName}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('image')) return res.blob();
  return res.json();
}
