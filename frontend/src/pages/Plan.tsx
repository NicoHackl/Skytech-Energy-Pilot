import { useCallback, useState } from 'react'
import { api } from '../api'
import {
  Alert,
  Card,
  DataTable,
  Empty,
  Kv,
  Loading,
  anyValue,
  deviceHeading,
  isoDE,
  planFieldLabel,
  usePoll,
} from '../components/Data'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { PromptEditor } from '../components/PromptEditor'
import { useToast } from '../components/Toast'
import type { ClassificationResponse, Plan, PlanDevice, PlanResponse, PublishResult } from '../types'

/** Felder, die je Gerät die Entscheidung erklären (D-060) – keine Vorschlagswerte. */
const EXPLANATION_KEYS = new Set(['name', 'begruendung', 'angewandte_regeln'])

/** Klartext der Konfidenz-Teilnoten (D-064). */
const CONFIDENCE_LABEL: Record<string, string> = {
  datenlage: 'Datenlage',
  prognosesicherheit: 'Prognosesicherheit',
  regelklarheit: 'Regelklarheit',
  zielkonflikt: 'Zielkonflikt',
}

/* Der einzige Weg, auf dem ein Plan entsteht: der Knopf hier (es gibt keinen
   Scheduler, siehe docs/bekannte-luecken.md). Der Plan ist ein Vorschlag — validiert
   gegen die harten Grenzen und als sensor.ep_*_vorschlag nach HA geschrieben, aber
   nicht an das HEMS übergeben. */

const CLASSIFICATION_ERRORS: Record<string, string> = {
  keine_ziele_konfiguriert: 'Noch keine Ziele definiert — anzulegen unter „Grenzen & Ziele“.',
  provider_not_configured: 'Kein KI-Anbieter konfiguriert (API-Schlüssel fehlt).',
}

export function Plan() {
  const { data, error, reload, setData } = usePoll(() => api.plan(), false)
  const [busy, setBusy] = useState<string | null>(null)
  const [classification, setClassification] = useState<ClassificationResponse | null>(null)
  const { toast } = useToast()

  const loadPrompt = useCallback(() => api.prompt(), [])
  const savePrompt = useCallback((text: string) => api.savePrompt(text), [])
  const loadClassPrompt = useCallback(() => api.classificationPrompt(), [])
  const saveClassPrompt = useCallback((text: string) => api.saveClassificationPrompt(text), [])

  const runPlan = async () => {
    setBusy('plan')
    try {
      const result = await api.runPlan()
      setData(result)
      if (result.ok) {
        toast('Plan erzeugt.')
      } else {
        const errors = result.validation?.errors ?? (result.error ? [result.error] : [])
        toast(errors.join('; ') || 'Planungslauf fehlgeschlagen.', 'err')
      }
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err), 'err')
    } finally {
      setBusy(null)
    }
  }

  const runClassification = async () => {
    setBusy('classification')
    try {
      const result = await api.runClassification()
      setClassification(result)
      if (result.ok) toast('Klassifizierung erzeugt.')
      else toast(classificationError(result), 'err')
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err), 'err')
    } finally {
      setBusy(null)
    }
  }

  const publish = async () => {
    setBusy('publish')
    try {
      const result = await api.publishPlan()
      toast(publishMessage(result), result.ok ? 'ok' : 'err')
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err), 'err')
    } finally {
      setBusy(null)
    }
  }

  const testAi = async () => {
    setBusy('ai')
    try {
      const result = await api.aiTest()
      if (result.connected) toast('KI-Anbieter ist erreichbar.')
      else toast(result.reason ?? 'KI-Anbieter nicht erreichbar.', 'err')
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err), 'err')
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <PageHeader
        title="Plan"
        subtitle="KI-Vorschlag erzeugen, prüfen und nach Home Assistant schreiben"
        actions={
          <>
            <button type="button" className="btn btn-ghost" disabled={busy !== null} onClick={() => void testAi()}>
              KI-Verbindung testen
            </button>
            <button type="button" className="btn btn-ghost" disabled={busy !== null} onClick={() => void publish()}>
              Erneut nach HA schreiben
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              disabled={busy !== null}
              onClick={() => void runClassification()}
            >
              {busy === 'classification' ? 'Klassifiziere…' : 'Klassifizierung erzeugen'}
            </button>
            <button type="button" className="btn btn-primary" disabled={busy !== null} onClick={() => void runPlan()}>
              <Icon name="play" size={16} />
              {busy === 'plan' ? 'Plane…' : 'Plan erzeugen'}
            </button>
          </>
        }
      />
      <div className="content">
        <div className="info-strip">
          <Icon name="info" size={16} />
          <span>
            Die KI erzeugt einen <b>Vorschlagsplan</b>. Er wird lokal gegen die harten Grenzen validiert
            und bei Gültigkeit als <code className="mono">sensor.ep_*_vorschlag</code> nach Home Assistant
            geschrieben — <b>nicht</b> an das HEMS übergeben.
          </span>
        </div>

        <Card title="Instruktionen">
          <PromptEditor
            title="Planungs-Prompt bearbeiten"
            hint="Die Instruktion für den eigentlichen Planungsaufruf. Der Datenblock wird automatisch angehängt; Antwortformat und harte Grenzen bleiben unabhängig davon erzwungen."
            load={loadPrompt}
            save={savePrompt}
          />
          <PromptEditor
            title="Klassifizierungs-Prompt bearbeiten"
            hint="Die Instruktion für den vorgelagerten Aufruf, der aus den Zielen pro Planungslauf eine Gewichtung ableitet. Bekommt dieselben Daten wie die Planung, zusätzlich die Zieldefinitionen."
            load={loadClassPrompt}
            save={saveClassPrompt}
          />
        </Card>

        {classification ? (
          <Card title="Klassifizierungs-Ergebnis">
            <ClassificationView data={classification} />
          </Card>
        ) : null}

        <Card title="Letzter Plan" actions={
          <button type="button" className="btn btn-ghost" onClick={() => void reload()}>
            <Icon name="refresh" size={16} />
            Aktualisieren
          </button>
        }>
          {error ? <Alert>{error}</Alert> : !data ? <Loading /> : <PlanView data={data} />}
        </Card>
      </div>
    </>
  )
}

