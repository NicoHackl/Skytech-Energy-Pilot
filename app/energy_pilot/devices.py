"""Gerätemodell und -Discovery des Energy Pilot.

EP liest pro Gerät die vom User gepflegten technischen `ems_*`-Werte (Decision
D-029/D-031). Die konkreten Entity-IDs werden **ausschließlich** aus dem HEMS-Schema
(`/api/device_controls_schema`, D-036) erkannt – die Geräte werden vollständig vom
HEMS gezogen. Einen Geräte-Fallback in der Addon-Config gibt es nicht mehr (D-046):
ist das HEMS beim Start nicht erreichbar, kennt EP keine Geräte. Der Webserver
wiederholt die Discovery dann automatisch (begrenzt) und stellt einen manuellen
HEMS-Sync (Button im HEMS-Tab) bereit.

Das Read-Schema ist gegen den HEMS-Quellcode verifiziert
(SkytechHEMS app/main.py `_ctrl_items_controllable`/`_ctrl_items_binary`).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from energy_pilot.hems_client import HEMSClient
from energy_pilot.logging_setup import log

CONTROLLABLE = "controllable"
BINARY = "binary"

# Prefix steckt im stabilen Suffix `_technische_freigabe` (existiert in beiden Klassen).
_PREFIX_RE = re.compile(r"\.ems_(?P<prefix>.+)_technische_freigabe$")


# Datentyp je HA-Domäne (D-048): steuert Lesen, KI-Antwort-Schema und Vorschlags-Sensor.
# Nicht gelistete Domänen (v.a. `sensor`) => "auto": Zahl bei numerischem Zustand, sonst Text.
_DOMAIN_KIND: dict[str, str] = {
    "input_number": "number",
    "number": "number",
    "input_boolean": "bool",
    "switch": "bool",
    "binary_sensor": "bool",
    "light": "bool",
    "input_datetime": "datetime",
    "input_text": "text",
    "text": "text",
    "input_select": "select",
    "select": "select",
}

# Semantische Rolle eines Zusatzwerts (D-061): sagt der KI, ob sie einen **gemessenen** Wert oder
# eine vom User gesetzte Vorgabe vor sich hat. Ohne diese Unterscheidung liest ein Modell einen
# Sollwert wie „Max. Wassertemperatur 85 °C" als Ist-Temperatur und plant daran vorbei.
EXTRA_ROLE_IST = "ist"  # gemessener Wert (Sensor)
EXTRA_ROLE_GRENZE = "grenze"  # vom User gesetzte Ober-/Untergrenze
EXTRA_ROLE_SOLLWERT = "sollwert"  # Zielwert/Vorgabe, ggf. von der KI vorgeschlagen
EXTRA_ROLES: tuple[str, ...] = (EXTRA_ROLE_IST, EXTRA_ROLE_GRENZE, EXTRA_ROLE_SOLLWERT)

# Klartext je Rolle für den KI-Kontext (die KI liest die Bedeutung, nicht das Kürzel).
EXTRA_ROLE_TEXT: dict[str, str] = {
    EXTRA_ROLE_IST: "gemessener Ist-Wert",
    EXTRA_ROLE_GRENZE: "vom User gesetzte Grenze, kein Messwert",
    EXTRA_ROLE_SOLLWERT: "Sollwert/Vorgabe, kein Messwert",
}


def normalize_extra_role(value: object) -> str:
    """Bringt eine Rollenangabe auf einen gültigen Wert; unbekannt/leer => `ist`."""
    text = str(value or "").strip().lower()
    return text if text in EXTRA_ROLES else EXTRA_ROLE_IST


# Domänen echter HA-„Helfer" (D-052): einzige Domänen, in die EP per Service zurückschreiben
# darf ("In Original schreiben"). `switch`/`light`/`binary_sensor` sind Geräte-Entitäten, kein
# Helfer, und `sensor` ist grundsätzlich read-only – dort entsteht nur der `_vorschlag`-Sensor.
_WRITABLE_HELPER_DOMAINS: frozenset[str] = frozenset(
    {
        "input_number", "number",
        "input_boolean",
        "input_datetime",
        "input_text", "text",
        "input_select", "select",
    }
)


@dataclass(frozen=True)
class DeviceExtra:
    """Eine user-gepflegte Zusatz-Entität eines Geräts (D-047/D-048, generalisiert D-035).

    Zusätzlich zu den vom HEMS gezogenen `ems_*`-Werten kann der User im Geräte-Tab je
    Gerät weitere Entitäten **beliebiger Domäne** hinterlegen (sensor, input_number,
    input_boolean, input_datetime, input_text, …), die EP liest und (optional) für die KI zu
    einem Vorschlagswert werden lässt. Beispiel: `input_number.min_soc_auto` → EP liest den
    Wert; bei `ai_suggestion=True` erzeugt die KI zusätzlich `sensor.ep_min_soc_auto_vorschlag`.

    Der Datentyp (`kind`) folgt der Domäne (D-048): Zahl/Bool/Datum/Text; `sensor` u.a. sind
    "auto" (Zahl, wenn der Zustand numerisch ist, sonst Text). Je nach Domäne liest EP zusätzlich
    Attribute (input_number: `min`/`max` als Ober-/Untergrenze für die KI; input_datetime:
    `has_date`/`has_time` für das erwartete Format).

    `rolle` (D-061) sagt der KI, **was** der Wert ist: `ist` (gemessen), `grenze` (vom User
    gesetzte Ober-/Untergrenze) oder `sollwert` (Vorgabe/Zielwert). Ohne diese Angabe liest ein
    Modell einen Sollwert wie „Max. Wassertemperatur 85 °C" als Ist-Temperatur.

    Diese Vorschläge sind rein **advisorisch** (nur HA-Sensor, D-047): sie werden NICHT an
    das HEMS übergeben (das HEMS kennt sie nicht); der Freitext (`ai_hint`) erklärt der KI
    Bedeutung und Verwendung des Werts.

    `write_original` (D-052, „In Original schreiben"): nur bei `ai_suggestion=True` wählbar.
    Ist sie aktiv, schreibt EP den KI-Vorschlag zusätzlich zum `sensor.ep_*_vorschlag` per
    HA-Service in die Original-Entität zurück – aber **nur**, wenn diese ein echter,
    schreibbarer Helfer ist (`is_writable_helper`). Bei `sensor.*` (immer read-only) entsteht
    unabhängig von `write_original` nur der `_vorschlag`-Sensor (siehe `should_write_original`).
    """

    read_entity_id: str  # z.B. "input_number.min_soc_auto" (die von EP gelesene Quelle)
    ai_suggestion: bool = False  # KI liefert einen Vorschlagswert (als sensor.ep_*_vorschlag)
    ai_hint: str = ""  # Freitext für die KI: was der Wert bedeutet / wie zu verwenden
    label: str = ""  # Anzeigename (leer => aus der object_id abgeleitet)
    unit: str = ""  # optionale Einheit für Anzeige/HA-Sensor (z.B. "°C", "%")
    write_original: bool = False  # D-052: Vorschlag zusätzlich in die Original-Entität schreiben
    rolle: str = EXTRA_ROLE_IST  # D-061: ist | grenze | sollwert (Semantik für die KI)

    @property
    def domain(self) -> str:
        """HA-Domäne der Quell-Entität (Teil vor dem ersten Punkt), z.B. `input_number`."""
        return self.read_entity_id.split(".", 1)[0].strip()

    @property
    def kind(self) -> str:
        """Datentyp nach Domäne (D-048): number | bool | datetime | text | auto."""
        return _DOMAIN_KIND.get(self.domain, "auto")

    @property
    def capture_attrs(self) -> tuple[str, ...]:
        """Zusätzlich zu lesende HA-Attribute je Typ (Grenzen/Format/Auswahl, D-048/D-049)."""
        if self.kind == "number":
            return ("min", "max", "step", "unit_of_measurement")
        if self.kind == "datetime":
            return ("has_date", "has_time")
        if self.kind == "select":  # input_select/select: Auswahlpool (D-049)
            return ("options",)
        if self.kind == "auto":  # sensor u.ä.: Einheit/Klasse mitnehmen, wenn vorhanden
            return ("unit_of_measurement", "device_class")
        return ()

    @property
    def object_id(self) -> str:
        """Stabile Kennung: object_id der Quell-Entität ohne führendes `ep_`.

        `input_number.min_soc_auto` → `min_soc_auto`;
        `input_number.ep_heizstab_max_temperatur` → `heizstab_max_temperatur` (kein `ep_ep_`).
        """
        raw = self.read_entity_id.split(".", 1)[-1].strip()
        return raw[3:] if raw.startswith("ep_") else raw

    @property
    def read_key(self) -> str:
        """Feldschlüssel im DeviceCollector/Readings (kollisionsfrei zu den `ems_*`-Feldern)."""
        return f"extra_{self.object_id}"

    @property
    def plan_field(self) -> str:
        """Vorschlagsfeld im Plan-/Antwort-Schema (Muster `extra_<obj>_vorschlag`)."""
        return f"extra_{self.object_id}_vorschlag"

    @property
    def suggestion_entity_id(self) -> str:
        """Zielsensor des KI-Vorschlags (`sensor.ep_<obj>_vorschlag`, D-047-Namensschema)."""
        return f"sensor.ep_{self.object_id}_vorschlag"

    @property
    def display_label(self) -> str:
        """Anzeigename: user-gepflegt oder aus der object_id abgeleitet."""
        return self.label.strip() or self.object_id.replace("_", " ").title()

    @property
    def rolle_text(self) -> str:
        """Klartext der semantischen Rolle für den KI-Kontext (D-061)."""
        return EXTRA_ROLE_TEXT[normalize_extra_role(self.rolle)]

    @property
    def is_writable_helper(self) -> bool:
        """True, wenn die Quell-Domäne ein echter HA-Helfer ist (D-052), kein `sensor.*`."""
        return self.domain in _WRITABLE_HELPER_DOMAINS

    @property
    def should_write_original(self) -> bool:
        """Effektiver Original-Schreibweg (D-052): `write_original` + Vorschlag + Helfer.

        Schützt gegen inkonsistent gepflegte/persistierte Kombinationen (z.B. `write_original`
        ohne `ai_suggestion`, oder auf einer `sensor.*`-Quelle) – der tatsächliche Schreibweg
        richtet sich immer nach dieser Eigenschaft, nie nach dem rohen `write_original`-Flag.
        """
        return self.write_original and self.can_suggest and self.is_writable_helper

    @property
    def can_suggest(self) -> bool:
        """Grenzen sind immer read-only und dürfen nie zu KI-Ausgaben werden."""
        return self.ai_suggestion and normalize_extra_role(self.rolle) != EXTRA_ROLE_GRENZE


@dataclass(frozen=True)
class HEMSField:
    """Ein vom HEMS deklarierter, semantisch typisierter Gerätewert."""

    key: str
    label: str
    kind: str
    entity_id: str
    unit: str = ""
    role: str = "diagnostic"
    planning_relevant: bool = False


@dataclass(frozen=True)
class Device:
    """Ein vom HEMS geregeltes Gerät aus EP-Sicht."""

    name: str
    label: str
    entity_prefix: str
    device_class: str  # CONTROLLABLE | BINARY
    output_unit: str = "watt"  # "watt" | "ampere"
    control_policy: str = "unknown"
    allowed_modes: tuple[str, ...] = ()
    actual_power_entity: str = ""
    switch_entity: str = ""
    request_entity: str = ""
    hems_fields: tuple[HEMSField, ...] = ()
    # User-gepflegte Zusatz-Entitäten (D-047); nach der HEMS-Discovery aus der DB gemergt.
    extras: tuple[DeviceExtra, ...] = ()
    # User-gepflegte Freitext-Beschreibung dieses Geräts für die KI (D-051): erklärt der KI
    # Funktion/Besonderheiten des Geräts. Rein advisorisch (geht als Kontext-Feld `funktion`
    # in den Planungs-Prompt, nie an das HEMS); nach der Discovery aus der DB gemergt.
    ai_prompt: str = ""
    # User-gepflegte Freitext-Betriebsregeln dieses Geräts (D-060): was der User will, nicht
    # was das Gerät ist. Geht als eigener Kontext-Block `regeln` in den Planungs-Prompt; die
    # KI muss ihre Entscheidung je Gerät dagegen begründen (`angewandte_regeln`).
    ai_regeln: str = ""


@dataclass(frozen=True)
class ReadField:
    """Eine von EP gelesene Gerätegröße inkl. abgeleiteter HA-Entität."""

    key: str
    label: str
    kind: str  # "bool" | "number" | "datetime" | "text" | "auto" (Zusatz-Entitäten, D-048)
    entity_id: str
    unit: str = ""
    capture_attrs: tuple[str, ...] = ()  # zusätzlich zu lesende HA-Attribute (D-048)
    role: str = "diagnostic"
    planning_relevant: bool = False


def _unit_suffix(output_unit: str) -> str:
    return "a" if output_unit == "ampere" else "w"


def read_fields(device: Device) -> list[ReadField]:
    """Leitet die EP-relevanten Lese-Entitäten eines Geräts ab (Read-Schema D-029)."""
    if device.hems_fields:
        fields = [
            ReadField(
                field.key,
                field.label,
                field.kind,
                field.entity_id,
                field.unit,
                role=field.role,
                planning_relevant=field.planning_relevant,
            )
            for field in device.hems_fields
        ]
        fields.extend(_extra_read_fields(device))
        return fields

    p = device.entity_prefix
    u = _unit_suffix(device.output_unit)
    unit_label = "A" if device.output_unit == "ampere" else "W"
    freigabe = ReadField(
        "technische_freigabe",
        "Technische Freigabe",
        "bool",
        f"input_boolean.ems_{p}_technische_freigabe",
    )

    if device.device_class == BINARY:
        fields = [
            ReadField(
                "leistung_w", "Ist-Leistung", "number",
                f"input_number.ems_{p}_leistung_w", "W",
            ),
            freigabe,
        ]
    else:  # CONTROLLABLE (inkl. Batterie)
        fields = [
            freigabe,
            ReadField(
                "min_technisch", "Min. Leistung (technisch)", "number",
                f"input_number.ems_{p}_min_technisch_{u}", unit_label,
            ),
            ReadField(
                "max_technisch", "Max. Leistung (technisch)", "number",
                f"input_number.ems_{p}_max_technisch_{u}", unit_label,
            ),
        ]

    # User-gepflegte Zusatz-Entitäten (D-047, ersetzt den früheren Heizstab-Hardcode D-035).
    # Typ (`kind`) und mitgelesene Attribute folgen der Domäne der Quell-Entität (D-048).
    fields.extend(_extra_read_fields(device))
    return fields


def _extra_read_fields(device: Device) -> list[ReadField]:
    """Lesevertrag der user-gepflegten Zusatzwerte eines Geräts."""
    return [
        ReadField(
            extra.read_key,
            extra.display_label,
            extra.kind,
            extra.read_entity_id,
            extra.unit,
            capture_attrs=extra.capture_attrs,
            role=f"extra_{normalize_extra_role(extra.rolle)}",
            planning_relevant=True,
        )
        for extra in device.extras
    ]


def _default_label(name: str) -> str:
    return name.replace("_", " ").title()


def _fields_from_items(items: list[dict]) -> tuple[HEMSField, ...]:
    """Übernimmt stabile HEMS-Feldmetadaten ohne lokale Suffixheuristik."""
    fields: list[HEMSField] = []
    for item in items:
        entity_id = str(item.get("entity") or "").strip()
        key = str(item.get("key") or "").strip()
        if not entity_id or not key:
            continue
        fields.append(
            HEMSField(
                key=key,
                label=str(item.get("label") or key),
                kind=str(item.get("kind") or "auto"),
                entity_id=entity_id,
                unit=str(item.get("unit") or ""),
                role=str(item.get("role") or "diagnostic"),
                planning_relevant=bool(item.get("planning_relevant", False)),
            )
        )
    return tuple(fields)


def global_fields_from_hems_schema(schema: list[dict]) -> tuple[HEMSField, ...]:
    """Planungsrelevante globale HEMS-Userinputs aus demselben Discovery-Vertrag."""
    for group in schema:
        if (group.get("name") or group.get("label") or "").strip().lower() == "global":
            items = [item for item in group.get("items", []) if isinstance(item, dict)]
            return _fields_from_items(items)
    return ()


def discover_from_hems_schema(schema: list[dict]) -> list[Device]:
    """Baut die Geräteliste aus dem HEMS-Kontrollschema (D-036).

    Klasse und Einheit werden aus den vorhandenen `ems_*`-Items abgeleitet:
    `_min_technisch_*` => controllable, sonst `_leistung_w` => binary;
    `_*_a` => Ampere, sonst Watt.
    """
    devices: list[Device] = []
    for group in schema:
        label = (group.get("label") or "").strip()
        if label.lower() == "global":
            continue
        raw_items = [item for item in group.get("items", []) if isinstance(item, dict)]
        entities = [item.get("entity", "") for item in raw_items]

        prefix = next(
            (m.group("prefix") for e in entities if (m := _PREFIX_RE.search(e))),
            None,
        )
        prefix = (group.get("entity_prefix") or "").strip() or prefix
        if not prefix:
            continue

        # Geräteidentität (D-029): stabiler technischer `name` aus dem HEMS-Schema.
        # `label` ist nur Anzeigename und darf ohne Folgen umbenannt werden. Ältere
        # HEMS-Versionen liefern kein `name` – dann auf das Entitätspräfix zurückfallen.
        name = (group.get("name") or "").strip() or prefix

        has_min_technisch = any(re.search(r"_min_technisch_[wa]$", e) for e in entities)
        has_leistung = any(e.endswith("_leistung_w") for e in entities)
        explicit_class = (group.get("class") or "").strip()
        if explicit_class in (CONTROLLABLE, BINARY):
            device_class = explicit_class
        elif has_min_technisch:
            device_class = CONTROLLABLE
        elif has_leistung:
            device_class = BINARY
        else:
            continue

        is_ampere = any(re.search(r"_(?:min|max)_technisch_a$", e) for e in entities)
        explicit_unit = (group.get("output_unit") or "").strip()
        output_unit = explicit_unit if explicit_unit in ("ampere", "watt") else (
            "ampere" if is_ampere else "watt"
        )

        hems_fields = list(_fields_from_items(raw_items))
        request_entity = str(group.get("request_entity") or "").strip()
        actual_power_entity = str(group.get("actual_power_entity") or "").strip()
        switch_entity = str(group.get("switch_entity") or "").strip()
        if request_entity:
            hems_fields.append(
                HEMSField(
                    key="hems_anforderung",
                    label="HEMS-Anforderung",
                    kind="bool" if device_class == BINARY else "number",
                    entity_id=request_entity,
                    unit=(
                        "" if device_class == BINARY else (
                            "A" if output_unit == "ampere" else "W"
                        )
                    ),
                    role="hems_request",
                    planning_relevant=True,
                )
            )
        if actual_power_entity:
            hems_fields.append(
                HEMSField(
                    key="istleistung",
                    label="Tatsächliche Leistung",
                    kind="number",
                    entity_id=actual_power_entity,
                    unit="W",
                    role="actual_power",
                    planning_relevant=True,
                )
            )
        if switch_entity:
            hems_fields.append(
                HEMSField(
                    key="istzustand",
                    label="Tatsächlicher Zustand",
                    kind="bool",
                    entity_id=switch_entity,
                    role="actual_state",
                    planning_relevant=True,
                )
            )

        devices.append(
            Device(
                name=name,
                label=label or _default_label(name),
                entity_prefix=prefix,
                device_class=device_class,
                output_unit=output_unit,
                control_policy=str(group.get("control_policy") or "unknown"),
                allowed_modes=tuple(str(mode) for mode in group.get("allowed_modes", []) if mode),
                actual_power_entity=actual_power_entity,
                switch_entity=switch_entity,
                request_entity=request_entity,
                hems_fields=tuple(hems_fields),
            )
        )
    return devices


async def discover(
    hems_client: HEMSClient | None,
    logger: logging.Logger | None = None,
) -> tuple[list[Device], str]:
    """Erkennt die Geräte ausschließlich über das HEMS-Kontrollschema (D-036).

    Liefert die Geräteliste und die Quelle ("hems" | "none"). Ist das HEMS nicht
    erreichbar oder liefert es keine Geräte, ist die Liste leer (Quelle "none") –
    einen Addon-Config-Fallback gibt es nicht mehr (D-046); die Geräte werden
    vollständig vom HEMS gezogen. Der Aufrufer wiederholt die Discovery bei "none"
    (Auto-Retry) bzw. stößt sie manuell über den HEMS-Sync neu an.
    """
    devices, source, _global_fields = await discover_contract(hems_client, logger)
    return devices, source


async def discover_contract(
    hems_client: HEMSClient | None,
    logger: logging.Logger | None = None,
) -> tuple[list[Device], str, tuple[HEMSField, ...]]:
    """Discovery inklusive globaler Userinputs; der alte Zweier-Vertrag bleibt erhalten."""
    if hems_client is not None:
        try:
            schema = await hems_client.device_schema()
            devices = discover_from_hems_schema(schema)
            if devices:
                return devices, "hems", global_fields_from_hems_schema(schema)
        except Exception as exc:
            if logger:
                log(
                    logger,
                    "warning",
                    "HEMS-Geräteschema nicht abrufbar – keine Geräte erkannt",
                    context={"error": str(exc)},
                )
    return [], "none", ()
