import { useEffect, useState } from 'react'
import { api } from '../api'
import {
  Alert,
  Card,
  DataTable,
  Empty,
  Loading,
  anyValue,
  controlSrcDe,
  modeDe,
  srcDe,
  usePoll,
} from '../components/Data'
import { DeviceExtras } from '../components/DeviceExtras'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { useToast } from '../components/Toast'
import type { Device } from '../types'

/* Geräte kommen ausschließlich vom HEMS (D-046). Je Gerät: Modus-Achse, gelesene
   ems_*-Werte, Zusatz-Entitäten, die Freitext-Beschreibung für die KI (D-051) und die
   Freitext-Betriebsregeln (D-060). */

export function Geraete() {
  const { data, error, reload } = usePoll(() => api.devices(), true)
  const [selected, setSelected] = useState<string | null>(null)
  const devices = data?.devices ?? []

  // Auswahl über die Auto-Aktualisierung hinweg halten; sonst das erste Gerät.
  useEffect(() => {
    if (!devices.length) {
      setSelected(null)
      return
    }
    setSelected((current) => (current && devices.some((d) => d.name === current) ? current : devices[0].name))
  }, [data]) // eslint-disable-line react-hooks/exhaustive-deps

  const device = devices.find((item) => item.name === selected) ?? null
  const sourceLabel = data
    ? ({ hems: 'HEMS-Schema', none: 'keine (HEMS nicht verbunden)' } as Record<string, string>)[data.source] ??
      data.source
    : ''

  return (
    <>
      <PageHeader
        title="Geräte"
        subtitle={data ? `Quelle: ${sourceLabel}` : undefined}
        actions={
          <button type="button" className="btn btn-ghost" onClick={() => void reload()}>
            <Icon name="refresh" size={16} />
            Aktualisieren
          </button>
        }
      />
      <div className="content">
        {error ? <Alert>{error}</Alert> : null}

        {!data && !error ? (
          <Loading />
        ) : !devices.length ? (
          <Card title="Geräte">
            <Empty
              icon="plug"
              text="Noch keine Geräte erkannt. Geräte kommen ausschließlich vom HEMS — trage die hems_base_url in der Addon-Konfiguration ein, lege die Geräte im HEMS an und lade sie dann neu."
              action={
                <a className="btn btn-primary" href="#/hems">
                  Zum HEMS-Tab
                </a>
              }
            />
          </Card>
        ) : (
          <>
            <Card title="Auswahl">
              <label className="field">
                <span>Gerät</span>
                <select value={selected ?? ''} onChange={(event) => setSelected(event.target.value)}>
                  {devices.map((item) => (
                    <option key={item.name} value={item.name}>
                      {item.label} ({item.class === 'controllable' ? 'regelbar' : 'binär'})
                    </option>
                  ))}
                </select>
              </label>
            </Card>

            {device ? <DeviceCard key={device.name} device={device} onChanged={() => void reload()} /> : null}
          </>
        )}
      </div>
    </>
  )
}

function DeviceCard({ device, onChanged }: { device: Device; onChanged: () => void }) {
  return (
    <Card
      title={device.label}
      sub={device.class === 'controllable' ? 'regelbar' : 'binär'}
      actions={<DeviceModePill device={device} />}
    >
      <DeviceMode device={device} />

      <h3>Gelesene Werte</h3>
      <DataTable
        head={
          <tr>
            <th>Größe</th>
            <th className="num">Wert</th>
            <th>Entität</th>
            <th>Quelle</th>
          </tr>
        }
      >
        {device.fields.map((field) => (
          <tr key={field.entity_id}>
            <td className="cell-title">{field.label}</td>
            <td className="num">{anyValue(field.value, field.unit)}</td>
            <td>
              <code className="mono">{field.entity_id}</code>
            </td>
            <td>
              <span className={`pill ${field.source === 'live' ? 'ok' : 'muted'}`}>{srcDe(field.source)}</span>
            </td>
          </tr>
        ))}
      </DataTable>

      <DeviceExtras device={device} onChanged={onChanged} />
      <DevicePrompt device={device} onChanged={onChanged} />
      <DeviceRegeln device={device} onChanged={onChanged} />
      <DeviceSpeicher device={device} onChanged={onChanged} />
    </Card>
  )
}

