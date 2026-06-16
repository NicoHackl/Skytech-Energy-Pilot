"""Strukturiertes JSON-Logging mit Ringpuffer (UI) und maschinenlesbarem Export.

Erfüllt user-regeln.md §02: umfangreiches, UI-einsehbares Logging plus
maschinenlesbarer Export für die KI-gestützte Fehleranalyse. Secrets werden
grundsätzlich maskiert (Sicherheitsvorgabe info.md §13).
"""

from __future__ import annotations

import json
import logging
import sys
from collections import deque
from datetime import UTC, datetime
from typing import IO, Any

LOGGER_NAME = "energy_pilot"

# Schlüssel, deren Werte niemals im Klartext geloggt werden dürfen.
SECRET_KEYS = frozenset(
    {"api_key", "apikey", "token", "authorization", "password", "secret", "supervisor_token"}
)
REDACTED = "***redacted***"

# Zusätzliche strukturierte Felder, die ein Log-Eintrag tragen kann.
EXTRA_FIELDS = ("run_id", "plan_id", "provider", "model")


def _redact(value: Any) -> Any:
    """Maskiert geheime Werte rekursiv in Dicts und Listen."""
    if isinstance(value, dict):
        return {k: (REDACTED if k.lower() in SECRET_KEYS else _redact(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_redact(item) for item in value]
    return value


def record_to_dict(record: logging.LogRecord) -> dict[str, Any]:
    """Wandelt einen Log-Eintrag in ein strukturiertes Dict um."""
    data: dict[str, Any] = {
        "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
        "level": record.levelname,
        "component": record.name,
        "message": record.getMessage(),
    }
    context = getattr(record, "context", None)
    if context:
        data["context"] = _redact(context)
    for key in EXTRA_FIELDS:
        value = getattr(record, key, None)
        if value is not None:
            data[key] = value
    if record.exc_info:
        data["error"] = logging.Formatter().formatException(record.exc_info)
    return data


class JsonFormatter(logging.Formatter):
    """Formatiert Log-Einträge als einzeilige JSON-Objekte (JSONL)."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(record_to_dict(record), ensure_ascii=False)


class RingBufferHandler(logging.Handler):
    """Hält die letzten N Einträge als Dicts für die UI und den Export vor."""

    def __init__(self, capacity: int = 1000) -> None:
        super().__init__()
        self.buffer: deque[dict[str, Any]] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.buffer.append(record_to_dict(record))
        except Exception:  # pragma: no cover - defensives Handler-Verhalten
            self.handleError(record)

    def records(self, level: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        items = list(self.buffer)
        if level:
            items = [r for r in items if r["level"] == level.upper()]
        if limit:
            items = items[-limit:]
        return items

    def export_jsonl(self, level: str | None = None) -> str:
        """Maschinenlesbarer Export (eine JSON-Zeile je Eintrag)."""
        return "\n".join(json.dumps(r, ensure_ascii=False) for r in self.records(level=level))


def setup_logging(
    level: str = "INFO",
    capacity: int = 1000,
    stream: IO[str] | None = None,
) -> tuple[logging.Logger, RingBufferHandler]:
    """Initialisiert den Projekt-Logger mit Ringpuffer- und Stream-Handler."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.handlers.clear()

    ring = RingBufferHandler(capacity)
    ring.setLevel(level)
    logger.addHandler(ring)

    stream_handler = logging.StreamHandler(stream or sys.stdout)
    stream_handler.setFormatter(JsonFormatter())
    stream_handler.setLevel(level)
    logger.addHandler(stream_handler)

    logger.propagate = False
    return logger, ring


def log(
    logger: logging.Logger,
    level: str,
    message: str,
    *,
    context: dict | None = None,
    **fields: Any,
) -> None:
    """Bequeme Hilfsfunktion für strukturiertes Logging mit Kontextfeldern."""
    extra: dict[str, Any] = {"context": context}
    extra.update(fields)
    logger.log(getattr(logging, level.upper()), message, extra=extra)
