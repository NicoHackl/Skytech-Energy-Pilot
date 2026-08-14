import { useState } from 'react'
import { api } from '../api'
import { Alert, Card, DataTable, Kv, Loading, boolDe, srcDe, tsDE, usePoll } from '../components/Data'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { useToast } from '../components/Toast'

/* Startseite: Systemzustand, Diagnose und das Register der freigegebenen Lese-Entitäten. */

const HEALTH_LABELS: Record<string, string> = {
  status: 'Status',
  version: 'Version',
  provider: 'KI-Anbieter',
  model: 'Modell',
  ha_configured: 'HA verbunden',
}

export function Status() {
  const health = usePoll(() => api.health(), false)
  const diag = usePoll(() => api.diagnostics(), true)
  const allow = usePoll(() => api.allowlist(), true)
  const { toast } = useToast()
  const [busy, setBusy] = useState(false)

  const runHaTest = async () => {
    setBusy(true)
    try {
      const result = await api.haTest()
      if (result.connected) toast('Home Assistant ist verbunden.')
      else toast(`Keine HA-Verbindung: ${result.reason ?? 'unbekannter Grund'}`, 'err')
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err), 'err')
    } finally {
      setBusy(false)
      void diag.reload()
    }
  }

  const healthRows: [string, string][] = health.data
    ? Object.entries(health.data).map(([key, value]) => [
        HEALTH_LABELS[key] ?? key,
        typeof value === 'boolean' ? boolDe(value) : String(value),
      ])
    : []

  const diagRows: [string, string][] = diag.data
    ? [
        ['HA verbunden', boolDe(diag.data.ha_configured)],
        ['Poller aktiv', boolDe(diag.data.poller_active)],
        ['Erfassungsintervall', diag.data.poll_interval_s ? `${diag.data.poll_interval_s} s` : '–'],
        ['Zugeordnete Größen', (diag.data.mapped_roles ?? []).join(', ') || '–'],
        ['Letzter Lauf', tsDE(diag.data.last_collect_ts)],
        ['Letzter Fehler', diag.data.last_error || '–'],
      ]
    : []

  return (
    <>
      <PageHeader
        title="Status"
        subtitle="Verbindungen, Diagnose und freigegebene Entitäten"
        actions={
          <button type="button" className="btn btn-ghost" disabled={busy} onClick={runHaTest}>
            <Icon name="refresh" size={16} />
            {busy ? 'Teste…' : 'HA-Verbindung testen'}
          </button>
        }
      />
      <div className="content">
        {health.error ? <Alert>{health.error}</Alert> : null}

        <Card title="Systemstatus">
          {health.data ? <Kv rows={healthRows} /> : health.error ? null : <Loading />}
        </Card>

        <Card title="Diagnose" sub="Zustand der Datenerfassung">
          {diag.data ? <Kv rows={diagRows} /> : diag.error ? <Alert>{diag.error}</Alert> : <Loading />}
        </Card>

        <Card
          title="Freigegebene Entitäten"
          sub="EP liest nur diese Entitäten. Zugriffe außerhalb der Liste werden protokolliert, aber nicht blockiert."
        >
          <AllowlistView data={allow.data} error={allow.error} />
        </Card>
      </div>
    </>
  )
}

function AllowlistView({
  data,
  error,
}: {
  data: { count: number; by_source?: Record<string, number>; entries?: { entity_id: string; source: string }[] } | null
  error: string | null
}) {
  if (error) return <Alert>{error}</Alert>
  if (!data) return <Loading />
  if (!data.count) {
    return (
      <p className="muted">
        Noch keine Entitäten freigegeben. Die Liste wird aus der Sensor-Zuordnung, den vom HEMS
        erkannten Geräten und der PV-Prognose abgeleitet — alle drei werden in der Addon-Konfiguration
        gepflegt.
      </p>
    )
  }
  const bySource = Object.entries(data.by_source ?? {})
    .map(([key, value]) => `${srcDe(key)}: ${value}`)
    .join(' · ')
  return (
    <>
      <div className="info-strip">
        <Icon name="info" size={16} />
        <span>
          {data.count} Entitäten{bySource ? ` (${bySource})` : ''}
        </span>
      </div>
      <DataTable
        head={
          <tr>
            <th>Entität</th>
            <th>Quelle</th>
          </tr>
        }
      >
        {(data.entries ?? []).map((entry) => (
          <tr key={entry.entity_id}>
            <td>
              <code className="mono">{entry.entity_id}</code>
            </td>
            <td>{srcDe(entry.source)}</td>
          </tr>
        ))}
      </DataTable>
    </>
  )
}
