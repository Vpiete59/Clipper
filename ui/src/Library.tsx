import {
  ArrowRight, CheckCircle, Clock, DeviceMobile, FilmStrip, Lightning, MagnifyingGlass, Play, Plus,
  Sparkle, Tray, VideoCamera, Warning,
} from '@phosphor-icons/react'
import { useEffect, useMemo, useState } from 'react'
import { BUSY } from './App'
import { api, fmtSize, fmtTime, STAGE_LABEL, STATUS_LABEL, type Game, type InboxFile, type Video } from './api'
import { Spinner, useToast } from './ui'

type Filter = 'all' | 'busy' | 'done'

export default function Library({ videos, games, onOpen }: { videos: Video[] | null; games: Game[]; onOpen: (id: string) => void }) {
  const [inbox, setInbox] = useState<InboxFile[]>([])
  const [path, setPath] = useState('')
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [importing, setImporting] = useState<string | null>(null)
  const toast = useToast()
  const list = useMemo(() => videos ?? [], [videos])

  const loadInbox = () => api.inbox().then(setInbox).catch(() => {})
  useEffect(() => { loadInbox() }, [list.length])

  const gameName = (id: string) => games.find(g => g.id === id)?.name ?? id

  const importPath = async (p: string, game?: string) => {
    const clean = p.trim().replace(/^"|"$/g, '')
    setImporting(clean)
    try {
      await api.importVideo(clean, game)
      setPath('')
      toast('Vidéo ajoutée : l\'analyse démarre', 'success')
      loadInbox()
    } catch (e) {
      toast((e as Error).message, 'error')
    } finally {
      setImporting(null)
    }
  }

  const shown = list.filter(v =>
    v.name.toLowerCase().includes(query.toLowerCase()) &&
    (filter === 'all' || (filter === 'busy' ? BUSY.includes(v.status) : v.status === 'done')))

  const totalMoments = list.reduce((s, v) => s + v.n_moments, 0)
  const busyCount = list.filter(v => BUSY.includes(v.status)).length
  const doneCount = list.filter(v => v.status === 'done').length

  return (
    <div className="page">
      <div className="page-head">
        <div className="grow">
          <div className="eyebrow">Tes enregistrements</div>
          <h1 className="page-title">Bibliothèque</h1>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <input className="input" style={{ width: 360 }} placeholder="Coller le chemin d'une vidéo (.mkv, .mp4)…"
            aria-label="Chemin d'une vidéo à analyser" value={path} onChange={e => setPath(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && path && importPath(path)} />
          <button className="btn primary" disabled={!path || !!importing} onClick={() => importPath(path)}>
            {importing === path.trim() ? <Spinner /> : <Plus size={16} weight="bold" aria-hidden />} Analyser
          </button>
        </div>
      </div>

      <div className="stats">
        <Stat icon={<FilmStrip size={20} aria-hidden />} value={list.length} label="Vidéos" />
        <Stat icon={<Lightning size={20} weight="fill" aria-hidden />} value={totalMoments} label="Moments forts détectés" accent />
        <Stat icon={<CheckCircle size={20} aria-hidden />} value={doneCount} label="Prêtes à publier" />
        <Stat icon={busyCount ? <Spinner size={20} /> : <Clock size={20} aria-hidden />} value={busyCount} label="En cours de traitement" />
      </div>

      {videos === null ? (
        <div className="grid">{[0, 1, 2].map(i => <div key={i} className="skeleton" style={{ height: 270 }} />)}</div>
      ) : list.length === 0 ? (
        <div className="card empty">
          <div className="empty-icon"><VideoCamera size={30} weight="duotone" aria-hidden /></div>
          <h2>Prêt à clipper</h2>
          <p>Lance une partie et enregistre-la avec OBS. Dès que l'enregistrement s'arrête, Clipper trouve tes meilleurs moments et prépare les clips.</p>
          <div className="steps">
            <div className="step-chip"><b>1</b> Enregistre dans OBS</div>
            <div className="step-chip"><b>2</b> Clipper analyse</div>
            <div className="step-chip"><b>3</b> Récupère tes clips 9:16</div>
          </div>
        </div>
      ) : (
        <>
          <div className="toolbar">
            <div className="segmented" role="tablist" aria-label="Filtrer">
              {([['all', 'Toutes'], ['busy', 'En cours'], ['done', 'Terminées']] as [Filter, string][]).map(([k, l]) => (
                <button key={k} role="tab" aria-selected={filter === k} onClick={() => setFilter(k)}>{l}</button>
              ))}
            </div>
            <div className="grow" />
            <div className="search">
              <MagnifyingGlass size={15} aria-hidden />
              <input className="input" placeholder="Rechercher…" aria-label="Rechercher une vidéo" value={query} onChange={e => setQuery(e.target.value)} />
            </div>
          </div>
          {shown.length === 0 ? (
            <div className="card empty"><p>Aucune vidéo ne correspond.</p></div>
          ) : (
            <div className="grid">
              {shown.map((v, i) => <VideoCard key={v.id} v={v} index={i} game={gameName(v.game)} onOpen={() => onOpen(v.id)} />)}
            </div>
          )}
        </>
      )}

      {inbox.length > 0 && (
        <section className="inbox" aria-labelledby="inbox-title">
          <div className="page-head" style={{ marginBottom: 12, alignItems: 'center' }}>
            <Tray size={22} className="faint" aria-hidden />
            <h2 id="inbox-title" className="section-title">Dans tes dossiers OBS</h2>
            <span className="faint">{inbox.length} enregistrement{inbox.length > 1 ? 's' : ''} pas encore analysé{inbox.length > 1 ? 's' : ''}</span>
          </div>
          <div className="card inbox-list">
            {inbox.slice(0, 12).map(f => <InboxRow key={f.path} f={f} games={games} busy={importing === f.path} onImport={g => importPath(f.path, g)} />)}
          </div>
        </section>
      )}
    </div>
  )
}

function Stat({ icon, value, label, accent }: { icon: React.ReactNode; value: number; label: string; accent?: boolean }) {
  return (
    <div className="card stat">
      <div className={`stat-icon ${accent ? 'accent' : ''}`}>{icon}</div>
      <div><div className="stat-value">{value}</div><div className="stat-label">{label}</div></div>
    </div>
  )
}

function VideoCard({ v, index, game, onOpen }: { v: Video; index: number; game: string; onOpen: () => void }) {
  const [thumbOk, setThumbOk] = useState(true)
  const busy = BUSY.includes(v.status)
  const portrait = v.orientation === 'portrait'
  const thumb = `/media/thumb/${v.id}?m=${v.n_moments}`

  return (
    <button className="card vcard" onClick={onOpen} style={{ animationDelay: `${Math.min(index, 10) * 40}ms` }}
      aria-label={`${v.name}, ${STATUS_LABEL[v.status] ?? v.status}`}>
      <div className="thumb">
        {thumbOk ? (
          <>
            {portrait && <div className="thumb-bg" style={{ backgroundImage: `url(${thumb})` }} />}
            <img src={thumb} alt="" loading="lazy" className={portrait ? 'portrait' : ''} onError={() => setThumbOk(false)} />
          </>
        ) : <div className="thumb-fallback"><FilmStrip size={34} aria-hidden /></div>}
        <div className="thumb-tl">
          {v.status === 'done' && <span className="pill-dark"><CheckCircle size={13} weight="fill" color="#3dd68c" aria-hidden /> Clips prêts</span>}
          {v.status === 'error' && <span className="pill-dark"><Warning size={13} weight="fill" color="#f2555a" aria-hidden /> Erreur</span>}
          {v.status === 'analyzed' && <span className="pill-dark"><Sparkle size={13} weight="fill" color="#ffb938" aria-hidden /> Analysée</span>}
        </div>
        {v.best_score > 0 && <div className="thumb-bl"><span className="score-pill"><Lightning size={13} weight="fill" aria-hidden />{Math.round(v.best_score)}</span></div>}
        {v.duration && <div className="thumb-br"><span className="pill-dark mono">{portrait && <DeviceMobile size={12} aria-hidden />}{fmtTime(v.duration)}</span></div>}
        {busy && (
          <div className="busy-overlay">
            <Spinner size={22} />
            <strong>{v.stage ? STAGE_LABEL[v.stage] ?? v.stage : STATUS_LABEL[v.status]}</strong>
            <div className="progress"><div style={{ width: `${v.progress * 100}%` }} /></div>
            <span className="mono faint">{Math.round(v.progress * 100)} %</span>
          </div>
        )}
      </div>
      <div className="vcard-body">
        <div className="vcard-title ellipsis" title={v.name}>{v.name}</div>
        <div className="vcard-meta">
          <span>{game}</span><span className="sep" /><span>{fmtSize(v.size)}</span><span className="sep" />
          <span>{new Date(v.added_at * 1000).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })}</span>
        </div>
        <div className="vcard-foot">
          {v.n_moments > 0
            ? <span className="chip" style={{ color: 'var(--accent)' }}><Lightning size={13} weight="fill" aria-hidden />{v.n_moments} moment{v.n_moments > 1 ? 's' : ''} fort{v.n_moments > 1 ? 's' : ''}</span>
            : <span className="faint" style={{ fontSize: 12 }}>{busy ? 'Recherche des moments forts…' : v.status === 'new' ? 'Pas encore analysée' : 'Aucun moment au-dessus du seuil'}</span>}
          <span className="grow" />
          <span className="faint row" style={{ fontSize: 12, gap: 4 }}>Ouvrir <ArrowRight size={13} aria-hidden /></span>
        </div>
      </div>
    </button>
  )
}

