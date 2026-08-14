# D-059: Oberfläche auf React + TypeScript + Vite, Bündel im Repo

- **Datum:** 14.08.2026
- **Status:** Aktiv
- **Betrifft:** `frontend/`, `app/energy_pilot/web/server.py`, `Dockerfile`, `.github/workflows/ci.yaml`

## Kontext

Die Ingress-Oberfläche war eine Preact-/htm-SPA ohne Build-Schritt (seit 0.0.39, davor
vanilla JS nach D-010). Sie funktionierte, hatte aber kein Typsystem, kein Design-System und
keinen Hell/Dunkel-Schalter — alles Punkte, die die eisernen Regeln 14, 16 und 17 in
[`../../AGENTS.md`](../../AGENTS.md) inzwischen verlangen.

Randbedingung, die alles andere prägt: die Oberfläche läuft im **HA-Ingress**, also in einem
iframe unter `/api/hassio_ingress/<token>/`. Das Präfix steht erst zur Laufzeit fest und
wechselt je Sitzung. Zweite Randbedingung: der HA-Supervisor baut das Addon-Image **auf der
Hardware des Users** — amd64, aarch64 oder armv7.

## Betrachtete Optionen

### Option A — bei Preact + htm bleiben

- Dafür: kein Build, kein Node, kleinstes Bündel, funktioniert heute.
- Dagegen: verstößt gegen die eiserne Regel 14; kein `strict`-Typsystem; das Design-System
  (Tokens, Klassenkatalog, Zustände) ließe sich nur von Hand nachbauen.

### Option B — React + TypeScript + Vite, Node-Build-Stage im Dockerfile

- Dafür: keine Build-Artefakte im Repo, sauberste Trennung.
- Dagegen: jede Addon-Installation und jedes Update baut das Frontend auf der Zielhardware
  neu — auf armv7 spürbar langsam — und braucht dafür npm-Zugriff aus dem Build-Container.

### Option C — React + TypeScript + Vite, gebautes Bündel im Repo

- Dafür: Installation bleibt so schnell wie bisher, kein Node im Image, funktioniert auf
  allen drei Architekturen gleich.
- Dagegen: bricht mit „keine generierten Artefakte im Repo"; ein vergessener Rebuild liefert
  eine alte Oberfläche über neuem Backend aus.

## Entscheidung

**Option C.** Der Stack folgt Regel 14; das Bündel liegt als `frontend/dist` im Repo, und die
CI baut bei jedem Lauf gegen und schlägt an, wenn `dist` nicht zum Quellstand passt. Damit ist
der einzige ernsthafte Nachteil von C — der vergessene Rebuild — maschinell abgefangen, während
der Nachteil von B (Build auf der Nutzerhardware) sich nicht abfangen ließe.

Vier Abweichungen von den Mustern aus [`../frontend.md`](../frontend.md) sind durch den Ingress
erzwungen, nicht durch Geschmack:

| Thema | Übliches Muster | Hier | Warum |
|---|---|---|---|
| API-Pfade | `fetch('/api/state')` | `fetch('api/state')` | Ein führender Slash verlässt das Ingress-Präfix und landet auf der HA-Core-API |
| Routing | `BrowserRouter` | `HashRouter` | Basispfad zur Bauzeit unbekannt; zusätzlich bräuchte der Server sonst eine Catch-all-Route |
| Asset-Basis | `base: '/'` | `base: './'` | Erzeugt relative Verweise auf `assets/…` |
| Anmeldung | `AuthProvider` | keiner | Ingress authentifiziert bereits gegen Home Assistant |

Die Navigation wurde bewusst von der Tab-Leiste auf die **Sidebar** des Design-Systems
umgestellt, obwohl das Ingress-Panel dadurch etwas Breite verliert: ein zweites
Navigationsmuster neben dem des Design-Systems hätte jede spätere Oberfläche des Projekts vor
dieselbe Frage erneut gestellt.

## Folgen

- **Positiv:** Typfehler fallen zur Bauzeit auf; Farben, Abstände und Zustände kommen aus
  einem Token-Satz; Hell und Dunkel sind vollständig ausgestaltet und umschaltbar; die
  Oberfläche ist ab 375 px bedienbar.
- **Negativ:** Das Repo enthält ein generiertes Bündel, jeder Frontend-Commit trägt den
  gebauten Stand mit. Das Bündel ist mit React deutlich größer als die vendored Preact-Variante
  (rund 225 kB, gzip rund 70 kB) — im lokalen Netz ohne Bedeutung.
- **Aufwand:** Alle neun Seiten wurden portiert; die Preact-SPA samt vendored Bibliotheken ist
  entfallen, die Web-Tests prüfen jetzt das Bündel statt der alten Assets.

## Rücknahmebedingung

Wenn die CI-Gegenprobe wiederholt anschlägt, weil Rebuilds vergessen werden, oder wenn eine
HA-Version das Ausliefern eines vorgebauten Bündels erschwert, wird auf die Node-Build-Stage
(Option B) umgestellt. Wenn sich die Sidebar im schmalen Ingress-Panel als hinderlich erweist,
wird die Navigation innerhalb desselben Design-Systems auf eine Tab-Leiste zurückgeführt — das
betrifft nur `components/Layout.tsx`, nicht die Seiten.
