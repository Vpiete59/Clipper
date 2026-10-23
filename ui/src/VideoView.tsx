import {
  ArrowCounterClockwise, ArrowLeft, ArrowSquareOut, Check, CheckCircle, ClosedCaptioning, DeviceMobile,
  Eye, EyeSlash, FilmStrip, FolderOpen, Lightning, Pause, Play, Plus, Quotes, Sparkle, Star, Warning,
} from '@phosphor-icons/react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { BUSY } from './App'
import { api, fileUrl, fmtTime, STAGE_LABEL, type Analysis, type Game, type Moment, type Render, type Video } from './api'
import { EventChip, eventStyle, ScoreRing, Spinner, useToast } from './ui'

const STAGES: [string, number, number][] = [
  ['audio', 0, 0.03], ['transcription', 0.03, 0.4], ['sons', 0.4, 0.55], ['image', 0.55, 0.97], ['moments', 0.97, 1],
]
const SIGNALS: [string, string][] = [['gunshot', '#ff6b5e'], ['loudness_spike', '#6b6b76'], ['speech_excited', '#b98cff'], ['laughter', '#f78fc5']]

// élisions et ponctuation découpées par Whisper : collées au mot précédent, comme dans le rendu
const GLUE = /^['’\-.,!?…)]/

type Props = { id: string; games: Game[]; summary?: Video; onBack: () => void }

export default function VideoView({ id, games, summary, onBack }: Props) {
  const [video, setVideo] = useState<Video | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [renders, setRenders] = useState<Render[]>([])
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [active, setActive] = useState<number | null>(null)
  const [tab, setTab] = useState<'moments' | 'subs'>('moments')
  const player = useRef<HTMLVideoElement>(null)
  const loopEnd = useRef<number | null>(null)
  const toast = useToast()

  const load = useCallback(() => api.video(id).then(d => {
    setVideo(d.video); setAnalysis(d.analysis); setRenders(d.renders)
  }), [id])
  useEffect(() => { load() }, [load, summary?.status, summary?.n_moments])

  const v = summary ?? video
  const duration = analysis?.duration ?? v?.duration ?? 1

  const seek = useCallback((t: number, until?: number, play = true) => {
    const p = player.current
    if (!p) return
    p.currentTime = Math.max(0, Math.min(duration, t))
    loopEnd.current = until ?? null
    if (play) p.play()
  }, [duration])

  const togglePlay = useCallback(() => {
    const p = player.current
    if (p) p.paused ? p.play() : p.pause()
  }, [])

  const addMomentHere = useCallback(async () => {
    const t = player.current?.currentTime ?? 0
    await api.addMoment(id, Math.max(0, t - 12), Math.min(duration, t + 4), 'Moment fort')
    await load()
    setTab('moments')
    toast('Moment ajouté autour de la position actuelle', 'success')
  }, [id, duration, load, toast])

  // raccourcis : Espace, ← →, M
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.isContentEditable) return
      const p = player.current
      if (!p) return
      if (e.code === 'Space') { e.preventDefault(); togglePlay() }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); seek(p.currentTime - 5, undefined, !p.paused) }
      else if (e.key === 'ArrowRight') { e.preventDefault(); seek(p.currentTime + 5, undefined, !p.paused) }
      else if (e.key.toLowerCase() === 'm' && analysis) { e.preventDefault(); addMomentHere() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [togglePlay, seek, addMomentHere, analysis])

  const onTime = () => {
    const p = player.current
    if (!p) return
    setTime(p.currentTime)
    if (loopEnd.current !== null && p.currentTime >= loopEnd.current) { p.pause(); loopEnd.current = null }
  }

  const patchMoment = async (m: Moment, patch: Partial<Moment>) => { await api.patchMoment(id, m.id, patch); load() }

  if (!v) return <div className="page"><div className="skeleton" style={{ height: 480 }} /></div>
  const busy = BUSY.includes(v.status)
  const portrait = (analysis?.orientation ?? v.orientation) === 'portrait'
  const gameName = games.find(g => g.id === v.game)?.name ?? v.game
  const renderedIds = new Set(renders.filter(r => r.kind === 'clip').map(r => r.moment_id))
  const outDir = renders[0]?.path.replace(/[\\/][^\\/]+$/, '')
  const included = analysis?.moments.filter(m => !m.excluded).length ?? 0

  return (
    <div className="page">
      <div className="editor-head">
        <button className="btn icon ghost" onClick={onBack} aria-label="Retour à la bibliothèque" title="Retour"><ArrowLeft size={20} /></button>
        <div className="grow" style={{ minWidth: 0 }}>
          <h1 className="editor-title ellipsis" title={v.name}>{v.name}</h1>
          <div className="editor-meta">
            <span className="mono">{fmtTime(duration)}</span>
            {portrait && <span className="row" style={{ gap: 4 }}><DeviceMobile size={13} aria-hidden /> Source verticale</span>}
            {analysis && <span>{analysis.segments.length} phrases transcrites</span>}
          </div>
        </div>
        <select className="select" style={{ width: 220 }} aria-label="Jeu" value={v.game} onChange={async e => {
          const r = await api.setGame(id, e.target.value)
          if (r.needs_reanalyze) toast('Jeu changé : relance l\'analyse pour lire le HUD de ce jeu')
          load()
        }}>
          {games.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
        </select>
        <button className="btn" disabled={busy} onClick={() => api.analyze(id).then(() => toast('Analyse relancée'))}>
          <ArrowCounterClockwise size={16} aria-hidden /> {analysis ? 'Ré-analyser' : 'Analyser'}
        </button>
        <button className="btn primary" disabled={busy || !included}
          onClick={() => api.render(id, null, true).then(() => toast(`Rendu de ${included} clip${included > 1 ? 's' : ''} + montage lancé`, 'success'))}>
          <Sparkle size={16} weight="fill" aria-hidden /> Rendre {included || ''} clip{included > 1 ? 's' : ''} + montage
        </button>
      </div>

      {busy && <Progress v={v} />}
      {v.status === 'error' && (
        <div className="card stepper" style={{ borderColor: 'rgba(242,85,90,0.4)' }} role="alert">
          <div className="row" style={{ color: 'var(--danger)', fontWeight: 600 }}><Warning size={18} weight="fill" aria-hidden /> Le traitement a échoué</div>
          <div className="mono faint" style={{ marginTop: 6, fontSize: 12 }}>{v.error}</div>
          <button className="btn sm" style={{ marginTop: 12 }} onClick={() => api.analyze(id)}><ArrowCounterClockwise size={14} aria-hidden /> Réessayer</button>
        </div>
      )}

      <div className="editor-layout">
        <div style={{ minWidth: 0 }}>
          <div className={`player ${portrait ? 'portrait' : ''}`}>
            <video ref={player} src={`/media/source/${id}`} controls onTimeUpdate={onTime} preload="metadata"
              onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} />
          </div>
          <div className="player-bar">
            <button className="btn sm icon" onClick={togglePlay} aria-label={playing ? 'Pause' : 'Lecture'}>
              {playing ? <Pause size={15} weight="fill" /> : <Play size={15} weight="fill" />}
            </button>
            <span className="timecode"><b>{fmtTime(time)}</b> / {fmtTime(duration)}</span>
            <span className="grow" />
            <div className="shortcuts" aria-label="Raccourcis clavier">
              <span><kbd className="kbd">Espace</kbd> lecture</span>
              <span><kbd className="kbd">←</kbd><kbd className="kbd">→</kbd> 5 s</span>
              {analysis && <span><kbd className="kbd">M</kbd> nouveau moment</span>}
            </div>
          </div>

          {analysis ? (
            <Timeline analysis={analysis} duration={duration} time={time} active={active}
              onSeek={t => seek(t, undefined, !player.current?.paused)}
              onSelect={m => { setActive(m.id); setTab('moments'); seek(m.start, m.end) }} />
          ) : !busy && (
            <div className="card empty" style={{ marginTop: 16 }}>
              <p>Cette vidéo n'a pas encore été analysée ({gameName}).</p>
              <button className="btn primary" onClick={() => api.analyze(id)}><Sparkle size={16} weight="fill" aria-hidden /> Lancer l'analyse</button>
            </div>
          )}

          {renders.length > 0 && (
            <>
              <div className="clips-head">
                <FilmStrip size={22} className="faint" aria-hidden />
                <h2 className="section-title">Clips rendus</h2>
                <span className="faint">{renders.length} fichier{renders.length > 1 ? 's' : ''}</span>
                <span className="grow" />
                {outDir && <button className="btn sm" onClick={() => api.reveal(outDir)}><FolderOpen size={15} aria-hidden /> Ouvrir le dossier</button>}
              </div>
              <div className="clips">
                {[...renders].sort((a, b) => (a.kind === 'montage' ? -1 : b.kind === 'montage' ? 1 : (a.moment_id ?? 0) - (b.moment_id ?? 0))).map((r, i) => (
                  <div key={r.id} className={`card clip ${r.kind === 'montage' ? 'montage' : ''}`} style={{ animationDelay: `${i * 40}ms` }}>
                    <video src={`${fileUrl(r.path)}&v=${r.created_at}`} controls preload="metadata" />
                    <div className="clip-foot">
                      {r.kind === 'montage'
                        ? <><Star size={15} weight="fill" color="var(--accent)" aria-hidden /> Montage</>
                        : <>Clip #{r.moment_id}</>}
                      <span className="grow" />
                      <button className="btn sm icon ghost" onClick={() => api.reveal(r.path)} aria-label="Afficher dans l'Explorateur" title="Afficher dans l'Explorateur">
                        <ArrowSquareOut size={15} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <aside className="card panel" aria-label="Moments et sous-titres">
          <div className="panel-head">
            <div className="tabs" role="tablist">
              <button role="tab" aria-selected={tab === 'moments'} onClick={() => setTab('moments')}>
                <Lightning size={15} weight="fill" aria-hidden /> Moments <span className="count">{analysis?.moments.length ?? 0}</span>
              </button>
              <button role="tab" aria-selected={tab === 'subs'} onClick={() => setTab('subs')}>
                <ClosedCaptioning size={16} aria-hidden /> Sous-titres
              </button>
            </div>
            {analysis && tab === 'moments' && (
              <button className="btn sm icon" onClick={addMomentHere} aria-label="Ajouter un moment ici (M)" title="Ajouter un moment ici (M)"><Plus size={16} weight="bold" /></button>
            )}
          </div>
          <div className="panel-body" role="tabpanel">
            {!analysis ? (
              <p className="faint" style={{ padding: 8 }}>Les moments forts et les sous-titres apparaîtront ici après l'analyse.</p>
            ) : tab === 'moments' ? (
              analysis.moments.length === 0 ? (
                <div className="empty" style={{ padding: '32px 12px' }}>
                  <p>Aucun moment au-dessus du score minimum.</p>
                  <p className="faint" style={{ fontSize: 13 }}>Baisse le seuil dans les réglages, ou place la lecture sur une action et appuie sur <kbd className="kbd">M</kbd>.</p>
                </div>
              ) : analysis.moments.map((m, i) => (
                <MomentCard key={`${m.id}-${m.start}-${m.end}`} vid={id} m={m} index={i} active={active === m.id}
                  rendered={renderedIds.has(m.id)} disabled={busy}
                  onPlay={() => { setActive(m.id); seek(m.start, m.end) }}
                  onPatch={p => patchMoment(m, p)}
                  onRender={() => api.render(id, [m.id], false).then(() => toast(`Rendu du clip #${m.id} lancé`, 'success'))} />
              ))
            ) : (
              <Subtitles analysis={analysis} time={time} onSeek={t => seek(t)}
                onEdit={async (s, w, text) => { await api.editWord(id, s, w, text); load(); toast('Mot corrigé', 'success') }} />
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}

function Progress({ v }: { v: Video }) {
  if (v.status === 'rendering' || v.status === 'rendering_queued') {
    return (
      <div className="card stepper" aria-live="polite">
        <div className="row"><Spinner size={16} /><strong>{v.stage === 'montage' ? 'Assemblage du montage' : 'Rendu des clips verticaux'}</strong><span className="grow" /><span className="mono faint">{Math.round(v.progress * 100)} %</span></div>
        <div className="progress" style={{ marginTop: 12 }}><div style={{ width: `${v.progress * 100}%` }} /></div>
      </div>
    )
  }
  return (
    <div className="card stepper" aria-live="polite">
      <div className="row"><Spinner size={16} /><strong>{v.status === 'queued' ? 'En file d\'attente' : 'Analyse en cours'}</strong><span className="grow" /><span className="mono faint">{Math.round(v.progress * 100)} %</span></div>
      <div className="stepper-steps">
        {STAGES.map(([key, a, b]) => {
          const p = Math.max(0, Math.min(1, (v.progress - a) / (b - a)))
          const state = v.stage === key ? 'active' : p >= 1 ? 'done' : ''
          return (
            <div key={key} className={`stepper-step ${state}`}>
              <div className="bar"><div style={{ width: `${p * 100}%` }} /></div>
              <span>{state === 'done' && <Check size={12} weight="bold" aria-hidden />}{STAGE_LABEL[key]}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function niceStep(duration: number) {
  const target = duration / 8
  return [5, 10, 15, 30, 60, 120, 300, 600, 900, 1800].find(s => s >= target) ?? 3600
}

function Timeline({ analysis, duration, time, active, onSeek, onSelect }: {
  analysis: Analysis; duration: number; time: number; active: number | null
  onSeek: (t: number) => void; onSelect: (m: Moment) => void
}) {
  const [hover, setHover] = useState<number | null>(null)
  const [hidden, setHidden] = useState<Set<string>>(new Set(['loud']))
  const dragging = useRef(false)
  const pct = (t: number) => `${(t / duration) * 100}%`

  const areas = useMemo(() => SIGNALS.filter(([k]) => analysis.timeline[k]?.length).map(([k, color]) => {
    const vals = analysis.timeline[k]
    const n = Math.max(1, vals.length - 1)
    const pts = vals.map((val, i) => `${(i / n) * 1000},${56 - Math.min(1, val) * 50}`).join(' ')
    return { k, color, d: `M0,56 L${pts} L1000,56 Z` }
  }), [analysis])

  const types = useMemo(() => {
    const seen = new Map<string, string>()
    analysis.events.forEach(e => { if (!seen.has(e.type)) seen.set(e.type, e.label) })
    return [...seen.entries()]
  }, [analysis])

  const timeAt = (e: React.PointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    return Math.max(0, Math.min(duration, ((e.clientX - r.left) / r.width) * duration))
  }
  const step = niceStep(duration)
  const ticks = Array.from({ length: Math.floor(duration / step) + 1 }, (_, i) => i * step).filter(t => t < duration - step * 0.3)

  return (
    <div className="card timeline">
      <div className="timeline-head">
        <span className="eyebrow">Timeline</span>
        <span className="faint" style={{ fontSize: 12 }}>Clique ou glisse pour te déplacer, clique un bloc pour lire le moment</span>
      </div>
      <div className="ruler" aria-hidden>
        {ticks.map(t => <span key={t} style={{ left: pct(t) }}>{fmtTime(t)}</span>)}
        {hover !== null && <div className="hovertime" style={{ left: pct(hover), top: -3 }}>{fmtTime(hover)}</div>}
      </div>
      <div className="track" role="slider" aria-label="Position de lecture" aria-valuemin={0} aria-valuemax={Math.round(duration)}
        aria-valuenow={Math.round(time)} aria-valuetext={fmtTime(time)} tabIndex={0}
        onKeyDown={e => {
          if (e.key === 'ArrowLeft') { e.preventDefault(); e.stopPropagation(); onSeek(time - 5) }
          if (e.key === 'ArrowRight') { e.preventDefault(); e.stopPropagation(); onSeek(time + 5) }
        }}
        onPointerDown={e => { dragging.current = true; e.currentTarget.setPointerCapture(e.pointerId); onSeek(timeAt(e)) }}
        onPointerMove={e => { const t = timeAt(e); setHover(t); if (dragging.current) onSeek(t) }}
        onPointerUp={() => { dragging.current = false }}
        onPointerLeave={() => setHover(null)}>
        <div className="track-grid" style={{ backgroundSize: `${(step / duration) * 100}% 100%` }} />
        <svg className="sig" viewBox="0 0 1000 56" preserveAspectRatio="none" aria-hidden>
          {areas.map(a => <path key={a.k} d={a.d} fill={a.color} fillOpacity="0.28" stroke={a.color} strokeOpacity="0.8" strokeWidth="1" vectorEffect="non-scaling-stroke" />)}
        </svg>
        {analysis.moments.map(m => (
          <div key={m.id} className={`mband ${m.excluded ? 'excluded' : ''} ${active === m.id ? 'active' : ''}`}
            style={{ left: pct(m.start), width: pct(m.end - m.start) }} title={`#${m.id} · ${m.title} · ${fmtTime(m.start)} → ${fmtTime(m.end)}`}
            onPointerDown={e => { e.stopPropagation(); onSelect(m) }}>
            <span>#{m.id} {m.title}</span>
          </div>
        ))}
        {analysis.events.filter(e => !hidden.has(e.type)).map((e, i) => {
          const { color, icon: I } = eventStyle(e.type)
          return (
            <div key={i} className="evmark" style={{ left: pct(e.t), background: color }}
              title={`${fmtTime(e.t)} · ${e.label}${e.text ? ` « ${e.text} »` : ''}`}>
              <I size={11} weight="fill" aria-hidden />
            </div>
          )
        })}
        {hover !== null && <div className="hoverline" style={{ left: pct(hover) }} />}
        <div className="playhead" style={{ left: pct(time) }} />
      </div>
      <div className="legend" aria-label="Afficher ou masquer des types d'événements">
        {types.map(([t, label]) => {
          const { color, icon: I } = eventStyle(t)
          const count = analysis.events.filter(e => e.type === t).length
          return (
            <button key={t} aria-pressed={!hidden.has(t)} onClick={() => setHidden(h => {
              const n = new Set(h); n.has(t) ? n.delete(t) : n.add(t); return n
            })}>
              <i style={{ background: color }}><I size={10} weight="fill" aria-hidden /></i>{label} <span className="mono faint">{count}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function MomentCard({ vid, m, index, active, rendered, disabled, onPlay, onPatch, onRender }: {
  vid: string; m: Moment; index: number; active: boolean; rendered: boolean; disabled: boolean
  onPlay: () => void; onPatch: (p: Partial<Moment>) => void; onRender: () => void
}) {
  const [hook, setHook] = useState(m.hook ?? m.title)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => { if (active) ref.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }, [active])
  const kinds = [...new Map(m.events.map(e => [e.type, e])).values()].sort((a, b) => b.score - a.score)
  const saveHook = () => { if (hook.trim() && hook !== (m.hook ?? m.title)) onPatch({ hook: hook.trim() }) }

  return (
    <div ref={ref} className={`moment ${active ? 'active' : ''} ${m.excluded ? 'excluded' : ''}`} style={{ animationDelay: `${Math.min(index, 8) * 35}ms` }}>
      <div className="moment-main">
        <button className="moment-thumb" onClick={onPlay} aria-label={`Lire le moment ${m.id}`}>
          <img src={`/media/thumb/${vid}?t=${m.peak.toFixed(1)}`} alt="" loading="lazy" />
          <span className="play"><Play size={20} weight="fill" aria-hidden /></span>
        </button>
        <div style={{ minWidth: 0 }}>
          <div className="moment-top">
            <div style={{ minWidth: 0 }}>
              <div className="moment-title ellipsis">{m.title}</div>
              <div className="moment-time">#{m.id} · {fmtTime(m.start)} → {fmtTime(m.end)} · {Math.round(m.end - m.start)} s</div>
            </div>
            <ScoreRing score={m.score} />
          </div>
          <div className="moment-tags">
            {kinds.slice(0, 4).map(e => <EventChip key={e.type} type={e.type} label={e.type === 'keyword' && e.text ? `« ${e.text} »` : e.label} />)}
            {kinds.length > 4 && <span className="chip" title={kinds.slice(4).map(e => e.label).join(', ')}>+{kinds.length - 4}</span>}
            {m.manual && <span className="chip">Manuel</span>}
            {rendered && <span className="chip" style={{ color: 'var(--success)' }}><CheckCircle size={13} weight="fill" aria-hidden />Rendu</span>}
          </div>
        </div>
      </div>
      <div className="moment-edit">
        <div className="hook-field">
          <Quotes size={14} weight="fill" aria-hidden />
          <input className="input" value={hook} aria-label={`Texte d'accroche du moment ${m.id}`} title="Accroche affichée en haut du clip"
            onChange={e => setHook(e.target.value)} onBlur={saveHook} onKeyDown={e => e.key === 'Enter' && (e.target as HTMLInputElement).blur()} />
        </div>
        <div className="moment-actions">
          <div className="nudge" role="group" aria-label="Début du clip">
            <button onClick={() => onPatch({ start: Math.max(0, m.start - 2) })} aria-label="Début 2 secondes plus tôt">−2</button>
            <span>début</span>
            <button onClick={() => onPatch({ start: Math.min(m.end - 3, m.start + 2) })} aria-label="Début 2 secondes plus tard">+2</button>
          </div>
          <div className="nudge" role="group" aria-label="Fin du clip">
            <button onClick={() => onPatch({ end: Math.max(m.start + 3, m.end - 2) })} aria-label="Fin 2 secondes plus tôt">−2</button>
            <span>fin</span>
            <button onClick={() => onPatch({ end: m.end + 2 })} aria-label="Fin 2 secondes plus tard">+2</button>
          </div>
          <span className="grow" />
          <button className="btn sm icon ghost" onClick={() => onPatch({ excluded: !m.excluded })}
            aria-label={m.excluded ? 'Inclure dans le rendu' : 'Exclure du rendu'} title={m.excluded ? 'Inclure dans le rendu' : 'Exclure du rendu'}>
            {m.excluded ? <EyeSlash size={16} /> : <Eye size={16} />}
          </button>
          <button className="btn sm primary" disabled={disabled} onClick={onRender}>
            <Sparkle size={14} weight="fill" aria-hidden /> {rendered ? 'Re-rendre' : 'Rendre'}
          </button>
        </div>
      </div>
    </div>
  )
}

function Subtitles({ analysis, time, onSeek, onEdit }: {
  analysis: Analysis; time: number; onSeek: (t: number) => void; onEdit: (s: number, w: number, text: string) => void
}) {
  const [editing, setEditing] = useState<[number, number] | null>(null)
  const [draft, setDraft] = useState('')
  const current = analysis.segments.findIndex(s => time >= s.start && time < s.end + 0.3)
  const segRefs = useRef<(HTMLDivElement | null)[]>([])
  useEffect(() => {
    if (current >= 0 && !editing) segRefs.current[current]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [current, editing])
  const lowCount = analysis.segments.reduce((n, s) => n + s.words.filter(w => w.prob < 0.5).length, 0)

  if (analysis.segments.length === 0) return <p className="faint" style={{ padding: 8 }}>Aucune parole détectée dans cette vidéo.</p>
  return (
    <>
      <div className="subs-legend">
        <span>Clique un mot pour le corriger</span>
        {lowCount > 0 && <span><span className="low-sample">{lowCount} mots</span> à vérifier</span>}
      </div>
      <div className="subs">
        {analysis.segments.map((seg, si) => (
          <div key={si} ref={el => { segRefs.current[si] = el }} className={`seg ${si === current ? 'current' : ''}`}>
            <button className="seg-time" onClick={() => onSeek(seg.start)} aria-label={`Aller à ${fmtTime(seg.start)}`}>{fmtTime(seg.start)}</button>
            <div>
              {seg.words.map((w, wi) => editing?.[0] === si && editing?.[1] === wi ? (
                <input key={wi} className="input w-input" autoFocus value={draft} aria-label="Corriger le mot"
                  onChange={e => setDraft(e.target.value)} onBlur={() => setEditing(null)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') { if (draft.trim() && draft !== w.word) onEdit(si, wi, draft.trim()); setEditing(null) }
                    if (e.key === 'Escape') setEditing(null)
                  }} />
              ) : (
                <button key={wi} className={`w ${w.prob < 0.5 ? 'low' : ''} ${time >= w.start && time < w.end ? 'now' : ''} ${GLUE.test(w.word) || /['’-]$/.test(seg.words[wi - 1]?.word ?? '') ? 'glue' : ''}`}
                  title={`${fmtTime(w.start)} · confiance ${Math.round(w.prob * 100)} %`}
                  onClick={() => { setEditing([si, wi]); setDraft(w.word) }}>{w.word}</button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </>
  )
}
