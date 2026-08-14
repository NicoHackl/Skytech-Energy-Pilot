import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Icon } from './Icon'

/* Gemeinsame Bausteine für die Datenansichten: Ladehaken, Formatierer und die drei
   Zustände Laden/Leer/Gefüllt. Enthält bewusst keine Farben — alles über die Klassen
   aus styles.css (docs/design-system.md). */

/** Zahl in deutscher Schreibweise, `–` für fehlende Werte. */
export function fmt(value: number | null | undefined): string {
  if (value === null || value === undefined) return '–'
  return Number(value).toLocaleString('de-DE', { maximumFractionDigits: 1 })
}

/** Zahl mit Einheit; fehlender Wert bleibt `–` ohne Einheit. */
export function fmtUnit(value: number | null | undefined, unit?: string): string {
  if (value === null || value === undefined) return '–'
  return `${fmt(value)}${unit ? ` ${unit}` : ''}`
}

/** Unix-Sekunden als Datum und Uhrzeit in Berliner Zeit (AGENTS.md, eiserne Regel 15). */
export function tsDE(seconds: number | null | undefined): string {
  if (!seconds) return '–'
  return new Date(seconds * 1000).toLocaleString('de-DE', {
    timeZone: 'Europe/Berlin',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** ISO-Zeitstempel aus dem Backend als `TT.MM.JJJJ, hh:mm` in Berliner Zeit. */
export function isoDE(value: string | null | undefined): string {
  if (!value) return '–'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('de-DE', {
    timeZone: 'Europe/Berlin',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export const boolDe = (value: boolean | null | undefined): string =>
  value === null || value === undefined ? '–' : value ? 'Ja' : 'Nein'

/* Technische Token aus dem Backend als lesbare Anzeige. Der Rohwert bleibt für
   Vergleiche erhalten — übersetzt wird nur, was der Nutzer sieht. */
const SOURCE_LABELS: Record<string, string> = {
  live: 'Live',
  none: 'keine',
  fallback: 'Ersatzwert',
  hems: 'HEMS',
  measurement: 'Messwert',
  device: 'Gerät',
  forecast: 'Prognose',
  weather: 'Wetter',
}
export const srcDe = (value?: string): string => (value ? SOURCE_LABELS[value] ?? value : '–')

/** HEMS-Regelmodus (`input_select.ems_regelmodus`): auto = KI/EP, manuell = Nutzerwert, aus = aus. */
const MODE_LABELS: Record<string, string> = {
  aus: 'Aus',
  auto: 'Automatik',
  manuell: 'Manuell',
  nur_heizen: 'Nur Heizen',
  nur_laden: 'Nur Laden',
}
export const modeDe = (value?: string | null): string => (value ? MODE_LABELS[value] ?? value : '–')

/** Aufgelöste Steuerquelle je Gerät (D-057). */
const CONTROL_SOURCE_LABELS: Record<string, string> = {
  ep: 'KI (Energy Pilot)',
  user: 'Manuell (Nutzerwerte)',
  aus: 'Aus',
}
export const controlSrcDe = (value?: string): string =>
  value ? CONTROL_SOURCE_LABELS[value] ?? value : '–'

/** Anzeigename eines Plan-Vorschlagsfelds, inkl. dynamischer Zusatzfelder (D-047). */
const PLAN_FIELD_LABELS: Record<string, string> = {
  prio_vorschlag: 'Priorität',
  freigabe_vorschlag: 'Freigabe',
  geschutzte_mindestleistung_w_vorschlag: 'Geschützte Mindestleistung (W)',
  geschutzte_mindestleistung_a_vorschlag: 'Geschützte Mindestleistung (A)',
}
export function planFieldLabel(key: string): string {
  if (PLAN_FIELD_LABELS[key]) return PLAN_FIELD_LABELS[key]
  const match = /^extra_(.+)_vorschlag$/.exec(key)
  return match ? `Zusatz: ${match[1].replace(/_/g, ' ')}` : key
}

/** Technischer Gerätename („heizstab“) als Überschrift, wenn kein Label mitkommt. */
export function deviceHeading(name: string): string {
  return String(name || '').replace(/_/g, ' ').replace(/\b\p{L}/gu, (c) => c.toUpperCase())
}

/** Beliebiger Wert (Zahl/Bool/Text) für eine Tabellenzelle. */
export function anyValue(value: number | boolean | string | null | undefined, unit?: string): string {
  if (value === null || value === undefined) return '–'
  if (typeof value === 'boolean') return value ? 'Ja' : 'Nein'
  if (typeof value === 'number') return fmtUnit(value, unit)
  return `${value}${unit ? ` ${unit}` : ''}`
}

/* Lädt beim Montieren und pollt danach — aber nur, solange die Seite sichtbar ist.
   Ein Poller über alle Seiten hinweg würde HA dauerhaft belasten (docs/frontend.md).
   `null` heißt „noch nicht geladen“, nicht „leer“. */
const POLL_INTERVAL_MS = 10_000

export function usePoll<T>(loader: () => Promise<T>, poll = false) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  const reload = useCallback(async () => {
    try {
      setData(await loaderRef.current())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [])

  useEffect(() => {
    void reload()
    if (!poll) return undefined
    const id = window.setInterval(() => void reload(), POLL_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [reload, poll])

  return { data, error, reload, setData }
}

/** Ladezustand. */
export function Loading() {
  return (
    <div className="center">
      <div className="spinner" />
    </div>
  )
}

/** Leerzustand — braucht immer einen Weg zur ersten Aktion (docs/frontend.md). */
export function Empty({ icon = 'info', text, action }: { icon?: string; text: string; action?: ReactNode }) {
  return (
    <div className="empty">
      <Icon name={icon} size={40} />
      <p>{text}</p>
      {action}
    </div>
  )
}

/** Blockierende Fehlermeldung, die stehen bleibt. */
export function Alert({ children }: { children: ReactNode }) {
  return <div className="alert">{children}</div>
}

/** Zweispaltige Schlüssel-Wert-Liste für Status- und Metadatenblöcke. */
export function Kv({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="kv">
      {rows.map(([key, value]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Datentabelle; scrollt horizontal statt umzubrechen (docs/design-system.md). */
export function DataTable({ head, children }: { head: ReactNode; children: ReactNode }) {
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>{head}</thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}

/** Karte mit Titel und optionalen Aktionen in der Kopfzeile. */
export function Card({
  title,
  sub,
  actions,
  children,
}: {
  title: string
  sub?: ReactNode
  actions?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>{title}</h2>
          {sub ? <div className="sub">{sub}</div> : null}
        </div>
        {actions ? <div className="row-actions">{actions}</div> : null}
      </div>
      <div className="card-body">{children}</div>
    </section>
  )
}
