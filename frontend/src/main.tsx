import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import { App } from './App'
import { ThemeProvider } from './components/Theme'
import { ToastProvider } from './components/Toast'
import './styles.css'

/* Verdrahtung, keine Logik. Provider-Reihenfolge: Router außen, dann Theme, dann Toast.

   HashRouter statt BrowserRouter: unter dem HA-Ingress liegt die Oberfläche unter einem
   dynamischen Präfix (/api/hassio_ingress/<token>/), das zur Bauzeit unbekannt ist und je
   Sitzung wechselt. Der Hash hält den Pfad konstant — damit lösen auch die relativen
   API-Aufrufe auf jeder Seite gleich auf, und der Server braucht keine Catch-all-Route
   für Unterseiten (docs/frontend.md). */
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HashRouter>
      <ThemeProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </ThemeProvider>
    </HashRouter>
  </StrictMode>,
)
