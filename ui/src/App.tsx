import { FilmStrip, GearSix, Scissors } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import { api, STAGE_LABEL, type Game, type Video } from './api'
import Library from './Library'
import SettingsPage from './SettingsPage'
import VideoView from './VideoView'

type Route = { page: 'library' } | { page: 'video'; id: string } | { page: 'settings' }
export const BUSY = ['queued', 'analyzing', 'rendering', 'rendering_queued']

export default function App() {
  const [route, setRoute] = useState<Route>({ page: 'library' })
  const [videos, setVideos] = useState<Video[] | null>(null)
  const [games, setGames] = useState<Game[]>([])

  useEffect(() => {
    api.games().then(setGames)
    const load = () => api.videos().then(setVideos).catch(() => {})
    load()
    const timer = setInterval(load, 1500)
    return () => clearInterval(timer)
  }, [])

  // le contenu principal défile, on remonte en haut à chaque changement d'écran
  useEffect(() => { document.querySelector('.main')?.scrollTo({ top: 0 }) }, [route])

  const list = videos ?? []
  const running = list.filter(v => ['analyzing', 'rendering'].includes(v.status))
  const waiting = list.filter(v => ['queued', 'rendering_queued'].includes(v.status)).length

  return (
    <div className="app">
      <aside className="sidebar" aria-label="Navigation">
        <div className="brand">
          <div className="brand-mark"><Scissors size={19} weight="bold" aria-hidden /></div>
          <div>
            <div className="brand-name">Clipper</div>
            <div className="brand-sub">Moments forts automatiques</div>
          </div>
        </div>
        <button className="nav" aria-current={route.page !== 'settings' ? 'page' : undefined} onClick={() => setRoute({ page: 'library' })}>
          <FilmStrip size={19} aria-hidden /> Bibliothèque <span className="count">{list.length}</span>
        </button>
        <button className="nav" aria-current={route.page === 'settings' ? 'page' : undefined} onClick={() => setRoute({ page: 'settings' })}>
          <GearSix size={19} aria-hidden /> Réglages
        </button>

        <div className="queue" aria-live="polite">
          <div className="queue-title">
            <span className={`live-dot ${running.length ? 'on' : 'ok'}`} aria-hidden />
            {running.length ? 'Au travail' : 'Surveillance OBS active'}
          </div>
          {running.map(v => (
            <div key={v.id} className="queue-item">
              <div className="ellipsis" title={v.name}>{v.name}</div>
              <div className="row faint" style={{ justifyContent: 'space-between', margin: '2px 0 5px' }}>
                <span>{v.stage ? STAGE_LABEL[v.stage] ?? v.stage : 'Préparation'}</span>
                <span className="mono">{Math.round(v.progress * 100)} %</span>
              </div>
              <div className="progress"><div style={{ width: `${v.progress * 100}%` }} /></div>
            </div>
          ))}
          {waiting > 0 && <div className="faint" style={{ marginTop: 8 }}>+ {waiting} en attente</div>}
          {!running.length && !waiting && <div className="faint" style={{ marginTop: 4 }}>Chaque enregistrement terminé est analysé tout seul.</div>}
        </div>
      </aside>

      <main className="main">
        {route.page === 'library' && (
          <Library videos={videos} games={games} onOpen={id => setRoute({ page: 'video', id })} />
        )}
        {route.page === 'video' && (
          <VideoView key={route.id} id={route.id} games={games} summary={list.find(v => v.id === route.id)}
            onBack={() => setRoute({ page: 'library' })} />
        )}
        {route.page === 'settings' && <SettingsPage games={games} />}
      </main>
    </div>
  )
}
