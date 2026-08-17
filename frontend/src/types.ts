/* Datenverträge zum Backend. Spiegeln die Antworten aus docs/api-referenz.md.
   Bewusst tolerant: das Backend darf Felder ergänzen, ohne das Frontend zu brechen —
   deshalb optionale Felder statt exakter Pflichtstrukturen. */

/** Herkunft eines gelesenen Werts (`live`, `fallback`, `hems`, …). */
export type Source = string

export interface Health {
  status: string
  version: string
  provider: string
  model: string
  ha_configured: boolean
}

export interface Diagnostics {
  ha_configured?: boolean
  poller_active?: boolean
  poll_interval_s?: number
  mapped_roles?: string[]
  last_collect_ts?: number | null
  last_error?: string | null
}

export interface AllowlistEntry {
  entity_id: string
  source: Source
}

export interface Allowlist {
  count: number
  by_source?: Record<string, number>
  entries?: AllowlistEntry[]
}

/** Ein Messwert einer Rolle; Leistungsgrößen tragen zusätzlich die 1/15/60-min-Mittel. */
export interface StateReading {
  label: string
  value: number | null
  latest?: number | null
  unit?: string
  source: Source
  averaged?: boolean
  mean_1m?: number | null
  mean_15m?: number | null
  mean_60m?: number | null
}

export interface EntityRow {
  label: string
  entity_id: string | null
  averaged?: boolean
}

export type DeviceClass = 'controllable' | 'binary'
export type ExtraKind = 'number' | 'bool' | 'datetime' | 'select' | 'text' | 'auto'
/** Semantik eines Zusatzwerts (D-061): Messwert, User-Grenze oder Sollwert. */
export type ExtraRole = 'ist' | 'grenze' | 'sollwert'
/** Aufgelöste Steuerquelle der HEMS-Modus-Achse (D-057). */
export type ControlSource = 'ep' | 'user' | 'aus'

export interface DeviceField {
  label: string
  value: number | boolean | string | null
  kind?: string
  unit?: string
  entity_id: string
  source: Source
}

export interface DeviceExtra {
  read_entity_id: string
  label?: string
  unit?: string
  kind: ExtraKind
  value: number | boolean | string | null
  source: Source
  ai_suggestion: boolean
  ai_hint?: string
  rolle?: ExtraRole
  rolle_bedeutung?: string
  suggestion_entity_id?: string
  write_original?: boolean
  should_write_original?: boolean
  attrs?: {
    min?: number | null
    max?: number | null
    unit_of_measurement?: string
    has_date?: boolean
    has_time?: boolean
    options?: string[]
  }
}

export interface Device {
  name: string
  label: string
  class: DeviceClass
  fields: DeviceField[]
  extras?: DeviceExtra[]
  ai_prompt?: string
  /** Freitext-Betriebsregeln des Users (D-060), getrennt von der Beschreibung. */
  ai_regeln?: string
  mode?: string | null
  global_mode?: string | null
  control_source?: ControlSource
  mode_entity_id?: string
}

export interface DevicesResponse {
  devices: Device[]
  source: string
  /** Auswahlpool für das Rollen-Feld eines Zusatzwerts (D-061). */
  extra_roles?: ExtraRole[]
}

/** Freitext-Regeln: hausweit plus je Gerät (D-060). */
export interface RegelnResponse {
  global: string
  devices: Record<string, string>
}

export interface ForecastValue {
  key: string
  label: string
  total: number | null
}

export interface ForecastOrientation {
  label: string
  values: Record<string, { value: number | null; entity_id: string; source: Source }>
}

export interface Forecast {
  unit?: string
  values?: ForecastValue[]
  orientations?: ForecastOrientation[]
}

export interface WeatherSlot {
  dt?: number
  time?: string
  temp?: number | null
  temp_min?: number | null
  temp_max?: number | null
  clouds?: number | null
  pop?: number | null
  wind_speed?: number | null
  condition?: string
}

export interface WeatherTimeline {
  enabled?: boolean
  refresh_min?: number
  pages?: number
  last_fetch_ts?: number | null
  last_error?: string | null
  slots?: WeatherSlot[]
}

export interface WeatherAlert {
  event?: string
  sender_name?: string
  start?: number
  end?: number
  tags?: string[]
  description?: string
}

