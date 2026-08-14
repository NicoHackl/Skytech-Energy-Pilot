import type {
  Allowlist,
  ClassificationResponse,
  Constraint,
  Diagnostics,
  DevicesResponse,
  EntityRow,
  Forecast,
  Health,
  HemsStatus,
  LogRow,
  PlanResponse,
  PromptResponse,
  PublishResult,
  StateReading,
  TestResult,
  Weather,
  Ziel,
} from './types'

/* Einziger Ort im Frontend, an dem fetch aufgerufen wird.

   HA-Ingress: die Oberfläche liegt unter /api/hassio_ingress/<token>/ — jeder Pfad wird
   deshalb **ohne führenden Slash** angegeben und relativ zur Dokumentbasis aufgelöst.
   `/api/state` würde das Ingress-Präfix verlassen und auf der HA-Core-API landen
   (docs/frontend.md). Das Routing ist aus demselben Grund ein HashRouter: der Pfad bleibt
   konstant, damit relative Aufrufe auf jeder Seite gleich auflösen. */

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public details?: unknown,
  ) {
    super(message)
  }
}

/** Deutsche Klartextmeldung für eine Antwort, die kein JSON ist. */
function nonJsonMessage(status: number, text: string): string {
  if (status >= 500 || !text.trim().startsWith('{')) {
    return `Server-Fehler ${status}: keine JSON-Antwort (evtl. Zeitüberschreitung oder Ingress). Details im Addon-Log.`
  }
  return `Unerwartete Antwort (${status}). Details im Addon-Log.`
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  // Bei FormData KEIN Content-Type setzen — sonst fehlt die Multipart-Boundary.
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')

  const response = await fetch(path, { ...options, headers })
  // Antwort erst als Text lesen: hängt ein Aufruf im Ingress, kommt eine HTML-Fehlerseite
  // zurück. `response.json()` würde daran mit „Unexpected token '<'" scheitern — eine
  // Meldung, die dem Nutzer nichts sagt.
  const text = await response.text()
  let body: unknown
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    throw new ApiError(nonJsonMessage(response.status, text), response.status)
  }

  if (!response.ok) {
    const detail = (body as { reason?: unknown; error?: unknown } | null)?.reason
      ?? (body as { error?: unknown } | null)?.error
    const message = typeof detail === 'string' ? detail : `Anfrage fehlgeschlagen (${response.status}).`
    throw new ApiError(message, response.status, body)
  }
  return body as T
}

const post = (data?: unknown): RequestInit => ({
  method: 'POST',
  ...(data === undefined ? {} : { body: JSON.stringify(data) }),
})

const del = (data: unknown): RequestInit => ({ method: 'DELETE', body: JSON.stringify(data) })

/** Jeder Endpunkt ist ein benannter Eintrag — kein roher Pfad in einer Seite. */
export const api = {
  health: () => request<Health>('api/health'),
  diagnostics: () => request<Diagnostics>('api/diagnostics'),
  allowlist: () => request<Allowlist>('api/allowlist'),
  haTest: () => request<TestResult>('api/ha/test'),

  state: () => request<Record<string, StateReading>>('api/state'),
  entities: () => request<EntityRow[]>('api/entities'),

  devices: () => request<DevicesResponse>('api/devices'),
  saveExtra: (data: {
    device_name: string
    read_entity_id: string
    ai_suggestion: boolean
    ai_hint: string
    label: string
    unit: string
    write_original: boolean
  }) => request<{ ok: boolean; reason?: string }>('api/devices/extras', post(data)),
  deleteExtra: (data: { device_name: string; read_entity_id: string }) =>
    request<{ ok: boolean; reason?: string }>('api/devices/extras', del(data)),
  saveDevicePrompt: (data: { device_name: string; prompt: string }) =>
    request<{ ok: boolean; is_custom?: boolean; reason?: string }>('api/devices/prompt', post(data)),

  forecast: () => request<Forecast>('api/forecast'),
  weather: () => request<Weather>('api/weather'),
  weatherTest: () => request<TestResult>('api/weather/test'),

  hemsStatus: (refresh = false) => request<HemsStatus>(`api/hems/status${refresh ? '?refresh=1' : ''}`),
  hemsTest: () => request<TestResult>('api/hems/test'),
  hemsRediscover: () =>
    request<{ source: string; device_count: number }>('api/hems/rediscover', post()),

  constraints: () => request<{ devices: Constraint[] }>('api/constraints'),

  ziele: () => request<{ ziele: Ziel[] }>('api/ziele'),
  saveZiel: (data: { id: number | null; name: string; beschreibung: string; devices: string[] }) =>
    request<{ ok: boolean; reason?: string }>('api/ziele', post(data)),
  deleteZiel: (id: number) => request<{ ok: boolean }>('api/ziele', del({ id })),

  prompt: () => request<PromptResponse>('api/prompt'),
  savePrompt: (prompt: string) =>
    request<{ ok: boolean; is_custom?: boolean; reason?: string }>('api/prompt', post({ prompt })),
  classificationPrompt: () => request<PromptResponse>('api/classification-prompt'),
  saveClassificationPrompt: (prompt: string) =>
    request<{ ok: boolean; is_custom?: boolean; reason?: string }>('api/classification-prompt', post({ prompt })),

  plan: () => request<PlanResponse>('api/plan'),
  runPlan: () => request<PlanResponse>('api/plan/run', post()),
  runClassification: () => request<ClassificationResponse>('api/classification/run', post()),
  publishPlan: () => request<PublishResult>('api/plan/publish', post()),
  aiTest: () => request<TestResult>('api/ai/test'),

  logs: (limit = 200) => request<LogRow[]>(`api/logs?limit=${limit}`),
  /** Der Export ist ein Download-Link, kein fetch — Pfad hier, damit auch er an einer Stelle steht. */
  logsExportPath: 'api/logs/export',
}
