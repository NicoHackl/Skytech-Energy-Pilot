import { useState } from 'react'
import { api } from '../api'
import { Alert, Card, DataTable, Empty, Loading, fmt, fmtUnit, srcDe, tsDE, usePoll } from '../components/Data'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { useToast } from '../components/Toast'
import type { Forecast, Weather, WeatherSlot } from '../types'

/* PV-Prognose (aus HA-Sensoren, D-006/D-018/D-026) und Wetter (direkt über
   OpenWeatherMap, D-042/D-044). Beides nur EP-intern: keine HA-Sensoren, keine
   HEMS-Übergabe. */

export function Prognose() {
  const forecast = usePoll(() => api.forecast(), true)
  const weather = usePoll(() => api.weather(), true)
  const [testing, setTesting] = useState(false)
  const { toast } = useToast()

  const testWeather = async () => {
    setTesting(true)
    try {
      const data = await api.weatherTest()
      toast(weatherTestMessage(data), data.connected ? 'ok' : 'err')
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err), 'err')
    } finally {
      setTesting(false)
      void weather.reload()
    }
  }

  return (
    <>
      <PageHeader
        title="Prognose"
        subtitle="PV-Ertrag und Wetter"
        actions={
          <>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                void forecast.reload()
                void weather.reload()
              }}
            >
              <Icon name="refresh" size={16} />
              Aktualisieren
            </button>
            <button type="button" className="btn btn-ghost" disabled={testing} onClick={() => void testWeather()}>
              {testing ? 'Teste…' : 'Wetterabruf testen'}
            </button>
          </>
        }
      />
      <div className="content">
        <Card title="PV-Prognose" sub="Summe über alle Ausrichtungen">
          {forecast.error ? (
            <Alert>{forecast.error}</Alert>
          ) : !forecast.data ? (
            <Loading />
          ) : (
            <ForecastView data={forecast.data} />
          )}
        </Card>

        <Card title="Wetter (OpenWeatherMap)">
          {weather.error ? (
            <Alert>{weather.error}</Alert>
          ) : !weather.data ? (
            <Loading />
          ) : (
            <WeatherView data={weather.data} />
          )}
        </Card>
      </div>
    </>
  )
}

/** Testergebnis als ein Satz — je nach Quelle mit Timeline- und Budget-Angaben. */
function weatherTestMessage(data: { connected?: boolean; reason?: string; result?: Record<string, unknown> }): string {
  const result = (data.result ?? {}) as {
    timelines?: { resolution: string; ok: boolean; slots?: number; pages?: number; reason?: string }[]
    alerts?: { ok: boolean; count?: number; reason?: string }
    daily_call_budget?: number
    calls_today?: number
    city?: string
    slots?: number
    reason?: string
  }
  if (Array.isArray(result.timelines)) {
    const parts = result.timelines.map((timeline) =>
      timeline.ok
        ? `${timeline.resolution}: ${timeline.slots ?? 0} Werte${timeline.pages && timeline.pages > 1 ? ` (${timeline.pages} Seiten)` : ''}`
        : `${timeline.resolution}: ${timeline.reason ?? 'fehlgeschlagen'}`,
    )
    if (result.alerts) {
      parts.push(result.alerts.ok ? `Warnungen: ${result.alerts.count ?? 0}` : `Warnungen: ${result.alerts.reason ?? 'fehlgeschlagen'}`)
    }
    if (result.daily_call_budget != null) parts.push(`Budget ${result.calls_today ?? 0}/${result.daily_call_budget}`)
    return parts.join(' · ')
  }
  if (data.connected) return `Abruf erfolgreich: ${result.city ?? 'ok'} (${result.slots ?? 0} Zeitschritte)`
  return result.reason ?? data.reason ?? 'Wetterabruf fehlgeschlagen.'
}

function ForecastView({ data }: { data: Forecast }) {
  const unit = data.unit ?? ''
  const values = data.values ?? []
  const labels = Object.fromEntries(values.map((value) => [value.key, value.label]))

  if (!values.length) {
    return (
      <Empty
        icon="sun"
        text="Keine PV-Prognose konfiguriert. Die Ausrichtungen und ihre Sensoren werden in der Addon-Konfiguration unter „PV-Prognose-Ausrichtungen“ gepflegt."
      />
    )
  }

  return (
    <>
      <DataTable
        head={
          <tr>
            <th>Wert</th>
            <th className="num">Summe</th>
          </tr>
        }
      >
        {values.map((value) => (
          <tr key={value.key}>
            <td className="cell-title">{value.label}</td>
            <td className="num">{fmtUnit(value.total, unit)}</td>
          </tr>
        ))}
      </DataTable>

      {(data.orientations ?? []).map((orientation) => (
        <div key={orientation.label}>
          <h3>{orientation.label}</h3>
          <DataTable
            head={
              <tr>
                <th>Wert</th>
                <th className="num">Wert</th>
                <th>Entität</th>
                <th>Quelle</th>
              </tr>
            }
          >
            {Object.entries(orientation.values).map(([key, field]) => (
              <tr key={key}>
                <td className="cell-title">{labels[key] ?? key}</td>
                <td className="num">{fmtUnit(field.value, unit)}</td>
                <td>
                  <code className="mono">{field.entity_id}</code>
                </td>
                <td>
                  <span className={`pill ${field.source === 'live' ? 'ok' : 'muted'}`}>{srcDe(field.source)}</span>
                </td>
              </tr>
            ))}
          </DataTable>
        </div>
      ))}
    </>
  )
}

function slotTime(slot: WeatherSlot): string {
  if (slot.dt) return tsDE(slot.dt)
  return slot.time ?? '–'
}

