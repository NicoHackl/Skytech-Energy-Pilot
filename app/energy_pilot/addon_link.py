"""Name und HA-Konfigurationsseite des eigenen Add-ons für den Sidebar-Fuß (D-068).

Der Slug trägt das Präfix des Add-on-Repositorys (z. B.
`03f1563e_skytech_energy_pilot_dev`) und unterscheidet Dev- und Stable-Kanal. Er steht
nur beim Supervisor (`GET /addons/self/info`, braucht `hassio_api: true`). Ohne ihn gibt es
keinen Link – der Fuß zeigt dann nur den Namen.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import aiohttp

from energy_pilot.logging_setup import log

SUPERVISOR_SELF_INFO_URL = "http://supervisor/addons/self/info"

FALLBACK_NAME = "Skytech Energy Pilot"

_TIMEOUT_S = 10

# Supervisor-Slugs bestehen aus Kleinbuchstaben, Ziffern und Unterstrichen. Was anders
# aussieht, wird nicht zu einem Pfad im HA-Frontend zusammengesetzt.
_SLUG_PATTERN = re.compile(r"[a-z0-9_]+")


def fallback() -> dict[str, Any]:
    """Antwort ohne Supervisor: Name ohne Link."""
    return {"name": FALLBACK_NAME, "config_path": None}


def link_from_info(info: dict[str, Any]) -> dict[str, Any] | None:
    """Baut den Link aus `/addons/self/info`. `None` bei fehlendem oder ungültigem Slug."""
    slug = str(info.get("slug") or "")
    if not _SLUG_PATTERN.fullmatch(slug):
        return None
    return {
        "name": str(info.get("name") or FALLBACK_NAME),
        "config_path": f"/hassio/addon/{slug}/config",
    }


async def fetch(
    token: str | None,
    logger: logging.Logger | None = None,
    url: str = SUPERVISOR_SELF_INFO_URL,
) -> dict[str, Any] | None:
    """Liest Name und Slug beim Supervisor. `None`, wenn das nicht gelingt."""
    if not token:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=_TIMEOUT_S),
            ) as resp:
                status = resp.status
                body = await resp.json(content_type=None) if status < 400 else None
    except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
        _warn(logger, "Add-on-Slug nicht abrufbar, Sidebar-Fuß ohne Link", fehler=str(exc))
        return None
    data = body.get("data") if isinstance(body, dict) else None
    link = link_from_info(data) if isinstance(data, dict) else None
    if link is None:
        _warn(
            logger,
            "Supervisor liefert keinen gültigen Add-on-Slug, Sidebar-Fuß ohne Link",
            status=status,
        )
    return link


def _warn(logger: logging.Logger | None, message: str, **fields: Any) -> None:
    if logger is not None:
        log(logger, "warning", message, **fields)
