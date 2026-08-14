# Teststrategie

## Befehle

```bash
pytest                       # alle Tests
pytest app/tests/test_planner.py   # gezielt eine Datei
ruff check app               # Linting und Formatprüfung
cd frontend && npm run build # Frontend: Typprüfung (tsc --noEmit) + Bündelung
```

Alle drei müssen vor jedem Commit fehlerfrei durchlaufen — siehe [git-workflow.md](git-workflow.md).

## Aufbau

`pytest-asyncio` läuft im **Auto-Modus** (`asyncio_mode = "auto"` in `pyproject.toml`) — asynchrone
Tests brauchen kein `@pytest.mark.asyncio`.

Ein Testfile je Quellmodul: zu `app/energy_pilot/<modul>.py` gehört `app/tests/test_<modul>.py`.
Ausnahmen sind die Web-Tests, die nach Themen geschnitten sind (`test_web.py`, `test_web_plan.py`,
`test_web_hems.py`), weil `web/server.py` alle Endpunkte bündelt.

| Art | Umfang | Beispiel |
|---|---|---|
| Unit | Eine reine Funktion, keine externen Zugriffe | `test_constraints.py`, `test_validator.py` |
| Integration | Zusammenspiel über die aiohttp-App | `test_web*.py` (`aiohttp_client`-Fixture) |
| Regression | Ein konkret aufgetretener Fehler | beim jeweiligen Modul |

## Pflicht-Testfälle

Für jede neue Funktion mindestens:

1. **Normalfall** — erwartete Eingabe, erwartetes Ergebnis
2. **Fehlerfall** — ungültige Eingabe, definierter Fehler statt Absturz
3. **Leerzustand** — leere Liste, `None`, fehlende Entität

Ein Bugfix ohne Regressionstest ist nicht abgeschlossen. Der Test muss **vor** dem Fix
nachweislich fehlschlagen.

## Grundregeln

- Tests laufen **ohne** Netzwerkzugriff, ohne echte Zugangsdaten, ohne laufendes Home Assistant
  und ohne erreichbares HEMS. HA-Client, HEMS-Client und KI-Provider werden gemockt.
- Die Datenbank läuft im Test als `:memory:` bzw. über `tmp_path` — kein Zustand bleibt zurück.
- Tests sind reihenfolgeunabhängig.
- Keine `sleep`-Aufrufe zur Synchronisierung.
- Ein Test prüft **eine** Aussage; der Name beschreibt sie
  (`test_validator_klemmt_schutzleistung_auf_max`).

## Coverage

Zielwert: **60 %** (`--cov-fail-under=60`, D-024), langfristig anzuheben. Coverage ist ein
Warnsignal, kein Ziel an sich — hohe Coverage ohne Zusicherungen im Test ist wertlos.

## Bekannte Lücke

Eine dedizierte Contract-Test-Suite gegen ein Mock-HEMS fehlt, obwohl D-015 sie verlangt. Was es
gibt, sind Unit-Tests gegen einen gemockten HTTP-Client. Details:
[bekannte-luecken.md](bekannte-luecken.md).
