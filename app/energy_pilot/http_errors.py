"""Gemeinsame HTTP-Fehlerbehandlung: den **Original-Grund** des Servers mitnehmen.

aiohttps `resp.raise_for_status()` verwirft den Antwort-Body und meldet nur Status + Reason
(z.B. „400, message='Bad Request'"). Die eigentliche Ursache liefern HA-Core, HEMS und die
KI-Provider aber erst im **Body** (`{"message": …}` bzw. `{"error": {"message": …}}`). Diese
Helfer lesen den Body aus und heben die echte Meldung in die Fehlermeldung – damit landet der
konkrete Grund in Log/UI statt eines nichtssagenden „HTTP 400".

eiserne Regel 7 bleibt gewahrt: mitgeführt wird nur der **Pfad** (ohne Query), nie die
volle URL –
so kann kein als Query-Parameter übergebener Schlüssel (z.B. OWM `appid`) in ein Log geraten.
"""

from __future__ import annotations

import json
from typing import Any

# Fehler-Bodies können lang sein (HTML-Fehlerseiten, Stacktraces) – auf das Wesentliche kürzen.
MAX_BODY_CHARS = 300


class HTTPStatusError(Exception):
    """Ein HTTP-Fehlerstatus (>= 400) inklusive der Original-Servermeldung.

    Trägt Status, Reason, die aus dem Body extrahierte `server_message` und den Anfrage-Pfad
    als strukturierte Felder – der Aufrufer kann sie gezielt loggen; `str()` liefert eine
    kompakte, sprechende Meldung mit dem echten Grund.
    """

    def __init__(
        self,
        *,
        service: str,
        status: int,
        reason: str = "",
        server_message: str = "",
        path: str | None = None,
    ) -> None:
        self.service = service
        self.status = status
        self.reason = reason
        self.server_message = server_message
        self.path = path
        head = f"{service}: HTTP {status}"
        if reason:
            head += f" {reason}"
        if path:
            head += f" ({path})"
        if server_message:
            head += f" – {server_message}"
        super().__init__(head)


def _truncate(text: str) -> str:
    text = text.strip()
    if len(text) <= MAX_BODY_CHARS:
        return text
    return text[:MAX_BODY_CHARS] + "…"


def message_from_json(data: Any) -> str | None:
    """Zieht die aussagekräftigste Meldung aus einem geparsten Fehler-Body.

    Deckt die verbreiteten Shapes ab: `{"message": …}` (HA/OWM), `{"error": "…"}` und
    `{"error": {"message": …}}` (Gemini/Google). Sonst None (→ Aufrufer nimmt den Rohtext).
    """
    if not isinstance(data, dict):
        return None
    msg = data.get("message")
    if isinstance(msg, str) and msg.strip():
        return msg.strip()
    err = data.get("error")
    if isinstance(err, str) and err.strip():
        return err.strip()
    if isinstance(err, dict):
        inner = err.get("message")
        if isinstance(inner, str) and inner.strip():
            return inner.strip()
    return None


async def read_error_body(resp: Any) -> str:
    """Liest den Fehler-Body defensiv und liefert die beste verfügbare Meldung (gekürzt).

    Bevorzugt eine strukturierte `message`/`error`, fällt sonst auf den Rohtext zurück. Kann
    der Body nicht gelesen/geparst werden, ergibt sich ein leerer String (nie ein Folgefehler).
    """
    try:
        text = await resp.text()
    except Exception:  # pragma: no cover - Body-Lesefehler darf die Fehlermeldung nie verschlucken
        return ""
    if not text or not text.strip():
        return ""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return _truncate(text)
    return _truncate(message_from_json(data) or text)


async def raise_for_status(resp: Any, *, service: str) -> None:
    """Wirft bei Status >= 400 einen `HTTPStatusError` mit der Original-Servermeldung.

    Ersatz für `resp.raise_for_status()` überall dort, wo der Body den echten Grund trägt.
    """
    if resp.status < 400:
        return
    server_message = await read_error_body(resp)
    reason = (getattr(resp, "reason", None) or "").strip()
    url = getattr(resp, "url", None)
    path = getattr(url, "path", None) if url is not None else None
    raise HTTPStatusError(
        service=service,
        status=resp.status,
        reason=reason,
        server_message=server_message,
        path=path,
    )
