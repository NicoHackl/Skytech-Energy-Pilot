"""Tests für den HA-Connector ohne echte Netzwerkverbindung (Fake-Session)."""

from datetime import UTC, datetime

import pytest

from energy_pilot.allowlist import SOURCE_MEASUREMENT, EntityAllowlist
from energy_pilot.database import init_db
from energy_pilot.ha_client import HAClient
from energy_pilot.http_errors import HTTPStatusError


class _FakeURL:
    def __init__(self, path):
        self.path = path


class _FakeResponse:
    def __init__(self, payload, status=200, text="", reason="OK", path="/core/api/"):
        self._payload = payload
        self.status = status
        self._text = text
        self.reason = reason
        self.url = _FakeURL(path)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return self._text


class _FakeSession:
    def __init__(self, payload, status=200, text=""):
        self._payload = payload
        self._status = status
        self._text = text
        self.urls = []
        self.params = []
        self.posts = []

    def get(self, url, headers=None, params=None):
        self.urls.append(url)
        self.params.append(params or {})
        return _FakeResponse(self._payload, self._status, self._text, path=url)

    def post(self, url, headers=None, json=None):
        self.urls.append(url)
        self.posts.append({"url": url, "json": json})
        return _FakeResponse(self._payload, self._status, self._text, path=url)


def test_headers_and_base_url_normalization():
    client = HAClient(token="abc", base_url="http://supervisor/core/api/")
    assert client.headers["Authorization"] == "Bearer abc"
    assert client.base_url == "http://supervisor/core/api"


@pytest.mark.asyncio
async def test_test_connection_calls_api_root():
    session = _FakeSession({"message": "API running."})
    client = HAClient(token="t", session=session)

    result = await client.test_connection()

    assert result["message"] == "API running."
    assert session.urls[0].endswith("/api/")


@pytest.mark.asyncio
async def test_error_status_surfaces_server_message():
    # 4XX mit JSON-Body: der Original-Grund landet in der Fehlermeldung (nicht nur „HTTP 400").
    session = _FakeSession({}, status=400, text='{"message": "Entity not found."}')
    client = HAClient(token="t", session=session)

    with pytest.raises(HTTPStatusError) as exc:
        await client.get_state("sensor.gibt_es_nicht")

    assert exc.value.status == 400
    assert exc.value.server_message == "Entity not found."
    msg = str(exc.value)
    assert "Home Assistant" in msg
    assert "HTTP 400" in msg
    assert "Entity not found." in msg


@pytest.mark.asyncio
async def test_get_state_builds_entity_url():
    session = _FakeSession({"state": "1234"})
    client = HAClient(token="t", session=session)

    result = await client.get_state("sensor.pv_leistung")

    assert result["state"] == "1234"
    assert session.urls[0].endswith("/states/sensor.pv_leistung")


@pytest.mark.asyncio
async def test_set_state_posts_state_and_attributes():
    session = _FakeSession({"entity_id": "sensor.ep_heizstab_prio_vorschlag", "state": "10"})
    client = HAClient(token="t", session=session)

    result = await client.set_state(
        "sensor.ep_heizstab_prio_vorschlag", "10", {"unit_of_measurement": "W"}
    )

    assert result["state"] == "10"
    assert session.posts[0]["url"].endswith("/states/sensor.ep_heizstab_prio_vorschlag")
    assert session.posts[0]["json"] == {"state": "10", "attributes": {"unit_of_measurement": "W"}}


@pytest.mark.asyncio
async def test_set_state_omits_attributes_when_none():
    session = _FakeSession({"state": "on"})
    client = HAClient(token="t", session=session)

    await client.set_state("sensor.ep_heizstab_freigabe_vorschlag", "on")

    assert session.posts[0]["json"] == {"state": "on"}


@pytest.mark.asyncio
async def test_call_service_posts_entity_id_and_data():
    session = _FakeSession({"context": {"id": "abc"}})
    client = HAClient(token="t", session=session)

    await client.call_service(
        "input_number", "set_value", "input_number.ep_heizstab_max_temperatur", {"value": 55.0}
    )

    assert session.posts[0]["url"].endswith("/services/input_number/set_value")
    assert session.posts[0]["json"] == {
        "entity_id": "input_number.ep_heizstab_max_temperatur", "value": 55.0
    }