/** Kurzanzeige der Steuerquelle in der Kartenkopfzeile. */
function DeviceModePill({ device }: { device: Device }) {
  const source = device.control_source
  return <span className={`pill ${source === 'ep' ? 'ok' : 'warn'}`}>{controlSrcDe(source)}</span>
}

/** Modus-Achse je Gerät (D-057): gepflegt im HEMS, EP liest nur. Erklärt sichtbar,
    warum „In Original schreiben“ gerade greift oder nicht. */
function DeviceMode({ device }: { device: Device }) {
  const writes = device.control_source === 'ep'
  return (
    <div className="info-strip">
      <Icon name={writes ? 'check' : 'info'} size={16} />
      <span>
        Modus <b>{modeDe(device.mode)}</b> (global: {modeDe(device.global_mode)}) → Steuerquelle{' '}
        <b>{controlSrcDe(device.control_source)}</b>.{' '}
        {writes
          ? 'KI-Vorschläge dürfen in Original-Entitäten geschrieben werden.'
          : 'KI-Vorschläge werden nicht in Original-Entitäten geschrieben — der Nutzerwert bleibt stehen.'}{' '}
        Gepflegt im HEMS unter <code className="mono">{device.mode_entity_id}</code>.
      </span>
    </div>
  )
}

/** Freitext-Beschreibung des Geräts für die KI (D-051), rein advisorisch. */
function DevicePrompt({ device, onChanged }: { device: Device; onChanged: () => void }) {
  const [text, setText] = useState(device.ai_prompt ?? '')
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()

  const save = async (clear: boolean) => {
    const value = clear ? '' : text
    if (clear) setText('')
    setSaving(true)
    try {
      const result = await api.saveDevicePrompt({ device_name: device.name, prompt: value })
      if (result.ok) {
        toast(result.is_custom ? 'Beschreibung gespeichert.' : 'Beschreibung geleert.')
        onChanged()
      } else {
        toast(result.reason ?? 'Speichern fehlgeschlagen.', 'err')
      }
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err), 'err')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <h3>KI-Beschreibung dieses Geräts</h3>
      <p className="muted">
        Optionaler Freitext, der der KI erklärt, was das Gerät tut und wie es zu behandeln ist
        (z. B. „versorgt die Fußbodenheizung, träge, läuft bevorzugt mittags“). Fließt als Feld
        <code className="mono"> funktion</code> in die Planung ein — advisorisch, <b>nicht</b> ans HEMS.
      </p>
      <label className="field">
        <span>Beschreibung</span>
        <textarea value={text} onChange={(event) => setText(event.target.value)} />
      </label>
      <div className="inline-actions">
        <button type="button" className="btn btn-primary" disabled={saving} onClick={() => void save(false)}>
          {saving ? 'Speichern…' : 'Speichern'}
        </button>
        <button type="button" className="btn btn-ghost" disabled={saving} onClick={() => void save(true)}>
          Leeren
        </button>
      </div>
    </>
  )
}


/** Freitext-Betriebsregeln des Geräts (D-060): die Vorgabe, gegen die die KI begründen muss. */
function DeviceRegeln({ device, onChanged }: { device: Device; onChanged: () => void }) {
  const [text, setText] = useState(device.ai_regeln ?? '')
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()

  const save = async (clear: boolean) => {
    const value = clear ? '' : text
    if (clear) setText('')
    setSaving(true)
    try {
      const result = await api.saveDeviceRegeln({ device_name: device.name, regeln: value })
      if (result.ok) {
        toast(result.is_custom ? 'Regeln gespeichert.' : 'Regeln geleert.')
        onChanged()
      } else {
        toast(result.reason ?? 'Speichern fehlgeschlagen.', 'err')
      }
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err), 'err')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <h3>Regeln für dieses Gerät</h3>
      <p className="muted">
        Was <b>du</b> willst — im Unterschied zur Beschreibung darüber, die sagt, was das Gerät
        <i> ist</i>. Formuliere die Bedingungen in eigenen Worten und nenne konkrete Werte, z. B.
        „Steht die Warmwassertemperatur über 70 °C oder werden die nächsten zwei Tage über 25 °C
        warm, bleibt der Heizstab gesperrt — die Solarthermie deckt das Warmwasser.“ Die KI muss
        ihre Entscheidung für dieses Gerät gegen diese Regeln begründen; die Begründung steht
        anschließend im Plan-Tab.
      </p>
      <label className="field">
        <span>Regeln</span>
        <textarea
          value={text}
          rows={5}
          placeholder="Eine Regel je Zeile, mit konkreten Schwellwerten."
          onChange={(event) => setText(event.target.value)}
        />
      </label>
      <div className="inline-actions">
        <button type="button" className="btn btn-primary" disabled={saving} onClick={() => void save(false)}>
          {saving ? 'Speichern…' : 'Speichern'}
        </button>
        <button type="button" className="btn btn-ghost" disabled={saving} onClick={() => void save(true)}>
          Leeren
        </button>
      </div>
    </>
  )
}


