import { http } from './http';

export type ProjectTopology = {
  nodes: Record<string, unknown>[];
  edges: Record<string, unknown>[];
  economic_parameters?: Record<string, unknown>;
};

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

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
  const data = await http<any>(`/api/topology/project/${projectId}`);
  return normalizeTopology(data);
}

async function putJson(path: string, body: unknown) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  const text = await response.text();
  if (!response.ok) {
    throw new Error(text || `HTTP ${response.status}`);
  }

  return text ? JSON.parse(text) : { success: true };
}

export async function saveProjectTopology(
  projectId: string,
  topology: ProjectTopology
): Promise<ProjectTopology> {
  // 先尝试直接提交 topology
  try {
    const data = await putJson(`/api/topology/project/${projectId}`, topology);
    return normalizeTopology(data);
  } catch {
    // 再尝试包装成 { network: topology }
    const data = await putJson(`/api/topology/project/${projectId}`, {
      network: topology,
    });
    return normalizeTopology(data);
  }
}
