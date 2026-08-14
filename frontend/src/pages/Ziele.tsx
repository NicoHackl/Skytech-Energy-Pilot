import { useState } from 'react'
import { api } from '../api'
import { Alert, Card, DataTable, Empty, Loading, anyValue, fmtUnit, usePoll } from '../components/Data'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { useToast } from '../components/Toast'
import type { Constraint, Ziel } from '../types'

/* Zwei Dinge, die im Planungslauf zusammenkommen: die harten Grenzen (aus den
   ems_*-Werten abgeleitet, nie durch die KI änderbar) und die weichen Ziele des Users
   (D-055) — letztere ohne Gewicht, das leitet ein vorgelagerter Klassifizierungslauf ab. */

export function Ziele() {
  const constraints = usePoll(() => api.constraints(), true)
  const ziele = usePoll(() => api.ziele(), true)
  const devices = usePoll(() => api.devices(), false)

  return (
    <>
      <PageHeader
        title="Grenzen & Ziele"
        subtitle="Harte technische Grenzen und eigene Optimierungsziele"
        actions={
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => {
              void constraints.reload()
              void ziele.reload()
            }}
          >
            <Icon name="refresh" size={16} />
            Aktualisieren
          </button>
        }
      />
      <div className="content">
        <Card
          title="Harte Grenzen je Gerät"
          sub="Technische Limits aus den ems_*-Werten — read-only und nie durch die KI änderbar."
        >
          {constraints.error ? (
            <Alert>{constraints.error}</Alert>
          ) : !constraints.data ? (
            <Loading />
          ) : !constraints.data.devices.length ? (
            <Empty
              icon="target"
              text="Keine Geräte erkannt — ohne HEMS kennt EP keine Grenzen."
              action={
                <a className="btn btn-primary" href="#/hems">
                  Zum HEMS-Tab
                </a>
              }
            />
          ) : (
            constraints.data.devices.map((device) => <ConstraintView key={device.name} device={device} />)
          )}
        </Card>

        <Card title="Ziele">
          <ZieleEditor
            ziele={ziele.data?.ziele ?? null}
            error={ziele.error}
            deviceOptions={(devices.data?.devices ?? []).map((device) => ({
              name: device.name,
              label: device.label,
            }))}
            onChanged={() => void ziele.reload()}
          />
        </Card>
      </div>
    </>
  )
}

function ConstraintView({ device }: { device: Constraint }) {
  const unit = device.output_unit === 'ampere' ? 'A' : 'W'
  const rows: [string, string][] = [
    ['Technische Freigabe', device.freigabe === null ? '–' : device.freigabe ? 'Ja' : 'Nein'],
  ]
  if (device.class === 'binary') {
    rows.push(['Feste Leistung', fmtUnit(device.fixed_power, unit)])
  } else {
    rows.push(['Min. Leistung', fmtUnit(device.min_power, unit)])
    rows.push([device.is_battery ? 'Max. Ladeleistung' : 'Max. Leistung', fmtUnit(device.max_power, unit)])
  }
  for (const extra of device.extras ?? []) {
    const label = extra.extra.label?.trim() || extra.extra.read_entity_id
    rows.push([
      `Zusatz: ${label}${extra.extra.ai_suggestion ? ' (KI-Vorschlag)' : ''}`,
      anyValue(extra.value, extra.extra.unit),
    ])
  }
  if (device.forced_prio != null) rows.push(['Feste Priorität', String(device.forced_prio)])

  return (
    <div>
      <h3>
        {device.label} <span className="muted">({device.class === 'controllable' ? 'regelbar' : 'binär'})</span>
      </h3>
      <DataTable
        head={
          <tr>
            <th>Grenze</th>
            <th className="num">Wert</th>
          </tr>
        }
      >
        {rows.map(([label, value]) => (
          <tr key={label}>
            <td className="cell-title">{label}</td>
            <td className="num">{value}</td>
          </tr>
        ))}
      </DataTable>
      <p className="muted">
        Schreibbar:{' '}
        {device.suggestion_keys?.length
          ? device.suggestion_keys.map((key) => (
              <code className="mono" key={key}>
                {key}{' '}
              </code>
            ))
          : '–'}
      </p>
    </div>
  )
}

const EMPTY_ZIEL = { id: null as number | null, name: '', beschreibung: '', devices: [] as string[] }