function classificationError(data: ClassificationResponse): string {
  if (data.error && CLASSIFICATION_ERRORS[data.error]) return CLASSIFICATION_ERRORS[data.error]
  if (data.error === 'classification_error') {
    return `Klassifizierungs-Aufruf fehlgeschlagen: ${data.ai_call?.error ?? 'unbekannter Grund'}`
  }
  return data.error ?? 'Klassifizierung fehlgeschlagen.'
}

function publishMessage(result: PublishResult): string {
  if (!result.ok) {
    return result.reason ?? `Fehlgeschlagen: ${(result.failed ?? []).map((item) => item.entity_id).join(', ')}`
  }
  const written = (result.written ?? []).length
  const skipped = (result.skipped ?? []).length
  // Modusbedingt Übersprungenes mitzählen (D-057): sonst wirkt „5 geschrieben“ so, als
  // wäre alles durchgelaufen, obwohl ein Original-Schreibweg gesperrt war.
  return `${written} Sensor(en) geschrieben${skipped ? ` — ${skipped} gesperrt (Modus)` : ''}.`
}

function ClassificationView({ data }: { data: ClassificationResponse }) {
  if (!data.ok) return <Alert>{classificationError(data)}</Alert>
  const objectives = data.objectives ?? []
  return (
    <>
      {objectives.length ? (
        <DataTable
          head={
            <tr>
              <th>Ziel</th>
              <th className="num">Gewicht</th>
            </tr>
          }
        >
          {objectives.map((objective) => (
            <tr key={objective.key}>
              <td className="cell-title">{objective.label}</td>
              <td className="num">{objective.weight} %</td>
            </tr>
          ))}
        </DataTable>
      ) : (
        <p className="muted">Keine Ziele konfiguriert.</p>
      )}
      {data.reasoning ? (
        <p>
          <b>Begründung:</b> {data.reasoning}
        </p>
      ) : null}
      {data.ai_call?.tokens_in != null ? (
        <p className="muted">
          Tokens (ein/aus): {data.ai_call.tokens_in} / {data.ai_call.tokens_out}
        </p>
      ) : null}
      <ContextDetails title="An die KI gesendete Daten (Klassifizierung)" context={data.context} />
    </>
  )
}

