import { useState } from 'react'
import { api } from '../api'
import {
  Alert,
  Card,
  DataTable,
  Empty,
  Kv,
  Loading,
  anyValue,
  boolDe,
  fmtUnit,
  isoDE,
  modeDe,
  planFieldLabel,
  tsDE,
  usePoll,
} from '../components/Data'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { useToast } from '../components/Toast'
import type { HemsFeedback, HemsStatus } from '../types'

/* Status-Rückkopplung (M3): EP liest den HEMS-Zustand und vergleicht die eigenen
   Vorschläge mit dem Ist. Die Aussage ist ausdrücklich **beobachtend** — sie bestätigt
   nichts und lenkt nichts. */

const OVERALL_LABELS: Record<string, { text: string; pill: string }> = {
  kein_plan: { text: 'Kein Plan', pill: 'muted' },
  unbekannt: { text: 'Unbekannt', pill: 'warn' },
  beobachtet_konform: { text: 'Beobachtet konform', pill: 'ok' },
  beobachtet_abweichend: { text: 'Beobachtet abweichend', pill: 'err' },
}

const FIELD_STATUS: Record<string, { text: string; pill: string }> = {
  match: { text: 'gleich', pill: 'ok' },
  abweichend: { text: 'abweichend', pill: 'err' },
  unbekannt: { text: 'unbekannt', pill: 'muted' },
}

export function Hems() {
  const { data, error, reload } = usePoll(() => api.hemsStatus(), true)
  const [busy, setBusy] = useState<string | null>(null)
  const { toast } = useToast()

  // „Aktualisieren“ erzwingt einen Live-Abruf; sonst zeigt der Knopf nur den gedrosselten
  // Zwischenstand des Collectors und die HEMS-Ist-Werte blieben unverändert.
  const refresh = async () => {
    setBusy('refresh')
    try {
      await api.hemsStatus(true)
      await reload()
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err), 'err')
    } finally {
      setBusy(null)
    }
  }

  const test = async () => {
    setBusy('test')
    try {
      const result = await api.hemsTest()
      const cycle = (result.result as { cycle_count?: number } | undefined)?.cycle_count
      if (result.connected) toast(`HEMS ist online (Zyklus ${cycle ?? '?'}).`)
      else toast((result.result as { reason?: string } | undefined)?.reason ?? result.reason ?? 'HEMS nicht erreichbar.', 'err')
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err), 'err')
    } finally {
      setBusy(null)
      void reload()
    }
  }

  const rediscover = async () => {
    setBusy('sync')
    try {
      const result = await api.hemsRediscover()
      if (result.source === 'hems') toast(`${result.device_count} Gerät(e) vom HEMS übernommen.`)
      else toast('HEMS nicht erreichbar oder keine Geräte vorhanden.', 'err')
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err), 'err')
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <PageHeader
        title="HEMS"
        subtitle="Verbindung, Regelzyklus und beobachtete Plan-Konformität"
        actions={
          <>
            <button type="button" className="btn btn-ghost" disabled={busy !== null} onClick={() => void rediscover()}>
              {busy === 'sync' ? 'Lade…' : 'Geräte von HEMS neu laden'}
            </button>
            <button type="button" className="btn btn-ghost" disabled={busy !== null} onClick={() => void test()}>
              Jetzt prüfen
            </button>
            <button type="button" className="btn btn-ghost" disabled={busy !== null} onClick={() => void refresh()}>
              <Icon name="refresh" size={16} />
              Aktualisieren
            </button>
          </>
        }
      />
      <div className="content">
        <div className="info-strip">
          <Icon name="info" size={16} />
          <span>
            EP liest <code className="mono">/api/status</code> und vergleicht die eigenen Vorschläge mit
            dem Ist-Zustand. Gespiegelt als <code className="mono">sensor.ep_plan_status</code> und{' '}
            <code className="mono">sensor.ep_hems_verbindung</code>. Die HEMS-Adresse steht in der
            Addon-Konfiguration unter <code className="mono">hems_base_url</code>.
          </span>
        </div>

        {error ? <Alert>{error}</Alert> : !data ? <Loading /> : <HemsBody data={data} />}
      </div>
    </>
  )
}

