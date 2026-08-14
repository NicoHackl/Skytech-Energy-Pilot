import { useState } from 'react'
import { api } from '../api'
import type { Device, DeviceExtra } from '../types'
import { DataTable, anyValue, srcDe } from './Data'
import { Icon } from './Icon'
import { useToast } from './Toast'

/* Zusatz-Entitäten je Gerät (D-047/D-048/D-049/D-052): beliebige HA-Entität lesen,
   optional einen KI-Vorschlag dafür erzeugen und diesen optional in die Original-Entität
   zurückschreiben. Der Rückschreibweg greift zusätzlich nur, wenn die HEMS-Modus-Achse
   für das Gerät die Quelle `ep` ergibt (D-057). */

const EMPTY = { entity: '', label: '', unit: '', suggest: false, original: false, hint: '' }

/** Typ und gelesene Grenzen/Optionen einer Zusatz-Entität als Klartext (D-048). */
function typeInfo(extra: DeviceExtra): string {
  const attrs = extra.attrs ?? {}
  if (extra.kind === 'number') {
    if (attrs.min != null || attrs.max != null) {
      const unit = attrs.unit_of_measurement ? ` ${attrs.unit_of_measurement}` : ''
      return `Zahl (${attrs.min ?? '?'}–${attrs.max ?? '?'}${unit})`
    }
    return 'Zahl'
  }
  if (extra.kind === 'bool') return 'Ja/Nein'
  if (extra.kind === 'datetime') {
    const parts: string[] = []
    if (attrs.has_date) parts.push('Datum')
    if (attrs.has_time) parts.push('Uhrzeit')
    return `Datum/Zeit${parts.length ? ` (${parts.join('+')})` : ''}`
  }
  if (extra.kind === 'select') {
    const options = Array.isArray(attrs.options) ? attrs.options : []
    return `Auswahl${options.length ? ` (${options.join(', ')})` : ''}`
  }
  if (extra.kind === 'text') return 'Text'
  return 'automatisch'
}

/** Effektiver „In Original schreiben“-Zustand inklusive Modus-Gate (D-052/D-057).
    Ohne diesen Hinweis wirkte der Haken aktiv und täte stumm nichts. */
function OriginalState({ extra, source }: { extra: DeviceExtra; source?: string }) {
  if (!extra.ai_suggestion) return <span className="muted">–</span>
  if (extra.should_write_original) {
    if (source && source !== 'ep') {
      return (
        <span className="pill warn">
          gesperrt: {source === 'aus' ? 'Modus aus' : 'Modus manuell'}
        </span>
      )
    }
    return <span className="pill ok">Ja</span>
  }
  if (extra.write_original) return <span className="pill muted">Ja (kein Helfer, wirkungslos)</span>
  return <span className="muted">Nein</span>
}

