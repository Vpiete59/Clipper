import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  api, EVENT_COLOR, fileUrl, fmtTime, STAGE_LABEL, STATUS_LABEL,
  type Analysis, type Game, type Moment, type Render, type Video,
} from './api'

const SIGNAL_LANES: [string, string][] = [
  ['gunshot', '#ff5a4e'], ['loudness_spike', '#64748b'], ['laughter', '#f472b6'], ['speech_excited', '#c084fc'],
]

type Props = { id: string; games: Game[]; summary?: Video; onBack: () => void }

export default function VideoView({ id, games, summary, onBack }: Props) {
  const [video, setVideo] = useState<Video | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [renders, setRenders] = useState<Render[]>([])
  const [time, setTime] = useState(0)
  const [active, setActive] = useState<number | null>(null)
  const [toast, setToast] = useState('')
  const player = useRef<HTMLVideoElement>(null)
  const loopEnd = useRef<number | null>(null)

  const load = useCallback(() => api.video(id).then(d => {
    setVideo(d.video); setAnalysis(d.analysis); setRenders(d.renders)
  }), [id])

  useEffect(() => { load() }, [load, summary?.status, summary?.n_moments])

  const notify = (msg: string) => { setToast(msg); setTimeout(() => setToast(''), 3000) }

  const seek = (t: number, until?: number) => {
    const p = player.current
    if (!p) return
    p.currentTime = t
    loopEnd.current = until ?? null
    p.play()
  }

  const onTime = () => {
    const p = player.current
    if (!p) return
    setTime(p.currentTime)
    if (loopEnd.current !== null && p.currentTime >= loopEnd.current) {
      p.pause()
      loopEnd.current = null
    }
  }

  const patchMoment = async (m: Moment, patch: Partial<Moment>) => {
    await api.patchMoment(id, m.id, patch)
    load()
  }

  const v = summary ?? video
  if (!v) return <div className="page muted">Chargement…</div>
  const busy = ['queued', 'analyzing', 'rendering', 'rendering_queued'].includes(v.status)
  const duration = analysis?.duration ?? v.duration ?? 1
  const outDir = renders[0]?.path.replace(/[\\/][^\\/]+$/, '')

  return (
    <div className="page">
      <div className="page-head">
        <button className="btn ghost small" onClick={onBack}>‹ Retour</button>
        <h1 className="grow" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v.name}</h1>
        <select value={v.game} onChange={async e => {
          const r = await api.setGame(id, e.target.value)
          if (r.needs_reanalyze) notify('Jeu changé : relance l\'analyse pour lire le HUD de ce jeu')
          load()
        }}>
          {games.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
        </select>
        <button className="btn" disabled={busy} onClick={() => api.analyze(id).then(() => notify('Analyse relancée'))}>
          {analysis ? 'Ré-analyser' : 'Analyser'}
        </button>
        <button className="btn primary" disabled={busy || !analysis?.moments.length}
          onClick={() => api.render(id, null, true).then(() => notify('Rendu des clips + montage lancé'))}>
          Rendre tout + montage
        </button>
      </div>

      {busy && (
        <div className="card" style={{ padding: 14, marginBottom: 16 }}>
          <div className="row">
            <span className="pill busy">{v.stage ? STAGE_LABEL[v.stage] ?? v.stage : STATUS_LABEL[v.status]}</span>
            <span className="muted">{Math.round(v.progress * 100)} %</span>
          </div>
          <div className="progress"><div style={{ width: `${v.progress * 100}%` }} /></div>
        </div>
      )}
      {v.status === 'error' && (
        <div className="card" style={{ padding: 14, marginBottom: 16, color: 'var(--danger)' }}>{v.error}</div>
      )}

      <div className="video-layout">
        <div>
          <div className={`player-wrap ${analysis?.orientation === 'portrait' || v.orientation === 'portrait' ? 'portrait' : ''}`}>
            <video ref={player} src={`/media/source/${id}`} controls onTimeUpdate={onTime} preload="metadata" />
          </div>

          {analysis && (
            <Timeline analysis={analysis} duration={duration} time={time} active={active}
              onSeek={t => seek(t)} />
          )}

          {renders.length > 0 && (
            <>
              <div className="page-head" style={{ marginTop: 26, marginBottom: 0 }}>
                <h2>Clips rendus</h2>
                <div className="spacer" />
                {outDir && <button className="btn small" onClick={() => api.reveal(outDir)}>Ouvrir le dossier</button>}
              </div>
              <div className="renders">
                {renders.map(r => (
                  <div key={r.id} className="card render-card">
                    <video src={`${fileUrl(r.path)}&v=${r.created_at}`} controls preload="metadata" />
                    <div className="row">
                      <span className="grow">{r.kind === 'montage' ? '★ Montage' : `Clip #${r.moment_id}`}</span>
                      <button className="btn small ghost" onClick={() => api.reveal(r.path)}>↗</button>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="side">
          {analysis ? (
            <>
              <div className="card side-section">
                <div className="row" style={{ marginBottom: 10 }}>
                  <h3 className="grow" style={{ margin: 0 }}>Moments forts ({analysis.moments.length})</h3>
                  <button className="btn small" onClick={async () => {
                    await api.addMoment(id, Math.max(0, time - 12), Math.min(duration, time + 4), 'Moment fort')
                    load(); notify('Moment ajouté autour de la position actuelle')
                  }}>+ Ici</button>
                </div>
                {analysis.moments.length === 0 && <p className="muted">Aucun moment au-dessus du score minimum. Baisse-le dans les réglages ou ajoute-en un à la main.</p>}
                {analysis.moments.map(m => (
                  <MomentCard key={`${m.id}-${m.start}`} m={m} active={active === m.id}
                    onPlay={() => { setActive(m.id); seek(m.start, m.end) }}
                    onPatch={p => patchMoment(m, p)}
                    onRender={() => api.render(id, [m.id], false).then(() => notify(`Rendu du clip #${m.id} lancé`))}
                    disabled={busy} />
                ))}
              </div>
              <Subtitles analysis={analysis} time={time} onSeek={t => seek(t)}
                onEdit={async (s, w, text) => { await api.editWord(id, s, w, text); load() }} />
            </>
          ) : (
            <div className="card side-section muted">Les moments forts et les sous-titres apparaîtront ici après l'analyse.</div>
          )}
        </div>
      </div>
      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}

function Timeline({ analysis, duration, time, active, onSeek }: {
  analysis: Analysis; duration: number; time: number; active: number | null; onSeek: (t: number) => void
}) {
  const pct = (t: number) => `${(t / duration) * 100}%`
  const lanes = useMemo(() => SIGNAL_LANES.filter(([k]) => analysis.timeline[k]?.length).map(([k, color]) => {
    const values = analysis.timeline[k]
    const pts = values.map((val, i) => `${(i / Math.max(1, values.length - 1)) * 1000},${40 - val * 38}`).join(' ')
    return { k, color, pts }
  }), [analysis])
  const types = [...new Set(analysis.events.map(e => e.type))]

  return (
    <div className="card timeline">
      <div className="lanes" onClick={e => {
        const r = e.currentTarget.getBoundingClientRect()
        onSeek(((e.clientX - r.left) / r.width) * duration)
      }}>
        {analysis.moments.map(m => (
          <div key={m.id} className={`moment-band ${m.excluded ? 'excluded' : ''}`}
            style={{ left: pct(m.start), width: pct(m.end - m.start), boxShadow: active === m.id ? '0 0 0 1px var(--accent)' : undefined }}>
            <span>#{m.id}</span>
          </div>
        ))}
        <svg className="lane-sig" viewBox="0 0 1000 40" preserveAspectRatio="none">
          {lanes.map(l => <polyline key={l.k} points={l.pts} fill="none" stroke={l.color} strokeWidth="1.2" vectorEffect="non-scaling-stroke" opacity="0.8" />)}
        </svg>
        {analysis.events.map((e, i) => (
          <div key={i} className="ev-dot" title={`${fmtTime(e.t)} · ${e.label}${e.text ? ` « ${e.text} »` : ''}`}
            style={{ left: pct(e.t), background: EVENT_COLOR[e.type] ?? '#aaa' }} />
        ))}
        <div className="playhead" style={{ left: pct(time) }} />
      </div>
      <div className="legend">
        {types.map(t => {
          const ev = analysis.events.find(e => e.type === t)!
          return <span key={t}><i style={{ background: EVENT_COLOR[t] ?? '#aaa' }} />{ev.label}</span>
        })}
        <span className="grow" />
        <span>{fmtTime(time)} / {fmtTime(duration)}</span>
      </div>
    </div>
  )
}

function MomentCard({ m, active, onPlay, onPatch, onRender, disabled }: {
  m: Moment; active: boolean; onPlay: () => void; onPatch: (p: Partial<Moment>) => void; onRender: () => void; disabled: boolean
}) {
  const [hook, setHook] = useState(m.hook ?? m.title)
  const labels = [...new Set(m.events.map(e => e.label))]
  return (
    <div className={`moment ${active ? 'active' : ''} ${m.excluded ? 'excluded' : ''}`}>
      <div className="moment-head">
        <button className="btn small" onClick={onPlay}>▶</button>
        <div className="moment-title">#{m.id} · {fmtTime(m.start)} → {fmtTime(m.end)}</div>
        <span className="score" style={{ color: 'var(--accent)' }}>{Math.round(m.score)}</span>
      </div>
      <div className="moment-tags">
        {labels.map(l => {
          const type = m.events.find(e => e.label === l)!.type
          return <span key={l} className="tag" style={{ color: EVENT_COLOR[type] }}>{l}</span>
        })}
        {m.manual && <span className="tag">manuel</span>}
      </div>
      <input type="text" value={hook} title="Texte d'accroche affiché en haut du clip"
        onChange={e => setHook(e.target.value)} onBlur={() => hook !== (m.hook ?? m.title) && onPatch({ hook })} />
      <div className="moment-actions">
        <button className="btn small" onClick={() => onPatch({ start: Math.max(0, m.start - 2) })}>Début −2s</button>
        <button className="btn small" onClick={() => onPatch({ end: m.end + 2 })}>Fin +2s</button>
        <button className="btn small" onClick={() => onPatch({ excluded: !m.excluded })}>{m.excluded ? 'Inclure' : 'Exclure'}</button>
        <button className="btn small primary" disabled={disabled} onClick={onRender}>Rendre</button>
      </div>
    </div>
  )
}

function Subtitles({ analysis, time, onSeek, onEdit }: {
  analysis: Analysis; time: number; onSeek: (t: number) => void; onEdit: (s: number, w: number, text: string) => void
}) {
  const [editing, setEditing] = useState<[number, number] | null>(null)
  const [draft, setDraft] = useState('')
  return (
    <div className="card side-section">
      <h3>Sous-titres <span style={{ textTransform: 'none', letterSpacing: 0 }}>— clique un mot pour le corriger</span></h3>
      <div className="subs">
        {analysis.segments.length === 0 && <p className="muted">Aucune parole détectée.</p>}
        {analysis.segments.map((seg, si) => (
          <div key={si} className="seg">
            <span className="seg-time" onClick={() => onSeek(seg.start)}>{fmtTime(seg.start)}</span>
            {seg.words.map((w, wi) => editing?.[0] === si && editing?.[1] === wi ? (
              <input key={wi} type="text" autoFocus value={draft} onChange={e => setDraft(e.target.value)}
                onBlur={() => setEditing(null)}
                onKeyDown={e => {
                  if (e.key === 'Enter') { onEdit(si, wi, draft); setEditing(null) }
                  if (e.key === 'Escape') setEditing(null)
                }} />
            ) : (
              <span key={wi} className={`w ${w.prob < 0.5 ? 'low' : ''} ${time >= w.start && time < w.end ? 'now' : ''}`}
                title={`${fmtTime(w.start)} · confiance ${Math.round(w.prob * 100)} %`}
                onClick={() => { setEditing([si, wi]); setDraft(w.word) }}>{w.word} </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
