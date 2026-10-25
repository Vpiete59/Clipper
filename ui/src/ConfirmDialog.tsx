import { Trash, X } from '@phosphor-icons/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Spinner } from './ui'

export type ConfirmOption = { key: string; label: string; hint?: string; defaultChecked?: boolean }

type Props = {
  title: string
  children?: ReactNode
  options?: ConfirmOption[]
  confirmLabel: string
  onConfirm: (checked: Record<string, boolean>) => Promise<void>
  onClose: () => void
}

/** Confirmation avant suppression : Échap ou clic à côté annulent, le bouton principal est rouge. */
export default function ConfirmDialog({ title, children, options = [], confirmLabel, onConfirm, onClose }: Props) {
  const [checked, setChecked] = useState<Record<string, boolean>>(
    Object.fromEntries(options.map(o => [o.key, !!o.defaultChecked])))
  const [busy, setBusy] = useState(false)
  const cancel = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    cancel.current?.focus()  // le focus va sur « Annuler » : Entrée par réflexe ne supprime rien
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !busy) onClose() }
    window.addEventListener('keydown', onKey)
    return () => { window.removeEventListener('keydown', onKey); previous?.focus() }
  }, [onClose, busy])

  const go = async () => {
    setBusy(true)
    try { await onConfirm(checked) } finally { setBusy(false) }
  }

  return createPortal(
    <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && !busy && onClose()}>
      <div className="modal confirm" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title">
        <div className="modal-head">
          <Trash size={20} weight="fill" color="var(--danger)" aria-hidden />
          <h2 id="confirm-title" className="section-title">{title}</h2>
          <span className="grow" />
          <button className="btn icon ghost" onClick={onClose} disabled={busy} aria-label="Fermer"><X size={18} /></button>
        </div>
        <div className="confirm-body">
          {children}
          {options.map(o => (
            <label key={o.key} className="confirm-option">
              <input type="checkbox" aria-label={o.label} checked={checked[o.key]} onChange={e => setChecked({ ...checked, [o.key]: e.target.checked })} />
              <span><b>{o.label}</b>{o.hint && <small>{o.hint}</small>}</span>
            </label>
          ))}
          <p className="hint" style={{ margin: 0 }}>Les fichiers partent dans la corbeille Windows : tu peux encore les récupérer.</p>
        </div>
        <div className="confirm-actions">
          <button ref={cancel} className="btn" onClick={onClose} disabled={busy}>Annuler</button>
          <button className="btn danger-solid" onClick={go} disabled={busy}>
            {busy ? <Spinner /> : <Trash size={16} weight="fill" aria-hidden />} {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