function ZieleEditor({
  ziele,
  error,
  deviceOptions,
  onChanged,
}: {
  ziele: Ziel[] | null
  error: string | null
  deviceOptions: { name: string; label: string }[]
  onChanged: () => void
}) {
  const [form, setForm] = useState(EMPTY_ZIEL)
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()

  const toggleDevice = (name: string) =>
    setForm((current) => ({
      ...current,
      devices: current.devices.includes(name)
        ? current.devices.filter((item) => item !== name)
        : [...current.devices, name],
    }))

  const remove = async (ziel: Ziel) => {
    if (!window.confirm(`Ziel „${ziel.name}“ wirklich löschen?`)) return
    try {
      await api.deleteZiel(ziel.id)
      toast('Ziel gelöscht.')
      onChanged()
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err), 'err')
    }
  }

  const save = async () => {
    if (!form.name.trim()) {
      toast('Bitte einen Namen angeben.', 'err')
      return
    }
    setSaving(true)
    try {
      const result = await api.saveZiel({
        id: form.id,
        name: form.name,
        beschreibung: form.beschreibung,
        devices: form.devices,
      })
      if (result.ok) {
        toast('Ziel gespeichert.')
        setForm(EMPTY_ZIEL)
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
      <div className="info-strip">
        <Icon name="info" size={16} />
        <span>
          Eigene Ziele mit Name, Beschreibung und zugeordneten Geräten — <b>ohne</b> Gewicht. Die
          Gewichtung leitet ein vorgelagerter Klassifizierungslauf pro Planung selbst ab; der Prompt
          dafür steht im Plan-Tab.
        </span>
      </div>

      {error ? (
        <Alert>{error}</Alert>
      ) : !ziele ? (
        <Loading />
      ) : !ziele.length ? (
        <p className="muted">Noch keine Ziele angelegt. Unten das erste anlegen.</p>
      ) : (
        <DataTable
          head={
            <tr>
              <th>Name</th>
              <th>Beschreibung</th>
              <th>Geräte</th>
              <th />
            </tr>
          }
        >
          {ziele.map((ziel) => (
            <tr key={ziel.id}>
              <td className="cell-title">{ziel.name}</td>
              <td className="muted">{ziel.beschreibung || '–'}</td>
              <td>{ziel.devices?.length ? ziel.devices.join(', ') : <span className="muted">alle</span>}</td>
              <td>
                <div className="row-actions">
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label={`Ziel ${ziel.name} bearbeiten`}
                    onClick={() =>
                      setForm({
                        id: ziel.id,
                        name: ziel.name,
                        beschreibung: ziel.beschreibung ?? '',
                        devices: [...(ziel.devices ?? [])],
                      })
                    }
                  >
                    <Icon name="edit" size={16} />
                  </button>
                  <button
                    type="button"
                    className="icon-btn danger-icon"
                    aria-label={`Ziel ${ziel.name} löschen`}
                    onClick={() => void remove(ziel)}
                  >
                    <Icon name="trash" size={16} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </DataTable>
      )}

      <div className="form-grid">
        <label className="field wide">
          <span>
            Name <em>*</em>
          </span>
          <input
            value={form.name}
            placeholder="z. B. Warmwasserkomfort"
            onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
          />
        </label>

        <label className="field wide">
          <span>Beschreibung</span>
          <textarea
            value={form.beschreibung}
            placeholder="Erklärt der KI, worum es bei diesem Ziel geht."
            onChange={(event) => setForm((current) => ({ ...current, beschreibung: event.target.value }))}
          />
        </label>

        <div className="field wide">
          <span>Zugeordnete Geräte</span>
          <small>Leer lassen für geräteunabhängige, globale Ziele.</small>
          <div className="inline-actions">
            {deviceOptions.length ? (
              deviceOptions.map((device) => (
                <label key={device.name} className="switch-label">
                  <input
                    type="checkbox"
                    checked={form.devices.includes(device.name)}
                    onChange={() => toggleDevice(device.name)}
                  />
                  {device.label}
                </label>
              ))
            ) : (
              <span className="muted">Keine Geräte erkannt.</span>
            )}
          </div>
        </div>

        <div className="wide inline-actions">
          <button type="button" className="btn btn-primary" disabled={saving} onClick={() => void save()}>
            {saving ? 'Speichern…' : form.id ? 'Ziel aktualisieren' : 'Ziel anlegen'}
          </button>
          {form.id || form.name ? (
            <button type="button" className="btn btn-ghost" onClick={() => setForm(EMPTY_ZIEL)}>
              Abbrechen
            </button>
          ) : null}
        </div>
      </div>
    </>
  )
}
