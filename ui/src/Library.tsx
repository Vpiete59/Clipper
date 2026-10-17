import { useEffect, useState } from 'react'
import { api, fmtSize, fmtTime, STAGE_LABEL, STATUS_LABEL, type Game, type InboxFile, type Video } from './api'

const BUSY = ['queued', 'analyzing', 'rendering', 'rendering_queued']

export default function Library({ videos, games, onOpen }: { videos: Video[]; games: Game[]; onOpen: (id: string) => void }) {
  const [inbox, setInbox] = useState<InboxFile[]>([])
  const [path, setPath] = useState('')
  const [error, setError] = useState('')

  const loadInbox = () => api.inbox().then(setInbox).catch(() => {})
  useEffect(() => { loadInbox() }, [videos.length])

  const gameName = (id: string) => games.find(g => g.id === id)?.name ?? id

  const importPath = async (p: string) => {
    setError('')
    try {
      await api.importVideo(p.trim().replace(/^"|"$/g, ''))
      setPath('')
      loadInbox()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <h1>Bibliothèque</h1>
        <div className="spacer" />
        <input type="text" placeholder="Coller le chemin d'une vidéo…" value={path} onChange={e => setPath(e.target.value)}
          style={{ width: 380 }} onKeyDown={e => e.key === 'Enter' && path && importPath(path)} />
        <button className="btn primary" disabled={!path} onClick={() => importPath(path)}>Analyser</button>
      </div>
      {error && <p style={{ color: 'var(--danger)' }}>{error}</p>}

      {videos.length === 0 ? (
        <div className="card empty">
          Aucune vidéo pour l'instant.<br />
          Lance un enregistrement dans OBS : dès qu'il est terminé, Clipper l'analyse tout seul.<br />
          Tu peux aussi choisir un enregistrement existant ci-dessous.
        </div>
      ) : (
        <div className="video-list">
          {videos.map(v => (
            <div key={v.id} className="card video-row" onClick={() => onOpen(v.id)}>
              <div style={{ minWidth: 0 }}>
                <div className="video-name">{v.name}</div>
                <div className="video-meta">
                  {v.duration ? fmtTime(v.duration) : '—'} · {fmtSize(v.size)}
                  {v.orientation === 'portrait' ? ' · vertical' : v.orientation ? ' · 16:9' : ''}
                </div>
              </div>
              <div className="muted">{gameName(v.game)}</div>
              <div>
                {v.n_moments > 0 && <><span className="score">{v.n_moments}</span> <span className="muted">moments</span></>}
              </div>
              <div>
                <span className={`pill ${v.status === 'done' ? 'done' : v.status === 'error' ? 'error' : BUSY.includes(v.status) ? 'busy' : ''}`}>
                  {v.stage && BUSY.includes(v.status) ? STAGE_LABEL[v.stage] ?? v.stage : STATUS_LABEL[v.status] ?? v.status}
                </span>
                {BUSY.includes(v.status) && (
                  <div className="progress"><div style={{ width: `${Math.round(v.progress * 100)}%` }} /></div>
                )}
              </div>
              <div className="muted">›</div>
            </div>
          ))}
        </div>
      )}

      {inbox.length > 0 && (
        <div className="inbox">
          <div className="page-head" style={{ marginBottom: 10 }}>
            <h2>Dans tes dossiers OBS</h2>
            <span className="muted">pas encore analysés</span>
          </div>
          <div className="card">
            {inbox.slice(0, 15).map(f => (
              <div key={f.path} className="inbox-row">
                <div className="video-name" title={f.path}>{f.name}</div>
                <div className="muted">{fmtSize(f.size)}</div>
                <div className="muted">{new Date(f.mtime * 1000).toLocaleDateString('fr-FR')}</div>
                <button className="btn small" onClick={() => importPath(f.path)}>Analyser</button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
