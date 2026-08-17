# Frontend — Architektur und Muster

> Das **Aussehen** (Tokens, Klassen, Zustände) steht in [design-system.md](design-system.md) und
> wird hier nicht wiederholt. Hier steht, wie der Code aufgebaut ist und was am
> Home-Assistant-Ingress anders läuft als in einer normalen Web-Anwendung.

## Stack — festgelegt

| Baustein | Wahl |
|---|---|
| Bibliothek | React 18 |
| Sprache | TypeScript, `strict: true` |
| Bündler | Vite |
| Routing | `react-router-dom` (**HashRouter**, siehe unten) |
| Styling | eine `src/styles.css` mit Design-Tokens |
| Zustand | React-Bordmittel (`useState`, Context) |
| Datenabruf | `fetch` in `src/api.ts` — der einzige Ort mit `fetch` |

**Nicht** verwendet und ohne ausdrückliche Entscheidung auch nicht einzuführen: Redux, Zustand,
MobX, React Query, SWR, Axios, Formik, React Hook Form, Tailwind, MUI, shadcn, Icon-Pakete.

## Verzeichnisstruktur

```text
frontend/
├── index.html              # Hülle: data-design="ha", Theme-Inline-Skript, #root
├── package.json
├── tsconfig.json
├── vite.config.ts
├── dist/                   # gebautes Bündel — wird mitcommittet (siehe „Auslieferung")
└── src/
    ├── main.tsx            # Einstieg: Router + ThemeProvider + ToastProvider
    ├── App.tsx             # ausschließlich die Routentabelle
    ├── styles.css          # das gesamte Design-System
    ├── api.ts              # typisierter API-Client
    ├── types.ts            # Datenverträge zum Backend
    ├── components/         # Layout, PageHeader, Theme, Toast, Icon, …
    └── pages/              # eine Datei je Route
```

`pages/` kennt `components/`, nie umgekehrt. Wächst eine Seite über ~150 Zeilen, wandert der
wiederverwendbare Teil nach `components/`.

## Besonderheiten unter Home-Assistant-Ingress

Die Oberfläche wird **nicht** unter einem festen Pfad ausgeliefert, sondern in einem iframe unter
einer dynamischen Ingress-URL der Form `/api/hassio_ingress/<zufälliges-token>/`. Das Token wechselt
je Sitzung. Daraus folgen vier Abweichungen von den sonst üblichen Mustern — jede ist begründet und
in [design-entscheidungen.md](design-entscheidungen.md) festgehalten:

| Thema | Übliches Muster | Hier | Warum |
|---|---|---|---|
| API-Pfade | `fetch('/api/state')` | `fetch('api/state')` — **ohne** führenden Slash | Ein führender Slash verlässt das Ingress-Präfix und landet auf der HA-Core-API |
| Routing | `BrowserRouter` | `HashRouter` | Der Basispfad ist zur Bauzeit unbekannt und wechselt je Sitzung; zusätzlich müsste der Server sonst jede Unterroute auf `index.html` abbilden |
| Asset-Pfade | `base: '/'` | `base: './'` in `vite.config.ts` | Erzeugt relative Verweise auf `assets/…` statt absoluter |
| Anmeldung | `AuthProvider` | keiner | Ingress authentifiziert bereits gegen Home Assistant; ein zweiter Login wäre Theater |

**Merksatz:** Kein Pfad im Frontend beginnt mit `/`. Das gilt für `fetch`, für Assets und für
Verweise in `index.html`.

## Einstieg und Provider

`main.tsx` verdrahtet nur, es enthält keine Logik. Reihenfolge verbindlich: Router außen, dann
Theme, dann Toast.

```tsx
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
```

## Hell und Dunkel

Pflicht (eiserne Regel 11). `components/Theme.tsx` liefert `ThemeProvider`, `useTheme()` und
`ThemeSwitch` — und **keine einzige Farbe**. Der Provider setzt `data-theme` am `<html>`, speichert
die Wahl in `localStorage` und folgt der Systemvorgabe nur so lange, wie der Nutzer nicht selbst
gewählt hat. Ein Inline-Skript in `index.html` setzt `data-theme` vor dem ersten Frame, sonst blitzt
die helle Oberfläche auf.

`ThemeSwitch` sitzt in `PageHeader`, nicht in der Sidebar — die fährt unter 820px aus dem Bild.

Wer im TSX auf `theme === 'dark'` verzweigt, um eine Farbe zu wählen, hat das System umgangen; die
Verzweigung gehört in `styles.css`.

## Navigation und Layout

`components/Layout.tsx` liefert:

1. `Layout` — Sidebar (Marke, Navigationsgruppen, Fußbereich mit Verbindungszustand) plus `<main>`
   mit `<Outlet />`. Unter 820px als Off-Canvas-Panel mit Backdrop.
2. `PageHeader` — die klebrige Kopfzeile jeder Seite: `title`, optional `subtitle`, der
   `ThemeSwitch` und optional `actions`.

Jede Seite rendert `<PageHeader …/>` gefolgt von `<div className="content">`. Keine Seite baut sich
eine eigene Kopfzeile.

## Seiten

Eine Route je fachlichem Bereich; die Namen entsprechen den Begriffen der Doku:

