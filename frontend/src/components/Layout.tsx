import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { api } from '../api'
import { Icon } from './Icon'
import { ThemeSwitch } from './Theme'

/* App-Gerüst: Sidebar + Hauptspalte. Das Layout ist Elternroute mit <Outlet />,
   damit Navigation und Kopfzeile beim Seitenwechsel nicht neu montiert werden. */

const navClass = ({ isActive }: { isActive: boolean }) => `nav-item${isActive ? ' active' : ''}`

/** Verbindungszustand im Sidebar-Fuß. Scheitert der Abruf, verschwindet nur die
    Anzeige — nie die Navigation. */
function ConnectionState() {
  const [health, setHealth] = useState<{ version: string; ha_configured: boolean } | null>(null)

  useEffect(() => {
    let active = true
    api
      .health()
      .then((data) => {
        if (active) setHealth({ version: data.version, ha_configured: data.ha_configured })
      })
      .catch(() => {
        if (active) setHealth(null)
      })
    return () => {
      active = false
    }
  }, [])

  if (!health) {
    return (
      <div className="sidebar-foot">
        <span className="avatar">EP</span>
        <div className="who">
          <b>Energy Pilot</b>
          <span>Verbindung unbekannt</span>
        </div>
      </div>
    )
  }
  return (
    <div className="sidebar-foot">
      <span className="avatar">EP</span>
      <div className="who">
        <b>Version {health.version}</b>
        <span>{health.ha_configured ? 'mit Home Assistant verbunden' : 'ohne HA-Verbindung'}</span>
      </div>
      <span
        className={`pill ${health.ha_configured ? 'ok' : 'warn'}`}
        title={health.ha_configured ? 'HA-Verbindung steht' : 'Kein SUPERVISOR_TOKEN'}
      >
        {health.ha_configured ? 'HA' : 'HA?'}
      </span>
    </div>
  )
}

export function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const closeMobile = () => setMobileOpen(false)

  return (
    <div className="shell">
      {mobileOpen ? (
        <button className="sidebar-backdrop" aria-label="Navigation schließen" onClick={closeMobile} />
      ) : null}

      <aside className={`sidebar${mobileOpen ? ' open' : ''}`}>
        <div className="sidebar-brand">
          <span className="crest">EP</span>
          <div>
            <b>Skytech Energy Pilot</b>
            <span>Energieplanung</span>
          </div>
        </div>

        <nav className="nav" onClick={closeMobile}>
          <NavLink to="/" end className={navClass}>
            <Icon name="dashboard" />
            <span>Status</span>
          </NavLink>

          <div className="nav-label">Anlage</div>
          <NavLink to="/daten" className={navClass}>
            <Icon name="chart" />
            <span>Daten</span>
          </NavLink>
          <NavLink to="/geraete" className={navClass}>
            <Icon name="plug" />
            <span>Geräte</span>
          </NavLink>
          <NavLink to="/prognose" className={navClass}>
            <Icon name="sun" />
            <span>Prognose</span>
          </NavLink>

          <div className="nav-label">Planung</div>
          <NavLink to="/ziele" className={navClass}>
            <Icon name="target" />
            <span>Grenzen &amp; Ziele</span>
          </NavLink>
          <NavLink to="/plan" className={navClass}>
            <Icon name="bolt" />
            <span>Plan</span>
          </NavLink>
          <NavLink to="/hems" className={navClass}>
            <Icon name="link" />
            <span>HEMS</span>
          </NavLink>

          <div className="nav-label">System</div>
          <NavLink to="/einstellungen" className={navClass}>
            <Icon name="settings" />
            <span>Einstellungen</span>
          </NavLink>
          <NavLink to="/logs" className={navClass}>
            <Icon name="list" />
            <span>Logs</span>
          </NavLink>
        </nav>

        <ConnectionState />
      </aside>

      <main className="main">
        <button className="mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Navigation öffnen">
          <Icon name="menu" />
        </button>
        <Outlet />
      </main>
    </div>
  )
}

/** Klebrige Kopfzeile jeder Seite. Keine Seite baut sich eine eigene.
    Der Theme-Schalter sitzt hier und nicht in der Sidebar: die fährt unter 820px
    aus dem Bild, der Schalter muss aber auf jeder Seite erreichbar bleiben. */
export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string
  subtitle?: string
  actions?: ReactNode
}) {
  return (
    <div className="topbar">
      <div>
        <h1>{title}</h1>
        {subtitle ? <div className="sub">{subtitle}</div> : null}
      </div>
      <div className="spacer" />
      <ThemeSwitch />
      {actions}
    </div>
  )
}
