import { useState, type ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { AddonFoot } from './AddonFoot'
import { Icon } from './Icon'
import { ThemeSwitch } from './Theme'

/* App-Gerüst: Sidebar + Hauptspalte. Das Layout ist Elternroute mit <Outlet />,
   damit Navigation und Kopfzeile beim Seitenwechsel nicht neu montiert werden. */

const navClass = ({ isActive }: { isActive: boolean }) => `nav-item${isActive ? ' active' : ''}`

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

        <AddonFoot />
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