| Route | Seite | Inhalt |
|---|---|---|
| `/` | Status | Verbindung zu HA/HEMS, Version, Provider, Allowlist |
| `/daten` | Daten | Mess-Rollen mit 1/15/60-min-Mittelwerten |
| `/geraete` | Geräte | Geräteauswahl, `ems_*`-Werte, Zusatz-Entitäten (inkl. Rolle `ist`/`grenze`/`sollwert`, D-061), KI-Beschreibung, **Regeln für dieses Gerät** (D-060), **Wärmespeicher-Kennwerte** (D-066), Modus |
| `/prognose` | Prognose | PV-Prognose je Ausrichtung, Wetter, **Rückblick** (gemessene Tageswerte, D-065 — dieselbe Tabelle, die die KI sieht) |
| `/ziele` | Grenzen & Ziele | abgeleitete harte Grenzen, **hausweite Regeln** (D-060), user-definierte Ziele (D-055) |
| `/plan` | Plan | Planungslauf, Klassifizierung, Prompts, Ergebnis, Schreib-Ergebnis; zusätzlich Begründung je Gerät, Konfidenz-Teilnoten und Unsicherheiten (D-060/D-064) sowie Hinweise „unverändert übernommen“, „Determinismus aus“ und „nicht geschrieben“ (D-063/D-064) |
| `/hems` | HEMS | HEMS-Status, Plan-Konformität, Geräte-Sync |
| `/einstellungen` | Einstellungen | read-only Anzeige der Addon-Konfiguration |
| `/logs` | Logs | Ringpuffer, Filter, JSONL-Export |

## API-Client

Genau **ein** Modul ruft `fetch` auf. Jeder Endpunkt ist ein benannter Eintrag im `api`-Objekt,
kein roher Pfad in der Seite. Rückgabetypen kommen aus `types.ts` und spiegeln den Vertrag aus
[api-referenz.md](api-referenz.md).

Besonderheit des Backends: `/api/plan/run`, `/api/plan/publish` und `/api/plan` antworten **immer**
mit HTTP 200 und melden Fehler über `ok:false` im Rumpf (Begründung in
[api-referenz.md](api-referenz.md)). Der Client wertet deshalb bei diesen Aufrufen `ok` aus und
verlässt sich nicht auf den Statuscode.

## Seitenmuster

Ladezustand wird über `null` unterschieden, nicht über ein zweites `loading`-Flag — `null` heißt
„noch nicht geladen", `[]` heißt „leer". Drei Zustände, immer alle drei umgesetzt:

| Zustand | Darstellung |
|---|---|
| Laden | `<div className="center"><div className="spinner" /></div>` |
| Leer | `.empty` in einer Karte: Icon, ein erklärender Satz, Primäraktion |
| Gefüllt | `table.data` in `.table-wrap` bei gleichförmigen Daten, sonst Kartenliste |

Ein Leerzustand ohne Weg zur ersten Aktion ist eine Sackgasse und gilt als Fehler. Typischer Fall
hier: „Noch keine Geräte erkannt" führt auf den Knopf „Geräte von HEMS neu laden".

Seiten mit Live-Daten aktualisieren sich selbst, aber **nur die gerade sichtbare Seite** — ein
Poll-Intervall im Hintergrund über alle Seiten hinweg erzeugt sonst dauerhaft Last auf HA.

## Rückmeldung an den Nutzer

| Mittel | Wofür |
|---|---|
| Toast (`ok` / `err`) | Ergebnis einer Aktion, verschwindet nach ~4 s |
| `.alert` | Fehler, der die ganze Seite betrifft |
| `.field-error` | Fehler an genau einem Eingabefeld |
| `.hint-box` | Fehlende Voraussetzung plus Knopf, der sie herstellt |
| `.info-strip` | Erklärung zur Bedienung einer Liste |

## Auslieferung

Das Bündel wird **gebaut und mitcommittet** (`frontend/dist/`), das Addon-Image kopiert es nur.
Grund: der HA-Supervisor baut das Image auf der Zielhardware des Users — dort soll kein Node laufen
(armv7 wäre spürbar langsam, und der Build bräuchte npm-Zugriff aus dem Container). Das ist eine
bewusste Ausnahme von „keine generierten Artefakte im Repo"
([git-workflow.md](git-workflow.md), Begründung in [design-entscheidungen.md](design-entscheidungen.md)).

Daraus folgt eine Pflicht: **wer `frontend/src/` ändert, baut neu und committet `dist/` mit.**
Die CI baut gegen und schlägt an, wenn beides auseinanderläuft.

```bash
cd frontend
npm install          # einmalig
npm run dev          # Entwicklung, Proxy auf das laufende Backend (Port 8098)
npm run build        # tsc --noEmit && vite build  → dist/
```

Ausgeliefert wird von aiohttp: `GET /` liefert `dist/index.html`, `GET /assets/*` die Bündel.

## Was ein Agent vor dem ersten Commit prüft

1. `npm run build` läuft fehlerfrei — `any` ist keine Lösung, sondern eine verschobene Fehlermeldung.
2. Kein `fetch` außerhalb von `api.ts`, und **kein Pfad mit führendem Slash**.
3. Keine Literalfarbe und kein gestaltender Inline-Style im TSX.
4. Lade-, Leer- und Fehlerzustand jeder neuen Seite sind umgesetzt.
5. Jeder Button ohne sichtbaren Text hat ein `aria-label`.
6. Die Ansicht ist bei 375px Breite bedienbar.
7. Der Theme-Schalter ist erreichbar, und jede neue Seite wurde in **beiden** Modi angesehen.
8. `frontend/dist/` ist neu gebaut und mitcommittet.