function InboxRow({ f, games, busy, onImport }: { f: InboxFile; games: Game[]; busy: boolean; onImport: (game: string) => void }) {
  // la liste des jeux arrive après le premier rendu : on ne fige pas le défaut dans l'état
  const [picked, setGame] = useState<string | null>(null)
  const game = picked ?? games.find(g => g.id === 'hunt_showdown')?.id ?? games[0]?.id ?? 'generic'
  return (
    <div className="inbox-row">
      <div className="inbox-icon"><Play size={15} weight="fill" aria-hidden /></div>
      <div className="ellipsis" title={f.path} style={{ fontWeight: 550 }}>{f.name}</div>
      <div className="faint mono">{fmtSize(f.size)}</div>
      <div className="faint">{new Date(f.mtime * 1000).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })}</div>
      <div className="inbox-actions">
        <select className="select" aria-label={`Jeu pour ${f.name}`} value={game} onChange={e => setGame(e.target.value)} style={{ width: 120 }}>
          {games.map(g => <option key={g.id} value={g.id}>{g.name.replace(' (tous jeux)', '')}</option>)}
        </select>
        <button className="btn sm" disabled={busy} onClick={() => onImport(game)}>
          {busy ? <Spinner /> : <Sparkle size={14} weight="fill" aria-hidden />} Analyser
        </button>
      </div>
    </div>
  )
}
