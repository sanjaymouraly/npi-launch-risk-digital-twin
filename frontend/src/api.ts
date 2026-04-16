export const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) || '/api'

export class ApiError extends Error {
  status: number
  details?: unknown
  constructor(message: string, status: number, details?: unknown) {
    super(message)
    this.status = status
    this.details = details
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem('npi_token')
  const headers: Record<string, string> = {
    ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...((init?.headers as Record<string, string>) || {}),
  }
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  } catch (error) {
    throw new ApiError('Cannot reach the API. Is the backend running on port 8000?', 0, error)
  }
  if (!response.ok) {
    let payload: any = null
    try {
      payload = await response.json()
    } catch {
      payload = null
    }
    throw new ApiError(
      payload?.message || payload?.detail || `Request failed (${response.status})`,
      response.status,
      payload,
    )
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}

export type ProjectSummary = {
  id: string
  key: string
  name: string
  product: string
  status: string
  owner: string
  tags: string[]
  start_date: string
  launch_deadline: string | null
  baseline_launch_date: string | null
  delay_cost_per_day: number
  intervention_budget: number
  is_demo: boolean
  task_count: number
  latest_simulation: null | {
    id: string
    created_at: string | null
    p50: number | null
    p90: number | null
    on_time_probability: number | null
    p90_date: string | null
    iterations: number
  }
  updated_at: string | null
}

export type ProjectDetail = Record<string, any> & {
  id: string
  key: string
  name: string
  tasks: any[]
  dependencies: any[]
  resources: any[]
  suppliers: any[]
  components: any[]
  risks: any[]
  milestones: any[]
  latest_simulation: any
}

export type SchedulePayload = {
  project_id: string
  project_key: string
  project_name: string
  calendar: { start_date: string; working_days_per_week: number; holidays: string[]; timezone?: string }
  deadline: string | null
  deadline_offset: number | null
  validation: { valid: boolean; errors: string[]; warnings: string[] }
  cpm: {
    project_duration: number
    finish_date: string
    deadline_margin_days: number | null
    meets_deadline: boolean | null
    critical_path: string[]
    critical_task_ids: string[]
    tasks: any[]
  }
  constrained?: {
    feasible?: boolean
    status?: string
    objective?: string
    makespan?: number
    project_finish_date?: string
    capacity_delay_days?: number
    tasks?: any[]
    bottlenecks?: any[]
    deadline?: { feasible?: boolean; slack_days?: number; conflicts?: string[]; requested_deadline_offset?: number }
    solver?: any
    conflicts?: string[]
    gap?: number | null
  }
  deterministic_heuristic?: any
  bottlenecks?: any[]
  comparison?: {
    unconstrained_days: number
    unconstrained_finish: string
    constrained_days: number
    constrained_finish: string
    capacity_delay_days: number
    deadline_feasible: boolean | null
    headline: string
  }
  assumptions?: Record<string, string>
}

export type SimulationSummary = {
  id: string
  label: string
  scenario_id: string | null
  seed: number
  iterations: number
  status: string
  engine_version: string
  created_at: string
  config: any
  summary: {
    engine: any
    makespan: any
    deadline: any
    cost: any
    histogram: { counts: number[]; bin_edges: number[] }
    convergence: any
    milestones: any[]
    tasks: any[]
    suppliers: any[]
    risks: any[]
    attribution: any
    completion_curve: any[]
    deterministic: any
    warnings: string[]
    assumptions: string[]
    solver_validation?: any
    scenario?: any
    inputs?: any
  }
  samples?: number[]
}

export type Scenario = {
  id: string
  name: string
  description: string
  is_baseline: boolean
  status: string
  intervention_count: number
  total_cost: number
  interventions: Array<{
    id: string
    type: string
    label: string
    target_type: string
    target_id: string | null
    params: any
    cost: number
  }>
  created_at?: string
  approved_at?: string | null
  approved_by?: string | null
}

export type Job = {
  id: string
  project_id: string | null
  kind: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  progress: number
  message: string
  payload: any
  result: any
  error: string | null
  simulation_id?: string
  optimization_id?: string
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export const api = {
  meta: () => request<any>('/meta'),
  stats: () => request<any>('/stats'),
  health: () => request<any>('/health'),

  projects: {
    list: (includeArchived = false) => request<ProjectSummary[]>(`/projects?include_archived=${includeArchived}`),
    get: (id: string) => request<ProjectDetail>(`/projects/${id}`),
    create: (payload: any) => request<any>('/projects', { method: 'POST', body: JSON.stringify(payload) }),
    patch: (id: string, payload: any) =>
      request<any>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
    duplicate: (id: string) => request<any>(`/projects/${id}/duplicate`, { method: 'POST' }),
    archive: (id: string) => request<any>(`/projects/${id}/archive`, { method: 'POST' }),
    schedule: (id: string, mode = 'both') =>
      request<SchedulePayload>(`/projects/${id}/schedule?mode=${mode}&time_limit=15`),
    validation: (id: string) => request<any>(`/projects/${id}/validation`),
    suppliers: (id: string) => request<any>(`/projects/${id}/suppliers`),
    milestones: (id: string) => request<any>(`/projects/${id}/milestones`),
    risks: (id: string) => request<any>(`/projects/${id}/risks`),
    network: (id: string) => request<any>(`/projects/${id}/network`),
    audit: (id: string, limit = 100) => request<any[]>(`/projects/${id}/audit?limit=${limit}`),
    snapshots: (id: string) => request<any[]>(`/projects/${id}/snapshots`),
    exportUrl: (id: string) => apiUrl(`/projects/${id}/export?download=true`),
    importFile: (file: File) => {
      const body = new FormData()
      body.append('file', file)
      return request<any>('/projects/import', { method: 'POST', body })
    },
    importTasks: (id: string, file: File) => {
      const body = new FormData()
      body.append('file', file)
      return request<any>(`/projects/${id}/tasks/import`, { method: 'POST', body })
    },
    csvTemplateUrl: () => apiUrl('/projects/csv-template'),
  },

  simulations: {
    run: (projectId: string, payload: any) =>
      request<any>(`/projects/${projectId}/simulations`, { method: 'POST', body: JSON.stringify(payload) }),
    list: (projectId: string) => request<any[]>(`/projects/${projectId}/simulations`),
    get: (id: string, includeSamples = false) =>
      request<SimulationSummary>(`/simulations/${id}?include_samples=${includeSamples}`),
    latest: (projectId: string) => request<SimulationSummary>(`/projects/${projectId}/simulations/latest`),
    downloadUrl: (id: string, format: 'json' | 'csv' = 'json') =>
      apiUrl(`/simulations/${id}/download?format=${format}`),
    calibration: (projectId: string) => request<any>(`/projects/${projectId}/calibration`),
    sobol: (projectId: string, payload: any) =>
      request<any>(`/projects/${projectId}/attribution/sobol`, { method: 'POST', body: JSON.stringify(payload) }),
    leaveOneOut: (projectId: string, payload: any) =>
      request<any>(`/projects/${projectId}/attribution/leave-one-out`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
  },

  scenarios: {
    list: (projectId: string) => request<Scenario[]>(`/projects/${projectId}/scenarios`),
    get: (id: string) => request<any>(`/scenarios/${id}`),
    create: (projectId: string, payload: any) =>
      request<any>(`/projects/${projectId}/scenarios`, { method: 'POST', body: JSON.stringify(payload) }),
    patch: (id: string, payload: any) =>
      request<any>(`/scenarios/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
    remove: (id: string) => request<any>(`/scenarios/${id}`, { method: 'DELETE' }),
    clone: (id: string, name: string) =>
      request<any>(`/scenarios/${id}/clone`, { method: 'POST', body: JSON.stringify({ name }) }),
    preview: (projectId: string, scenarioId: string) =>
      request<any>(`/projects/${projectId}/scenarios/${scenarioId}/preview`, { method: 'POST' }),
    compare: (projectId: string, payload: any) =>
      request<any>(`/projects/${projectId}/scenarios/compare`, { method: 'POST', body: JSON.stringify(payload) }),
    interventions: (projectId: string) => request<any>(`/projects/${projectId}/interventions`),
  },

  optimization: {
    run: (projectId: string, payload: any) =>
      request<any>(`/projects/${projectId}/optimizations`, { method: 'POST', body: JSON.stringify(payload) }),
    list: (projectId: string) => request<any[]>(`/projects/${projectId}/optimizations`),
    latest: (projectId: string) => request<any>(`/projects/${projectId}/optimizations/latest`),
    get: (id: string) => request<any>(`/optimizations/${id}`),
  },

  ai: {
    status: (projectId: string) => request<any>(`/projects/${projectId}/ai/status`),
    chat: (projectId: string, payload: any) =>
      request<any>(`/projects/${projectId}/ai/chat`, { method: 'POST', body: JSON.stringify(payload) }),
    conversations: (projectId: string) => request<any[]>(`/projects/${projectId}/ai/conversations`),
    conversation: (projectId: string, conversationId: string) =>
      request<any>(`/projects/${projectId}/ai/conversations/${conversationId}`),
    suggestions: (projectId: string) => request<string[]>(`/projects/${projectId}/ai/suggestions`),
    removeConversation: (projectId: string, conversationId: string) =>
      request<any>(`/projects/${projectId}/ai/conversations/${conversationId}`, { method: 'DELETE' }),
  },

  settings: {
    providers: () => request<any>('/settings/providers'),
    update: (provider: string, payload: any) =>
      request<any>(`/settings/providers/${provider}`, { method: 'PATCH', body: JSON.stringify(payload) }),
    test: (provider: string) => request<any>(`/settings/providers/${provider}/test`, { method: 'POST' }),
    models: (provider: string) => request<any>(`/settings/providers/${provider}/models`),
  },

  jobs: {
    get: (id: string) => request<Job>(`/jobs/${id}`),
    list: (projectId?: string) => request<Job[]>(`/jobs${projectId ? `?project_id=${projectId}` : ''}`),
    cancel: (id: string) => request<any>(`/jobs/${id}/cancel`, { method: 'POST' }),
  },
}
