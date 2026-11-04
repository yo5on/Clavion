// Typed client for the Clavion API. Mirrors the Pydantic models in backend/app/main.py.

export interface Health {
  status: 'ok' | 'degraded'
  version: string
  database: boolean
  llm_configured: boolean
  model: string
}

export interface LLMHealth {
  reachable: boolean
  model: string
  model_listed: boolean
  model_capabilities: { input?: string[]; toolCalling?: boolean; reasoning?: boolean } | null
  live_inference: boolean | null
  error: string | null
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) throw new Error(`${path} returned ${r.status}`)
  return r.json() as Promise<T>
}

export const api = {
  health: () => get<Health>('/api/health'),
  llmHealth: (live = false) => get<LLMHealth>(`/api/health/llm${live ? '?live=true' : ''}`),
}