/** Wärmespeicher-Kennwerte (D-066): Anlagendaten und eine Anforderung, keine Regel.

    Erst mit Volumen und Komfortminimum kann EP den Speicherinhalt in kWh ausdrücken — und damit
    die Frage rechnen, die eine Schwelle nicht beantworten kann: reicht der Inhalt, bis wieder
    Wärme von außen kommt? */
function DeviceSpeicher({ device, onChanged }: { device: Device; onChanged: () => void }) {
  const gespeichert = device.speicher
  const [form, setForm] = useState({
    volumen: gespeichert?.volumen_liter?.toString() ?? '',
    komfort: gespeichert?.komfort_min_c?.toString() ?? '',
    ziel: gespeichert?.ziel_c?.toString() ?? '',
  })
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()

  const zahl = (text: string): number | null => {
    const wert = text.trim()
    if (!wert) return null
    const parsed = Number(wert.replace(',', '.'))
    return Number.isFinite(parsed) ? parsed : null
  }

  const save = async () => {
    setSaving(true)
    try {
      const result = await api.saveSpeicher({
        device_name: device.name,
        volumen_liter: zahl(form.volumen),
        komfort_min_c: zahl(form.komfort),
        ziel_c: zahl(form.ziel),
      })
      if (result.ok) {
        toast(
          result.rechenbar
            ? 'Kennwerte gespeichert — die Energiebilanz ist rechenbar.'
            : 'Kennwerte gespeichert. Für die kWh-Rechnung fehlen noch: ' +
                (result.fehlt ?? []).join(', '),
        )
        onChanged()
      } else {
        toast(result.reason ?? 'Speichern fehlgeschlagen.', 'err')
      }
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err), 'err')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <h3>Wärmespeicher</h3>
      <p className="muted">
        Nur für Geräte, die einen Speicher laden (z. B. Heizstab). Aus Volumen und Temperatur
        rechnet EP die Reserve über dem Komfortminimum in kWh und daraus, wie viele Tage sie
        trägt — die Zahlen, an denen die KI abwägt, statt an einer Schwelle. Die gemessene
        Temperatur kommt aus der Mess-Rolle „Warmwassertemperatur" in der Addon-Konfiguration.
        Leere Felder heißen „nicht gepflegt", nicht 0.
      </p>
      <div className="form-grid">
        <label className="field">
          <span>Volumen</span>
          <input
            value={form.volumen}
            inputMode="decimal"
            placeholder="z. B. 300"
            onChange={(event) => setForm({ ...form, volumen: event.target.value })}
          />
          <small>Liter</small>
        </label>
        <label className="field">
          <span>Komfortminimum</span>
          <input
            value={form.komfort}
            inputMode="decimal"
            placeholder="z. B. 45"
            onChange={(event) => setForm({ ...form, komfort: event.target.value })}
          />
          <small>°C — darf nie unterschritten werden</small>
        </label>
        <label className="field">
          <span>Zielwert</span>
          <input
            value={form.ziel}
            inputMode="decimal"
            placeholder="z. B. 60"
            onChange={(event) => setForm({ ...form, ziel: event.target.value })}
          />
          <small>°C — optional, worauf geladen wird</small>
        </label>
        <div className="wide inline-actions">
          <button type="button" className="btn btn-primary" disabled={saving} onClick={() => void save()}>
            {saving ? 'Speichern…' : 'Speichern'}
          </button>
        </div>
      </div>
    </>
  )
}
