import { api } from '../api'
import { Alert, Card, DataTable, Empty, Loading, usePoll } from '../components/Data'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'

/* Read-only-Anzeige der Sensor-Zuordnung (D-027). Gepflegt wird sie in der
   Addon-Konfiguration, nicht hier — eine zweite Pflegestelle würde auseinanderlaufen. */
export function Einstellungen() {
  const { data, error } = usePoll(() => api.entities(), false)
  const rows = Array.isArray(data) ? data : []

  return (
    <>
      <PageHeader title="Einstellungen" subtitle="Zuordnung der Messgrößen zu HA-Entitäten" />
      <div className="content">
        <div className="info-strip">
          <Icon name="info" size={16} />
          <span>
            Die Zuordnung wird in der <b>Addon-Konfiguration</b> gepflegt (Gruppe „Sensor-Zuordnung“,
            Felder <code className="mono">entity_…</code>). Hier steht nur der aktuell geladene Stand;
            Änderungen wirken erst nach einem Addon-Neustart.
          </span>
        </div>

        <Card title="Sensor-Zuordnung">
          {error ? (
            <Alert>{error}</Alert>
          ) : !data ? (
            <Loading />
          ) : !rows.length ? (
            <Empty icon="settings" text="Keine Messgrößen bekannt." />
          ) : (
            <DataTable
              head={
                <tr>
                  <th>Größe</th>
                  <th>HA-Entität</th>
                </tr>
              }
            >
              {rows.map((row) => (
                <tr key={row.label}>
                  <td className="cell-title">
                    {row.label}
                    {row.averaged ? null : <span className="cell-sub">Letztwert, wird nicht gemittelt</span>}
                  </td>
                  <td>
                    {row.entity_id ? <code className="mono">{row.entity_id}</code> : <span className="muted">–</span>}
                  </td>
                </tr>
              ))}
            </DataTable>
          )}
        </Card>
      </div>
    </>
  )
}