function WeatherView({ data }: { data: Weather }) {
  if (!data.enabled) {
    return (
      <Empty
        icon="sun"
        text="Wetterabruf inaktiv. Den OpenWeatherMap-Schlüssel in der Addon-Konfiguration unter „Wetter“ eintragen."
      />
    )
  }
  const coords = data.coords ? `${fmt(data.coords.lat)} / ${fmt(data.coords.lon)}` : '–'
  return data.source === 'onecall' ? (
    <OneCallView data={data} coords={coords} />
  ) : (
    <Forecast3hView data={data} coords={coords} />
  )
}

function Forecast3hView({ data, coords }: { data: Weather; coords: string }) {
  const forecast = data.forecast
  const place = forecast?.city ? `${forecast.city}${forecast.country ? `, ${forecast.country}` : ''}` : '–'
  const slots = forecast?.slots ?? []

  return (
    <>
      <div className="info-strip">
        <Icon name="info" size={16} />
        <span>
          Ort <b>{place}</b> · Zone <code className="mono">{data.zone_entity}</code> ({coords}) · Stand{' '}
          {tsDE(data.last_fetch_ts)}
          {data.last_error ? ` · Fehler: ${data.last_error}` : ''}
        </span>
      </div>
      {slots.length ? (
        <SlotTable slots={slots} daily={false} />
      ) : (
        <p className="muted">Noch keine Prognose abgerufen.</p>
      )}
    </>
  )
}

const TIMELINE_LABELS: Record<string, string> = {
  '15min': '15-Minuten-Prognose',
  '1h': 'Stündliche Prognose',
  '1day': 'Tägliche Prognose',
}

function OneCallView({ data, coords }: { data: Weather; coords: string }) {
  const timelines = data.timelines ?? {}
  const active = ['15min', '1h', '1day'].filter((key) => timelines[key]?.enabled)
  // Jedes aktive Modell fließt in den KI-Kontext (D-054) — kein Einzel-Select mehr.
  const aiModels = (data.ai_models?.length ? data.ai_models : active).map((key) => TIMELINE_LABELS[key] ?? key)
  const alerts = data.alerts ?? []

  return (
    <>
      <div className="info-strip">
        <Icon name="info" size={16} />
        <span>
          Quelle <b>One Call API 4.0</b> · Zone <code className="mono">{data.zone_entity}</code> ({coords}) · die KI
          nutzt: {aiModels.length ? aiModels.join(', ') : 'keine'} · Stand {tsDE(data.last_fetch_ts)}
          {data.daily_call_budget != null
            ? ` · Budget heute ${data.calls_today ?? 0}/${data.daily_call_budget}${data.budget_exhausted ? ' (erschöpft)' : ''}`
            : ''}
          {data.last_error ? ` · Fehler: ${data.last_error}` : ''}
        </span>
      </div>

      {active.length ? (
        active.map((key) => {
          const timeline = timelines[key]
          return (
            <div key={key}>
              <h3>{TIMELINE_LABELS[key] ?? key}</h3>
              <p className="muted">
                alle {timeline.refresh_min} min
                {timeline.pages && timeline.pages > 1 ? ` · ${timeline.pages} Seiten` : ''} · Stand{' '}
                {tsDE(timeline.last_fetch_ts)}
                {timeline.last_error ? ` · Fehler: ${timeline.last_error}` : ''}
              </p>
              {timeline.slots?.length ? (
                <SlotTable slots={timeline.slots} daily={key === '1day'} />
              ) : (
                <p className="muted">Noch keine Werte abgerufen.</p>
              )}
            </div>
          )
        })
      ) : (
        <p className="muted">Keine Timeline aktiviert. Die Schalter stehen in der Addon-Konfiguration unter „One Call API 4.0“.</p>
      )}

      {data.alerts_enabled && alerts.length ? (
        <>
          <h3>Unwetter-Warnungen</h3>
          <ul>
            {alerts.map((alert, index) => (
              <li key={`${alert.event}-${index}`}>
                <b>{alert.event ?? 'Warnung'}</b>
                {alert.sender_name ? <span className="muted"> ({alert.sender_name})</span> : null}
                <div className="muted">
                  {tsDE(alert.start)} – {tsDE(alert.end)}
                  {alert.tags?.length ? ` · ${alert.tags.join(', ')}` : ''}
                </div>
                {alert.description ? <div>{alert.description}</div> : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </>
  )
}

function SlotTable({ slots, daily }: { slots: WeatherSlot[]; daily: boolean }) {
  return (
    <DataTable
      head={
        <tr>
          <th>Zeit</th>
          <th className="num">Temperatur</th>
          <th className="num">Bewölkung</th>
          <th className="num">Regenwahrscheinlichkeit</th>
          {daily ? null : <th className="num">Wind</th>}
          <th>Wetter</th>
        </tr>
      }
    >
      {slots.map((slot, index) => (
        <tr key={`${slot.dt ?? slot.time ?? index}`}>
          <td>{slotTime(slot)}</td>
          <td className="num">
            {daily ? `${fmt(slot.temp_min)}–${fmt(slot.temp_max)} °` : `${fmt(slot.temp)} °`}
          </td>
          <td className="num">{fmtUnit(slot.clouds, '%')}</td>
          <td className="num">{slot.pop == null ? '–' : `${Math.round(slot.pop * 100)} %`}</td>
          {daily ? null : <td className="num">{fmt(slot.wind_speed)}</td>}
          <td>{slot.condition ?? '–'}</td>
        </tr>
      ))}
    </DataTable>
  )
}
