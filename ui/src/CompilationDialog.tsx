import { CheckCircle, Question, Skull, Sparkle, X, YoutubeLogo } from '@phosphor-icons/react'
import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { api, fmtTime, type MatchSummary } from './api'
import { Spinner, useToast } from './ui'

const OUTCOME = {
  extracted: { label: 'Extraction', icon: CheckCircle, color: 'var(--success)' },
  dead: { label: 'Mort', icon: Skull, color: 'var(--danger)' },
  unknown: { label: '?', icon: Question, color: 'var(--text-3)' },
}
const PER_MATCH_S = 150 // ~2 min 30 condensées par partie, carton-titre compris

/** Choisir des parties (de une ou plusieurs vidéos) et en faire une vidéo YouTube 16:9. */
export default function CompilationDialog({ onClose }: { onClose: () => void }) {
  const [matches, setMatches] = useState<MatchSummary[] | null>(null)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const key = (m: MatchSummary) => `${m.vid}:${m.id}`

  useEffect(() => {
    api.allMatches().then(list => {
      const ordered = [...list].sort((a, b) => a.added_at - b.added_at || a.start - b.start)
      setMatches(ordered)
      setPicked(new Set(ordered.filter(m => m.worth).map(key)))  // les bonnes parties sont cochées d'office
    })
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !busy) onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, busy])

  const groups = useMemo(() => {
    const g = new Map<string, MatchSummary[]>()
    for (const m of matches ?? []) g.set(m.video, [...(g.get(m.video) ?? []), m])
    return [...g.entries()]
  }, [matches])
  const chosen = (matches ?? []).filter(m => picked.has(key(m)))
  const toggle = (m: MatchSummary) => setPicked(p => { const n = new Set(p); n.has(key(m)) ? n.delete(key(m)) : n.add(key(m)); return n })

  const create = async () => {
    setBusy(true)
    try {
      await api.compile(chosen.map(m => [m.vid, m.id] as [string, number]), title)
      toast(`Vidéo YouTube de ${chosen.length} partie${chosen.length > 1 ? 's' : ''} lancée : suis-la dans la file`, 'success')
      onClose()
    } catch (e) {
      toast((e as Error).message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return createPortal(
    <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && !busy && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="compile-title">
        <div className="modal-head">
          <YoutubeLogo size={22} weight="fill" color="#ff3b3b" aria-hidden />
          <h2 id="compile-title" className="section-title">Créer une vidéo YouTube</h2>
          <span className="grow" />
          <button className="btn icon ghost" onClick={onClose} aria-label="Fermer"><X size={18} /></button>
        </div>
        <div className="compile-body">
          <p className="faint" style={{ margin: 0 }}>
            Format 16:9. Chaque partie commence par un carton-titre, puis sa version condensée (~2 min 30).
            Fondu au noir entre les parties. Chapitres YouTube, sous-titres .srt et miniature fournis.
          </p>
          <div>
            <label className="field-label" htmlFor="compile-name">Titre (pour la miniature et le nom du fichier)</label>
            <input id="compile-name" className="input" value={title} onChange={e => setTitle(e.target.value)} placeholder="3 parties folles sur le Bayou" />
          </div>
          {matches === null ? <div className="skeleton" style={{ height: 200 }} /> : matches.length === 0 ? (
            <p className="faint">Aucune partie reconnue pour l'instant : analyse une session de Hunt d'abord.</p>
          ) : (
            <div className="compile-list">
              {groups.map(([video, list]) => (
                <section key={video}>
                  <div className="eyebrow" style={{ margin: '10px 0 6px' }}>{video}</div>
                  {list.map(m => {
                    const o = OUTCOME[m.outcome]
                    const OI = o.icon
                    const on = picked.has(key(m))
                    return (
                      <label key={key(m)} className={`compile-row ${on ? 'on' : ''}`}>
                        <input type="checkbox" checked={on} onChange={() => toggle(m)} aria-label={`Partie ${m.id + 1} de ${video}`} />
                        <span className="moment-title" style={{ fontSize: 16 }}>Partie {m.id + 1}</span>
                        <span className="mono faint" style={{ fontSize: 12 }}>{fmtTime(m.start)} · {Math.round((m.end - m.start) / 60)} min</span>
                        <span className="chip" style={{ color: o.color }}><OI size={12} weight="fill" aria-hidden />{o.label}</span>
                        <span className="faint" style={{ fontSize: 12 }}>{m.kills} kill{m.kills > 1 ? 's' : ''} · {m.clues} indice{m.clues > 1 ? 's' : ''}{m.boss ? ' · boss' : ''}{m.bounty ? ' · prime' : ''}</span>
                        <span className="grow" />
                        <span className="potential" title="Potentiel">{m.potential}</span>
                      </label>
                    )
                  })}
                </section>
              ))}
            </div>
          )}
        </div>
        <div className="confirm-actions">
          <span className="faint grow" style={{ alignSelf: 'center' }}>
            {chosen.length} partie{chosen.length > 1 ? 's' : ''} · environ {Math.round(chosen.length * PER_MATCH_S / 60)} min
          </span>
          <button className="btn" onClick={onClose} disabled={busy}>Annuler</button>
          <button className="btn primary" onClick={create} disabled={busy || !chosen.length}>
            {busy ? <Spinner /> : <Sparkle size={16} weight="fill" aria-hidden />} Créer la vidéo
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
