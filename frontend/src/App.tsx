import { Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Daten } from './pages/Daten'
import { Einstellungen } from './pages/Einstellungen'
import { Geraete } from './pages/Geraete'
import { Hems } from './pages/Hems'
import { Logs } from './pages/Logs'
import { Plan } from './pages/Plan'
import { Prognose } from './pages/Prognose'
import { Status } from './pages/Status'
import { Ziele } from './pages/Ziele'

/* Ausschließlich die Routentabelle. Eine Route je fachlichem Bereich; die Namen
   entsprechen den Begriffen der Doku (docs/frontend.md). */
export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Status />} />
        <Route path="/daten" element={<Daten />} />
        <Route path="/geraete" element={<Geraete />} />
        <Route path="/prognose" element={<Prognose />} />
        <Route path="/ziele" element={<Ziele />} />
        <Route path="/plan" element={<Plan />} />
        <Route path="/hems" element={<Hems />} />
        <Route path="/einstellungen" element={<Einstellungen />} />
        <Route path="/logs" element={<Logs />} />
        <Route
          path="*"
          element={
            <div className="content">
              <div className="empty">Seite nicht gefunden.</div>
            </div>
          }
        />
      </Route>
    </Routes>
  )
}
