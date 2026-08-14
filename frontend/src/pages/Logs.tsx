import { useState } from 'react'
import { api } from '../api'
import { Alert, Card, DataTable, Empty, Loading, isoDE, usePoll } from '../components/Data'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'

/* Ringpuffer-Ansicht des strukturierten Logs, neueste zuerst, plus JSONL-Export
   für die maschinelle Fehleranalyse (D-014). */

const LEVELS = ['ALLE', 'DEBUG', 'INFO', 'WARNING', 'ERROR'] as const
type Level = (typeof LEVELS)[number]

const levelPill: Record<string, string> = {
  DEBUG: 'muted',
  INFO: 'primary',
  WARNING: 'warn',
  ERROR: 'err',
  CRITICAL: 'err',
}

export function Logs() {
  const { data, error, reload } = usePoll(() => api.logs(200), false)
  const [level, setLevel] = useState<Level>('ALLE')

  const rows = Array.isArray(data) ? [...data].reverse() : []
  const shown = level === 'ALLE' ? rows : rows.filter((row) => row.level === level)

  return (
    <>
      <PageHeader
        title="Logs"
        subtitle="Die letzten 200 Einträge aus dem Ringpuffer"
        actions={
          <>
            <button type="button" className="btn btn-ghost" onClick={() => void reload()}>
              <Icon name="refresh" size={16} />
              Aktualisieren
            </button>
            <a className="btn btn-ghost" href={api.logsExportPath}>
              <Icon name="download" size={16} />
              Export (JSONL)
            </a>
          </>
        }
      />
      <div className="content">
        <Card
          title="Protokoll"
          actions={
            <label className="switch-label">
              <span className="muted">Level</span>
              <select value={level} onChange={(event) => setLevel(event.target.value as Level)}>
                {LEVELS.map((item) => (
                  <option key={item} value={item}>
                    {item === 'ALLE' ? 'alle' : item}
                  </option>
                ))}
              </select>
            </label>
          }
        >
          {error ? (
            <Alert>{error}</Alert>
          ) : !data ? (
            <Loading />
          ) : !shown.length ? (
            <Empty icon="list" text="Keine Einträge für dieses Level." />
          ) : (
            <DataTable
              head={
                <tr>
                  <th>Zeit</th>
                  <th>Level</th>
                  <th>Komponente</th>
                  <th>Nachricht</th>
                </tr>
              }
            >
              {shown.map((row, index) => (
                <tr key={`${row.ts}-${index}`}>
                  <td className="mono">{isoDE(row.ts)}</td>
                  <td>
                    <span className={`pill ${levelPill[row.level] ?? 'muted'}`}>{row.level}</span>
                  </td>
                  <td>{row.component}</td>
                  <td>{row.message}</td>
                </tr>
              ))}
            </DataTable>
          )}
        </Card>
      </div>
    </>
  )
}