function PlanView({ data }: { data: PlanResponse }) {
  const validation = data.validation ?? {}
  const errors = validation.errors ?? []
  const clamped = validation.clamped ?? []
  const plan = data.plan

  if (!plan) {
    return errors.length ? (
      <Alert>
        {errors.map((message) => (
          <div key={message}>{message}</div>
        ))}
      </Alert>
    ) : (
      <Empty
        icon="bolt"
        text="Noch kein Plan erzeugt. Dafür braucht es einen KI-Schlüssel in der Addon-Konfiguration und vom HEMS erkannte Geräte."
      />
    )
  }

  const meta: [string, string][] = [
    ['Status', validation.ok ? 'gültig' : 'abgelehnt'],
    ['Anbieter / Modell', `${plan.provider ?? '–'} / ${plan.model ?? '–'}`],
    ['Konfidenz (schwächstes Glied)', plan.confidence == null ? '–' : `${plan.confidence} %`],
    ['Gültig von', isoDE(plan.valid_from)],
    ['Gültig bis', isoDE(plan.valid_until)],
  ]
  if (data.ts) meta.push(['Erzeugt', isoDE(data.ts)])
  if (data.ai_call?.tokens_in != null) {
    meta.push(['Tokens (ein/aus)', `${data.ai_call.tokens_in} / ${data.ai_call.tokens_out}`])
  }

  return (
    <>
      <Kv rows={meta} />
      {data.reused ? (
        <div className="info-strip">
          <Icon name="check" size={16} />
          <span>
            Unverändert übernommen: die Sachlage ist identisch zum letzten Lauf, deshalb wurde
            die KI nicht erneut gefragt.
          </span>
        </div>
      ) : null}
      {data.ai_call?.sampling_dropped ? (
        <div className="info-strip">
          <Icon name="warn" size={16} />
          <span>
            Determinismus aus: das Modell nimmt <code className="mono">temperature</code> und
            <code className="mono"> seed</code> nicht an. Gleiche Daten können unterschiedliche
            Antworten ergeben.
          </span>
        </div>
      ) : null}
      {validation.publish_blocked ? (
        <div className="info-strip">
          <Icon name="warn" size={16} />
          <span>Nicht nach HA geschrieben — {validation.publish_blocked}</span>
        </div>
      ) : null}
      {errors.length ? <Alert>Fehler: {errors.join('; ')}</Alert> : null}
      {clamped.length ? (
        <div className="info-strip">
          <Icon name="warn" size={16} />
          <span>Geklemmt oder ergänzt: {clamped.join('; ')}</span>
        </div>
      ) : null}

      <h3>Geräte-Vorschläge</h3>
      {(plan.devices ?? []).map((device) => {
        const entries = Object.entries(device).filter(([key]) => !EXPLANATION_KEYS.has(key))
        return (
          <div key={String(device.name)}>
            <h3>{deviceHeading(String(device.name))}</h3>
            {entries.length ? (
              <DataTable
                head={
                  <tr>
                    <th>Feld</th>
                    <th className="num">Vorschlag</th>
                  </tr>
                }
              >
                {entries.map(([key, value]) => (
                  <tr key={key}>
                    <td className="cell-title">{planFieldLabel(key)}</td>
                    <td className="num">{anyValue(value)}</td>
                  </tr>
                ))}
              </DataTable>
            ) : (
              <p className="muted">Keine Vorschläge für dieses Gerät.</p>
            )}
            <DeviceReasoning device={device} />
          </div>
        )
      })}

      {data.published ? <PublishedView result={data.published} /> : null}

      {plan.reasoning ? (
        <>
          <h3>Begründung</h3>
          <p>{plan.reasoning}</p>
        </>
      ) : null}

      <ConfidenceView plan={plan} />

      {plan.warnings?.length ? (
        <>
          <h3>Warnungen</h3>
          <ul>
            {plan.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </>
      ) : null}

      <ContextDetails title="An die KI gesendete Daten" context={data.context} />
    </>
  )
}

function PublishedView({ result }: { result: PublishResult }) {
  const written = result.written ?? []
  const failed = result.failed ?? []
  const skipped = result.skipped ?? []
  if (!written.length && !failed.length && !skipped.length && !result.reason) return null

  return (
    <>
      <h3>Nach Home Assistant geschrieben</h3>
      {written.length ? (
        <p>
          <span className="pill ok">geschrieben</span>{' '}
          {written.map((entity) => (
            <code className="mono" key={entity}>
              {entity}{' '}
            </code>
          ))}
        </p>
      ) : null}
      {failed.length ? (
        <p>
          <span className="pill err">fehlgeschlagen</span>{' '}
          {failed.map((item) => (
            <span key={item.entity_id}>
              <code className="mono">{item.entity_id}</code> ({item.error}){' '}
            </span>
          ))}
        </p>
      ) : null}
      {skipped.length ? (
        <p>
          <span className="pill warn">gesperrt</span>{' '}
          {skipped.map((item) => (
            <span key={item.entity_id}>
              <code className="mono">{item.entity_id}</code> ({item.reason}){' '}
            </span>
          ))}
        </p>
      ) : null}
      {!written.length && !failed.length && !skipped.length && result.reason ? (
        <p className="muted">{result.reason}</p>
      ) : null}
    </>
  )
}

/** Der an die KI gesendete Kontext — aufklappbar, weil er lang ist, aber sichtbar,
    weil Transparenz über die gesendeten Daten Teil des Datenminimum-Versprechens ist. */
function ContextDetails({ title, context }: { title: string; context: unknown }) {
  if (!context) return null
  return (
    <details className="advanced-card">
      <summary>{title}</summary>
      <pre className="mono">{JSON.stringify(context, null, 2)}</pre>
    </details>
  )
}


/** Begründung und angewandte Regeln je Gerät (D-060): macht eine Fehlentscheidung lesbar. */
function DeviceReasoning({ device }: { device: PlanDevice }) {
  const begruendung = typeof device.begruendung === 'string' ? device.begruendung : ''
  const regeln = Array.isArray(device.angewandte_regeln)
    ? (device.angewandte_regeln as unknown[]).map(String)
    : []
  if (!begruendung && !regeln.length) return null
  return (
    <div className="info-strip">
      <Icon name="info" size={16} />
      <span>
        {begruendung}
        {regeln.length ? (
          <>
            {' '}
            <b>Regeln:</b> {regeln.join(' · ')}
          </>
        ) : (
          <>
            {' '}
            <b>Keine Regel gegriffen.</b>
          </>
        )}
      </span>
    </div>
  )
}

/** Konfidenz-Teilnoten und offene Unsicherheiten (D-064).

    Eine nackte Gesamtzahl sagt nicht, WARUM die KI unsicher war — die Teilnoten schon, und
    die Gesamtnote ist deren Minimum (schwächstes Glied). */
function ConfidenceView({ plan }: { plan: Plan }) {
  const parts = Object.entries(plan.konfidenz_teilnoten ?? {})
  const unsicherheiten = plan.unsicherheiten ?? []
  if (!parts.length && !unsicherheiten.length) return null
  return (
    <>
      <h3>Konfidenz</h3>
      {parts.length ? (
        <DataTable
          head={
            <tr>
              <th>Teilnote</th>
              <th className="num">Wert</th>
            </tr>
          }
        >
          {parts.map(([key, value]) => (
            <tr key={key}>
              <td className="cell-title">{CONFIDENCE_LABEL[key] ?? key}</td>
              <td className="num">{value} %</td>
            </tr>
          ))}
        </DataTable>
      ) : null}
      {unsicherheiten.length ? (
        <>
          <h3>Was der KI gefehlt hat</h3>
          <ul>
            {unsicherheiten.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      ) : null}
    </>
  )
}
