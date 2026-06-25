"""Entity Allowlist: zentrales Register der von EP freigegebenen HA-Entitäten.

EP liest nur explizit konfigurierte/freigegebene Entitäten (info.md §6.1/§13,
plan/01 + plan/08). Die freigegebenen IDs leiten sich vollständig aus den drei
Konfigurationsquellen ab (Messgrößen-Rollen, Geräte-`ems_*`-Felder, PV-
Prognosesensoren) — keine Doppelpflege.

Die Allowlist ist Defense-in-Depth + Transparenzregister: Zugriffe außerhalb des
Registers werden protokolliert und auditiert, aber **nicht blockiert**
(Soft-Durchsetzung, D-038). So stört eine Fehlkonfiguration der Allowlist nie den
lokalen Anlagenbetrieb (Leitprinzip „Fallback blockiert nie").
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterable

from energy_pilot.devices import Device, read_fields
from energy_pilot.entity_map import EntityMapping
from energy_pilot.forecast import PVOrientation
from energy_pilot.logging_setup import log

# Quell-Kennungen für die Nachvollziehbarkeit jeder freigegebenen Entität.
SOURCE_MEASUREMENT = "measurement"
SOURCE_DEVICE = "device"
SOURCE_FORECAST = "forecast"
SOURCE_WEATHER = "weather"


def collect_entity_ids(
    mapping: dict[str, EntityMapping] | None = None,
    orientations: Iterable[PVOrientation] | None = None,
    devices: Iterable[Device] | None = None,
) -> dict[str, str]:
    """Leitet die freigegebenen Entity-IDs aus den (teils gesetzten) Quellen ab.

    Liefert `entity_id -> source`. Geräte-IDs stammen aus dem zentralen Read-
    Schema (`read_fields`), damit es keine zweite Quelle der Wahrheit gibt.
    """
    entities: dict[str, str] = {}
    for entity_map in (mapping or {}).values():
        if entity_map.entity_id:
            entities.setdefault(entity_map.entity_id, SOURCE_MEASUREMENT)
    for device in devices or ():
        for field in read_fields(device):
            entities.setdefault(field.entity_id, SOURCE_DEVICE)
    for orientation in orientations or ():
        for entity_id in orientation.entities.values():
            if entity_id:
                entities.setdefault(entity_id, SOURCE_FORECAST)
    return entities


class EntityAllowlist:
    """Register freigegebener Entitäten mit weicher Durchsetzung (Soft-Guard)."""

    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._conn = conn
        self._logger = logger
        self._entities: dict[str, str] = {}
        # Bereits gemeldete Verstöße – drosselt Log-/Audit-Spam je Poll-Zyklus.
        self._reported_violations: set[str] = set()

    def register_all(self, entities: dict[str, str]) -> None:
        """Übernimmt ein abgeleitetes `entity_id -> source`-Mapping (idempotent)."""
        for entity_id, source in entities.items():
            if entity_id:
                self._entities.setdefault(entity_id, source)

    def is_allowed(self, entity_id: str) -> bool:
        """Reiner Check ohne Seiteneffekt."""
        return entity_id in self._entities

    def check(self, entity_id: str) -> bool:
        """Soft-Guard: protokolliert/auditiert Verstöße, blockiert aber nie.

        Gibt zurück, ob die Entität freigegeben ist. Der Aufrufer (HAClient)
        liest unabhängig vom Ergebnis weiter (Soft-Durchsetzung, D-038).
        """
        if entity_id in self._entities:
            return True
        if entity_id not in self._reported_violations:
            self._reported_violations.add(entity_id)
            if self._logger is not None:
                log(
                    self._logger,
                    "warning",
                    "Zugriff auf nicht freigegebene Entität (Allowlist)",
                    context={"entity": entity_id},
                )
            self._audit("allowlist_violation", entity_id, {"entity": entity_id})
        return False

    def persist(self, conn: sqlite3.Connection | None = None) -> None:
        """Schreibt das Register in die DB-Tabelle `allowlist` und auditiert es."""
        conn = conn or self._conn
        if conn is None:
            return
        conn.execute("DELETE FROM allowlist")
        conn.executemany(
            "INSERT INTO allowlist (entity_id, source, updated_at) "
            "VALUES (?, ?, datetime('now'))",
            list(self._entities.items()),
        )
        conn.commit()
        self._audit(
            "allowlist_rebuilt",
            None,
            {"count": len(self._entities), "by_source": self._by_source()},
        )

    def snapshot(self) -> dict:
        """Register für UI/API (read-only)."""
        return {
            "count": len(self._entities),
            "by_source": self._by_source(),
            "entries": [
                {"entity_id": entity_id, "source": source}
                for entity_id, source in sorted(self._entities.items())
            ],
        }

    def _by_source(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for source in self._entities.values():
            counts[source] = counts.get(source, 0) + 1
        return counts

    def _audit(self, action: str, subject: str | None, detail: dict) -> None:
        """Schreibt einen Audit-Eintrag; Fehler hier dürfen nie den Read stören."""
        if self._conn is None:
            return
        try:
            self._conn.execute(
                "INSERT INTO audit (actor, action, subject, detail_json) VALUES (?, ?, ?, ?)",
                ("allowlist", action, subject, json.dumps(detail, ensure_ascii=False)),
            )
            self._conn.commit()
        except sqlite3.Error:  # pragma: no cover - defensiv, Audit darf nie crashen
            pass