@pytest.mark.asyncio
async def test_call_service_without_data_only_posts_entity_id():
    session = _FakeSession({})
    client = HAClient(token="t", session=session)

    await client.call_service("input_boolean", "turn_on", "input_boolean.eco_modus")

    assert session.posts[0]["json"] == {"entity_id": "input_boolean.eco_modus"}


@pytest.mark.asyncio
async def test_get_state_allowed_entity_passes_guard():
    allow = EntityAllowlist()
    allow.register_all({"sensor.pv_leistung": SOURCE_MEASUREMENT})
    session = _FakeSession({"state": "1"})
    client = HAClient(token="t", session=session, allowlist=allow)

    result = await client.get_state("sensor.pv_leistung")

    assert result["state"] == "1"


@pytest.mark.asyncio
async def test_get_state_soft_guard_does_not_block_unlisted_entity():
    # Nicht freigegebene Entität: Read läuft trotzdem (soft), Verstoß wird auditiert.
    conn = init_db(":memory:")
    allow = EntityAllowlist(conn)
    session = _FakeSession({"state": "1"})
    client = HAClient(token="t", session=session, allowlist=allow)

    result = await client.get_state("sensor.verboten")

    assert result["state"] == "1"
    violations = conn.execute(
        "SELECT COUNT(*) AS n FROM audit WHERE action = 'allowlist_violation'"
    ).fetchone()["n"]
    assert violations == 1
    conn.close()


# --- Verlaufsabruf für den Tages-Rückblick (D-065) --------------------------------------------

_HISTORY_START = datetime(2026, 8, 14, 0, 0, tzinfo=UTC)
_HISTORY_END = datetime(2026, 8, 15, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_get_history_flattens_the_per_entity_list():
    """HA antwortet mit einer Liste **pro** Entität; EP fragt genau eine ab."""
    rows = [{"state": "60.0", "last_changed": "2026-08-14T06:00:00+02:00"}]
    session = _FakeSession([rows])
    client = HAClient(token="t", session=session)

    result = await client.get_history("sensor.ww", _HISTORY_START, _HISTORY_END)

    assert result == rows
    assert session.urls[0].endswith(f"/history/period/{_HISTORY_START.isoformat()}")
    params = session.params[0]
    assert params["filter_entity_id"] == "sensor.ww"
    # Ohne diese beiden Parameter liefert ein Temperaturfühler fünfstellige Zeilenzahlen.
    assert params["minimal_response"] == "true"
    assert params["significant_changes_only"] == "true"
    assert params["end_time"] == _HISTORY_END.isoformat()


@pytest.mark.asyncio
async def test_get_history_without_end_time_omits_the_parameter():
    session = _FakeSession([[]])
    client = HAClient(token="t", session=session)

    await client.get_history("sensor.ww", _HISTORY_START)

    assert "end_time" not in session.params[0]


@pytest.mark.asyncio
async def test_get_history_tolerates_empty_and_unexpected_payloads():
    """Ohne Aufzeichnung antwortet HA mit `[]` — das darf keinen Fehler auslösen."""
    for payload in ([], {}, [None], "kaputt"):
        client = HAClient(token="t", session=_FakeSession(payload))
        assert await client.get_history("sensor.ww", _HISTORY_START) == []


@pytest.mark.asyncio
async def test_get_history_runs_through_the_allowlist_guard():
    """Wie `get_state`: nicht freigegebene Entitäten werden protokolliert, nicht blockiert."""
    db = init_db(":memory:")
    allowlist = EntityAllowlist(db)
    allowlist.register_all({"sensor.erlaubt": SOURCE_MEASUREMENT})
    session = _FakeSession([[]])
    client = HAClient(token="t", session=session, allowlist=allowlist)

    await client.get_history("sensor.fremd", _HISTORY_START)

    assert session.urls  # der Read läuft trotzdem (Soft-Durchsetzung, D-038)
    verstoesse = db.execute(
        "SELECT COUNT(*) AS n FROM audit WHERE action LIKE '%allowlist%'"
    ).fetchone()["n"]
    assert verstoesse >= 1
