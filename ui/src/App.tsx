import { FilmStrip, GearSix, Scissors } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import { api, type Game, type QueueState, type Video } from './api'
import QueuePanel from './QueuePanel'
import Library from './Library'
import SettingsPage from './SettingsPage'
import VideoView from './VideoView'

type Route = { page: 'library' } | { page: 'video'; id: string } | { page: 'settings' }
export const BUSY = ['queued', 'analyzing', 'rendering', 'rendering_queued']

export default function App() {
  const [route, setRoute] = useState<Route>({ page: 'library' })
  const [videos, setVideos] = useState<Video[] | null>(null)
  const [games, setGames] = useState<Game[]>([])

  const [queue, setQueue] = useState<QueueState | null>(null)
  const refresh = () => {
    api.videos().then(setVideos).catch(() => {})
    api.queue().then(setQueue).catch(() => {})
  }
  useEffect(() => {
    api.games().then(setGames)
    refresh()
    const timer = setInterval(refresh, 1500)
    return () => clearInterval(timer)
  }, [])

  // le contenu principal défile, on remonte en haut à chaque changement d'écran
  useEffect(() => { document.querySelector('.main')?.scrollTo({ top: 0 }) }, [route])

  const list = videos ?? []

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

        <QueuePanel queue={queue} videos={list} onChange={refresh} />
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