function HemsBody({ data }: { data: HemsStatus }) {
  if (!data.configured) {
    return (
      <Card title="Verbindung">
        <Empty
          icon="link"
          text="HEMS nicht konfiguriert. Ohne hems_base_url kennt EP keine Geräte — und ohne Geräte kann kein Plan entstehen."
        />
      </Card>
    )
  }

  const rows: [string, string][] = [
    ['Verbindung', data.online ? 'online' : 'offline'],
    ['Letzter Abruf', tsDE(data.last_fetch_ts)],
    ['Letzter Regelzyklus', isoDE(data.last_cycle_at)],
    ['Zyklen', data.cycle_count == null ? '–' : String(data.cycle_count)],
    ['Regelintervall', data.interval_s == null ? '–' : `${data.interval_s} s`],
    ['Pool', fmtUnit(data.pool_w, 'W')],
    ['Defizit', fmtUnit(data.current_deficit_w, 'W')],
    ['Globaler Modus', modeDe(data.global_mode)],
    ['HEMS-Fehler', data.error || data.last_error || '–'],
  ]

  return (
    <>
      <Card title="Verbindung & Regelzyklus">
        <Kv rows={rows} />
      </Card>

      <Card title="Plan-Rückkopplung" sub="Beobachtet — bestätigt nichts und lenkt nichts.">
        <FeedbackView feedback={data.feedback ?? null} />
      </Card>

      <Card title="HEMS-Gerätezustände">
        {data.devices?.length ? (
          <DataTable
            head={
              <tr>
                <th>Gerät</th>
                <th>Typ</th>
                <th className="num">Priorität</th>
                <th>Freigegeben</th>
                <th className="num">Ist</th>
              </tr>
            }
          >
            {data.devices.map((device) => (
              <tr key={device.id}>
                <td className="cell-title">{device.label || device.id}</td>
                <td>{device.type === 'binary' ? 'binär' : device.type === 'controllable' ? 'regelbar' : device.type ?? '–'}</td>
                <td className="num">{device.priority ?? '–'}</td>
                <td>{boolDe(device.eligible)}</td>
                <td className="num">
                  {device.type === 'binary' ? (device.actual_on ? 'an' : 'aus') : fmtUnit(device.actual_w, 'W')}
                </td>
              </tr>
            ))}
          </DataTable>
        ) : (
          <p className="muted">Keine Gerätezustände — HEMS offline oder ohne Geräte.</p>
        )}
      </Card>
    </>
  )
}

function FeedbackView({ feedback }: { feedback: HemsFeedback | null }) {
  if (!feedback) return <p className="muted">Keine Daten.</p>
  const overall = OVERALL_LABELS[feedback.overall] ?? { text: feedback.overall, pill: 'muted' }
  const meta = [
    feedback.plan_id ? `Plan ${feedback.plan_id}` : null,
    feedback.valid_until ? `gültig bis ${isoDE(feedback.valid_until)}` : null,
    feedback.reason ?? null,
  ].filter(Boolean)

  return (
    <>
      <p>
        <span className={`pill ${overall.pill}`}>{overall.text}</span>{' '}
        {meta.length ? <span className="muted">{meta.join(' · ')}</span> : null}
      </p>

      {feedback.devices?.length ? (
        feedback.devices.map((device) => (
          <div key={device.label}>
            <h3>
              {device.label} <span className="muted">({device.verdict})</span>
              {device.matched === false ? <span className="pill warn">nicht im HEMS gefunden</span> : null}
            </h3>
            {device.fields?.length ? (
              <DataTable
                head={
                  <tr>
                    <th>Feld</th>
                    <th className="num">Vorschlag</th>
                    <th className="num">HEMS-Ist</th>
                    <th>Vergleich</th>
                  </tr>
                }
              >
                {device.fields.map((field) => {
                  const status = FIELD_STATUS[field.status] ?? { text: field.status, pill: 'muted' }
                  return (
                    <tr key={field.feld}>
                      <td className="cell-title">{planFieldLabel(field.feld)}</td>
                      <td className="num">{anyValue(field.vorschlag)}</td>
                      <td className="num">{anyValue(field.ist)}</td>
                      <td>
                        <span className={`pill ${status.pill}`}>{status.text}</span>
                      </td>
                    </tr>
                  )
                })}
              </DataTable>
            ) : (
              <p className="muted">Keine vergleichbaren Felder.</p>
            )}
          </div>
        ))
      ) : (
        <p className="muted">Keine Geräte im Plan.</p>
      )}
    </>
  )
}