export function DeviceExtras({ device, onChanged }: { device: Device; onChanged: () => void }) {
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()
  const extras = device.extras ?? []
  const patch = (part: Partial<typeof EMPTY>) => setForm((current) => ({ ...current, ...part }))

  const startEdit = (extra: DeviceExtra) =>
    setForm({
      entity: extra.read_entity_id,
      label: extra.label ?? '',
      unit: extra.unit ?? '',
      suggest: Boolean(extra.ai_suggestion),
      original: Boolean(extra.write_original),
      hint: extra.ai_hint ?? '',
    })

  const remove = async (entity: string) => {
    if (!window.confirm(`Zusatz-Entität „${entity}“ wirklich entfernen?`)) return
    try {
      await api.deleteExtra({ device_name: device.name, read_entity_id: entity })
      toast('Zusatz-Entität entfernt.')
      onChanged()
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err), 'err')
    }
  }

  const save = async () => {
    const entity = form.entity.trim()
    if (!entity) {
      toast('Bitte eine Entität angeben.', 'err')
      return
    }
    setSaving(true)
    try {
      const result = await api.saveExtra({
        device_name: device.name,
        read_entity_id: entity,
        ai_suggestion: form.suggest,
        ai_hint: form.hint,
        label: form.label,
        unit: form.unit,
        write_original: form.suggest && form.original,
      })
      if (result.ok) {
        toast('Zusatz-Entität gespeichert.')
        setForm(EMPTY)
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
      <h3>Zusatz-Entitäten</h3>
      <p className="muted">
        Zusätzlich zu den <code className="mono">ems_*</code>-Werten des HEMS: beliebige HA-Entität
        lesen, optional mit KI-Vorschlag als <code className="mono">sensor.ep_&lt;entität&gt;_vorschlag</code>.
        Vorschläge sind advisorisch und gehen <b>nie</b> an das HEMS.
      </p>

      {extras.length ? (
        <DataTable
          head={
            <tr>
              <th>Entität (gelesen)</th>
              <th>Typ</th>
              <th>KI-Vorschlag</th>
              <th>Vorschlags-Sensor</th>
              <th>In Original schreiben</th>
              <th className="num">Wert</th>
              <th>Hinweis für die KI</th>
              <th />
            </tr>
          }
        >
          {extras.map((extra) => (
            <tr key={extra.read_entity_id}>
              <td>
                <span className="cell-title">
                  <code className="mono">{extra.read_entity_id}</code>
                </span>
                {extra.label ? <span className="cell-sub">{extra.label}</span> : null}
              </td>
              <td className="muted">{typeInfo(extra)}</td>
              <td>{extra.ai_suggestion ? 'Ja' : 'Nein'}</td>
              <td>
                {extra.ai_suggestion && extra.suggestion_entity_id ? (
                  <code className="mono">{extra.suggestion_entity_id}</code>
                ) : (
                  <span className="muted">–</span>
                )}
              </td>
              <td>
                <OriginalState extra={extra} source={device.control_source} />
              </td>
              <td className="num" title={srcDe(extra.source)}>
                {anyValue(extra.value, extra.unit)}
              </td>
              <td className="muted">{extra.ai_hint || '–'}</td>
              <td>
                <div className="row-actions">
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label={`${extra.read_entity_id} bearbeiten`}
                    onClick={() => startEdit(extra)}
                  >
                    <Icon name="edit" size={16} />
                  </button>
                  <button
                    type="button"
                    className="icon-btn danger-icon"
                    aria-label={`${extra.read_entity_id} löschen`}
                    onClick={() => void remove(extra.read_entity_id)}
                  >
                    <Icon name="trash" size={16} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </DataTable>
      ) : (
        <p className="muted">Noch keine Zusatz-Entitäten für dieses Gerät.</p>
      )}

      <div className="form-grid">
        <label className="field wide">
          <span>Entität</span>
          <input
            value={form.entity}
            placeholder="sensor.… · input_number.… · input_boolean.… · input_datetime.… · input_select.…"
            onChange={(event) => patch({ entity: event.target.value })}
          />
          <small>Der Typ folgt der Domäne: Zahl, Ja/Nein, Datum/Zeit, Text oder Auswahl.</small>
        </label>

        <label className="field">
          <span>Anzeigename</span>
          <input value={form.label} onChange={(event) => patch({ label: event.target.value })} />
        </label>

        <label className="field">
          <span>Einheit</span>
          <input
            value={form.unit}
            placeholder="z. B. % oder °C"
            onChange={(event) => patch({ unit: event.target.value })}
          />
        </label>

        <label className="switch wide">
          <input
            type="checkbox"
            checked={form.suggest}
            onChange={(event) =>
              patch({ suggest: event.target.checked, original: event.target.checked ? form.original : false })
            }
          />
          <span className="track" />
          <span className="switch-label">KI liefert einen Vorschlagswert</span>
        </label>

        <label className="switch wide">
          <input
            type="checkbox"
            disabled={!form.suggest}
            checked={form.original}
            onChange={(event) => patch({ original: event.target.checked })}
          />
          <span className="track" />
          <span className="switch-label">
            In Original schreiben
            <small>
              Nur zusammen mit dem KI-Vorschlag und nur bei echten Helfern — bei
              <code className="mono"> sensor.*</code> entsteht ausschließlich der Vorschlags-Sensor.
              Greift zusätzlich nur, wenn der Gerätemodus die Steuerquelle „KI“ ergibt.
            </small>
          </span>
        </label>

        <label className="field wide">
          <span>Hinweis für die KI</span>
          <textarea
            value={form.hint}
            placeholder="Was der Wert bedeutet und wie die KI ihn verwenden soll."
            onChange={(event) => patch({ hint: event.target.value })}
          />
        </label>

        <div className="wide inline-actions">
          <button type="button" className="btn btn-primary" disabled={saving} onClick={() => void save()}>
            {saving ? 'Speichern…' : 'Speichern'}
          </button>
          {form.entity ? (
            <button type="button" className="btn btn-ghost" onClick={() => setForm(EMPTY)}>
              Abbrechen
            </button>
          ) : null}
        </div>
      </div>
    </>
  )
}
