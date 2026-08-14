import { useEffect, useState } from 'react'
import type { PromptResponse } from '../types'
import { useToast } from './Toast'

/* Editor für eine der beiden in der Datenbank gespeicherten KI-Instruktionen
   (Planung und Klassifizierung, D-055). Änderungen wirken beim nächsten Lauf und
   überleben Neustart wie Addon-Update — ohne Git-Push. */

export function PromptEditor({
  title,
  hint,
  load,
  save,
}: {
  title: string
  hint: string
  load: () => Promise<PromptResponse>
  save: (prompt: string) => Promise<{ ok: boolean; is_custom?: boolean; reason?: string }>
}) {
  const [prompt, setPrompt] = useState('')
  const [fallback, setFallback] = useState('')
  const [isCustom, setIsCustom] = useState(false)
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()

  useEffect(() => {
    let active = true
    load()
      .then((data) => {
        if (!active) return
        setFallback(data.default ?? '')
        setPrompt(data.prompt ?? '')
        setIsCustom(Boolean(data.is_custom))
      })
      .catch((err: Error) => {
        if (active) toast(err.message, 'err')
      })
    return () => {
      active = false
    }
  }, [load, toast])

  const store = async (text: string) => {
    setSaving(true)
    try {
      const result = await save(text)
      if (result.ok) {
        setIsCustom(Boolean(result.is_custom))
        toast(result.is_custom ? 'Eigener Prompt gespeichert.' : 'Auf den Standard zurückgesetzt.')
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
    <details className="advanced-card">
      <summary>
        {title} <span className={`pill ${isCustom ? 'primary' : 'muted'}`}>{isCustom ? 'eigener Prompt' : 'Standard'}</span>
      </summary>
      <p className="muted">{hint}</p>
      <label className="field">
        <span>Instruktion</span>
        <textarea rows={14} value={prompt} onChange={(event) => setPrompt(event.target.value)} />
      </label>
      <div className="inline-actions">
        <button type="button" className="btn btn-primary" disabled={saving} onClick={() => void store(prompt)}>
          {saving ? 'Speichern…' : 'Speichern'}
        </button>
        <button
          type="button"
          className="btn btn-ghost"
          disabled={saving}
          onClick={() => {
            setPrompt(fallback)
            void store('')
          }}
        >
          Auf Standard zurücksetzen
        </button>
      </div>
    </details>
  )
}
