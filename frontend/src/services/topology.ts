import { http } from './http';

export type ProjectTopology = {
  nodes: Record<string, unknown>[];
  edges: Record<string, unknown>[];
  economic_parameters?: Record<string, unknown>;
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function normalizeTopology(data: any): ProjectTopology {
  if (data?.project?.network) {
    return {
      nodes: Array.isArray(data.project.network.nodes) ? data.project.network.nodes : [],
      edges: Array.isArray(data.project.network.edges) ? data.project.network.edges : [],
      economic_parameters:
        typeof data.project.network.economic_parameters === 'object' && data.project.network.economic_parameters !== null
          ? data.project.network.economic_parameters
          : {},
    };
  }

  if (data?.network) {
    return {
      nodes: Array.isArray(data.network.nodes) ? data.network.nodes : [],
      edges: Array.isArray(data.network.edges) ? data.network.edges : [],
      economic_parameters:
        typeof data.network.economic_parameters === 'object' && data.network.economic_parameters !== null
          ? data.network.economic_parameters
          : {},
    };
  }

  if (data?.topology) {
    return {
      nodes: Array.isArray(data.topology.nodes) ? data.topology.nodes : [],
      edges: Array.isArray(data.topology.edges) ? data.topology.edges : [],
      economic_parameters:
        typeof data.topology.economic_parameters === 'object' && data.topology.economic_parameters !== null
          ? data.topology.economic_parameters
          : {},
    };
  }

  return { nodes: [], edges: [], economic_parameters: {} };
}

export async function fetchProjectTopology(projectId: string): Promise<ProjectTopology> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = await http<any>(`/api/topology/project/${encodeURIComponent(projectId)}`);
  return normalizeTopology(data);
}

async function putJson(path: string, body: unknown) {
  return http(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export async function saveProjectTopology(
  projectId: string,
  topology: ProjectTopology
): Promise<ProjectTopology> {
  const encodedProjectId = encodeURIComponent(projectId);
  // 先尝试直接提交 topology
  try {
    const data = await putJson(`/api/topology/project/${encodedProjectId}`, topology);
    return normalizeTopology(data);
  } catch (firstErr) {
    // 再尝试包装成 { network: topology }
    try {
      const data = await putJson(`/api/topology/project/${encodedProjectId}`, {
        network: topology,
      });
      return normalizeTopology(data);
    } catch {
      throw firstErr;
    }
  }
}

// ── Topology template APIs ──

export type TemplateMeta = {
  template_id: string;
  name: string;
  description: string;
  created_at: string;
  node_count: number;
  edge_count: number;
};

export async function fetchTemplates(): Promise<TemplateMeta[]> {
  const data = await http<{ success: boolean; templates: TemplateMeta[] }>('/api/topology/templates');
  return data.templates ?? [];
}

export async function saveTemplate(name: string, description: string, topology: ProjectTopology): Promise<string> {
  const data = await http<{ success: boolean; template: Record<string, unknown> }>('/api/topology/templates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description, topology }),
  });
  return String(data.template?.template_id ?? '');
}

export async function fetchTemplateDetail(templateId: string): Promise<ProjectTopology> {
  const data = await http<{ success: boolean; template: Record<string, unknown> }>(
    `/api/topology/templates/${encodeURIComponent(templateId)}`,
  );
  const topology = (data.template?.topology ?? data.template ?? {}) as Record<string, unknown>;
  return {
    nodes: Array.isArray(topology.nodes) ? topology.nodes : [],
    edges: Array.isArray(topology.edges) ? topology.edges : [],
    economic_parameters: typeof topology.economic_parameters === 'object' && topology.economic_parameters !== null
      ? topology.economic_parameters as Record<string, unknown>
      : {},
  };
}

export async function deleteTemplate(templateId: string): Promise<void> {
  await http<unknown>(`/api/topology/templates/${encodeURIComponent(templateId)}`, { method: 'DELETE' });
}
