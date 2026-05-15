const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';
const API_TIMEOUT_FROM_ENV = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? 60000);
const API_TIMEOUT_MS = Number.isFinite(API_TIMEOUT_FROM_ENV) && API_TIMEOUT_FROM_ENV > 0 ? API_TIMEOUT_FROM_ENV : 60000;

export async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), API_TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: init?.signal ?? controller.signal,
    });
    const text = await response.text();
    if (!response.ok) {
      throw new Error(text || `HTTP ${response.status}`);
    }
    return text ? (JSON.parse(text) as T) : ({} as T);
  } catch (err) {
    const name = (err as { name?: string }).name;
    const message = (err as { message?: string }).message ?? '';
    if (name === 'AbortError') {
      throw new Error(`请求超时：${API_BASE}${path} 在 ${Math.round(API_TIMEOUT_MS / 1000)} 秒内没有响应。`);
    }
    if (message.includes('Failed to fetch')) {
      throw new Error(API_BASE ? `无法连接后端服务：${API_BASE}` : '无法连接后端服务，请确认服务已启动。');
    }
    throw err;
  } finally {
    window.clearTimeout(timeoutId);
  }
}
