import { api } from '../api'
import { Alert, Card, DataTable, Empty, Loading, fmtUnit, srcDe, usePoll } from '../components/Data'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'

/* Messwerte der sieben festen Rollen. Leistungsgrößen tragen zusätzlich die
   1/15/60-min-Mittel (D-001/D-003); Letztwertgrößen (SOC, Temperatur) nicht. */
export function Daten() {
  const { data, error, reload } = usePoll(() => api.state(), true)
  const rows = data ? Object.values(data) : []

  return (
    <>
      <PageHeader
        title="Daten"
        subtitle="Aktuelle Messwerte mit gleitenden Mittelwerten"
        actions={
          <button type="button" className="btn btn-ghost" onClick={() => void reload()}>
            <Icon name="refresh" size={16} />
            Aktualisieren
          </button>
        }
      />
      <div className="content">
        <Card title="Messwerte">
          {error ? (
            <Alert>{error}</Alert>
          ) : !data ? (
            <Loading />
          ) : !rows.length ? (
            <Empty
              icon="chart"
              text="Keine Messgrößen zugeordnet. Die Zuordnung wird in der Addon-Konfiguration unter „Sensor-Zuordnung“ gepflegt."
            />
          ) : (
            <DataTable
              head={
                <tr>
                  <th>Größe</th>
                  <th className="num">Aktuell</th>
                  <th className="num">Ø 1 min</th>
                  <th className="num">Ø 15 min</th>
                  <th className="num">Ø 60 min</th>
                  <th>Quelle</th>
                </tr>
              }
            >
              {rows.map((row) => {
                const current = row.averaged ? row.latest ?? null : row.value
                return (
                  <tr key={row.label}>
                    <td className="cell-title">{row.label}</td>
                    <td className="num">{fmtUnit(current, row.unit)}</td>
                    <td className="num">{row.averaged ? fmtUnit(row.mean_1m, row.unit) : ''}</td>
                    <td className="num">{row.averaged ? fmtUnit(row.mean_15m, row.unit) : ''}</td>
                    <td className="num">{row.averaged ? fmtUnit(row.mean_60m, row.unit) : ''}</td>
                    <td>
                      <span className={`pill ${row.source === 'live' ? 'ok' : 'muted'}`}>{srcDe(row.source)}</span>
                    </td>
                  </tr>
                )
              })}
            </DataTable>
          )}
        </Card>
      </div>
    </>
  )
}