export interface Weather {
  enabled: boolean
  source?: string
  zone_entity?: string
  coords?: { lat: number; lon: number } | null
  last_fetch_ts?: number | null
  last_error?: string | null
  forecast?: { city?: string; country?: string; slots?: WeatherSlot[] } | null
  timelines?: Record<string, WeatherTimeline>
  ai_models?: string[]
  alerts_enabled?: boolean
  alerts?: WeatherAlert[]
  daily_call_budget?: number | null
  calls_today?: number
  budget_exhausted?: boolean
}

export interface ConstraintExtra {
  extra: { read_entity_id: string; label?: string; unit?: string; ai_suggestion?: boolean }
  value: number | boolean | string | null
}

export interface Constraint {
  name: string
  label: string
  class: DeviceClass
  output_unit?: string
  is_battery?: boolean
  freigabe: boolean | null
  fixed_power?: number | null
  min_power?: number | null
  max_power?: number | null
  forced_prio?: number | null
  extras?: ConstraintExtra[]
  suggestion_keys?: string[]
}

export interface Ziel {
  id: number
  name: string
  beschreibung?: string
  devices?: string[]
}

export interface Objective {
  key: string
  label: string
  weight: number
}

export interface AiCall {
  provider?: string
  model?: string
  tokens_in?: number | null
  tokens_out?: number | null
  ok?: boolean
  error?: string | null
  /** D-063: Anbieter hat temperature/seed verworfen – Determinismus ist dann nicht aktiv. */
  sampling_dropped?: boolean
  /** D-063: Antwort kam aus dem Vorplan, es gab keinen KI-Aufruf. */
  reused?: boolean
}

/** Ein Geräte-Eintrag im Plan: `name` plus die je Gerät erlaubten Vorschlagsfelder. */
export type PlanDevice = { name: string } & Record<string, number | boolean | string | null>

export interface Plan {
  plan_id?: string
  provider?: string
  model?: string
  /** Aggregierte Konfidenz: schwächstes Glied der Teilnoten (D-064). */
  confidence?: number | null
  konfidenz_teilnoten?: Record<string, number>
  unsicherheiten?: string[]
  valid_from?: string
  valid_until?: string
  devices?: PlanDevice[]
  reasoning?: string
  warnings?: string[]
}

export interface Validation {
  ok?: boolean
  errors?: string[]
  clamped?: string[]
  /** Grund, warum ein gültiger Plan nicht nach HA geschrieben wurde (D-064). */
  publish_blocked?: string | null
}

export interface PublishResult {
  ok?: boolean
  written?: string[]
  failed?: { entity_id: string; error: string }[]
  skipped?: { entity_id: string; device?: string; source?: string; reason: string }[]
  reason?: string
}

export interface PlanResponse {
  ok?: boolean
  plan?: Plan | null
  validation?: Validation
  ai_call?: AiCall
  context?: unknown
  published?: PublishResult | null
  error?: string | null
  ts?: string
  /** D-063: Kontext unverändert => kein KI-Aufruf, der gespeicherte Plan gilt weiter. */
  reused?: boolean
  context_hash?: string | null
}

export interface ClassificationResponse {
  ok?: boolean
  objectives?: Objective[]
  reasoning?: string
  ai_call?: AiCall
  context?: unknown
  error?: string | null
}

export interface PromptResponse {
  prompt: string
  default: string
  is_custom: boolean
}

export interface HemsFeedbackField {
  feld: string
  vorschlag: number | boolean | null
  ist: number | boolean | null
  status: 'match' | 'abweichend' | 'unbekannt' | string
}

export interface HemsFeedbackDevice {
  label: string
  verdict: string
  matched?: boolean
  fields?: HemsFeedbackField[]
}

export interface HemsFeedback {
  overall: string
  plan_id?: string
  valid_until?: string
  reason?: string
  devices?: HemsFeedbackDevice[]
}

export interface HemsDeviceState {
  id: string
  label?: string
  type?: string
  priority?: number | null
  eligible?: boolean
  actual_w?: number | null
  actual_on?: boolean
}

export interface HemsStatus {
  configured: boolean
  online?: boolean
  last_fetch_ts?: number | null
  last_cycle_at?: string | null
  cycle_count?: number | null
  interval_s?: number | null
  pool_w?: number | null
  current_deficit_w?: number | null
  global_mode?: string | null
  error?: string | null
  last_error?: string | null
  feedback?: HemsFeedback | null
  devices?: HemsDeviceState[]
}

export interface LogRow {
  ts: string
  level: string
  component: string
  message: string
}

export interface TestResult {
  connected?: boolean
  reason?: string
  result?: Record<string, unknown>
}
