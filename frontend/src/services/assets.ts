const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

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
  const response = await fetch(`${API_BASE}/api/assets/project/${projectId}`);
  const data = await parseJsonResponse(response);
  return Array.isArray(data?.assets) ? (data.assets as ProjectAsset[]) : [];
}
