import { useEffect, useState } from 'react'
import { api, type Game, type Video } from './api'
import Library from './Library'
import SettingsPage from './SettingsPage'
import VideoView from './VideoView'

type Route = { page: 'library' } | { page: 'video'; id: string } | { page: 'settings' }

export default function App() {
  const [route, setRoute] = useState<Route>({ page: 'library' })
  const [videos, setVideos] = useState<Video[]>([])
  const [games, setGames] = useState<Game[]>([])

  useEffect(() => {
    api.games().then(setGames)
    const load = () => api.videos().then(setVideos).catch(() => {})
    load()
    const timer = setInterval(load, 1500)
    return () => clearInterval(timer)
  }, [])

  const busy = videos.filter(v => ['queued', 'analyzing', 'rendering', 'rendering_queued'].includes(v.status)).length

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark">✂</div>Clipper</div>
        <button className={`nav ${route.page !== 'settings' ? 'active' : ''}`} onClick={() => setRoute({ page: 'library' })}>
          Bibliothèque <span className="count">{videos.length}</span>
        </button>
        <button className={`nav ${route.page === 'settings' ? 'active' : ''}`} onClick={() => setRoute({ page: 'settings' })}>
          Réglages
        </button>
        <div className="sidebar-foot">
          {busy > 0 ? <span style={{ color: 'var(--accent)' }}>● {busy} tâche{busy > 1 ? 's' : ''} en cours</span> : '● Inactif'}
          <br />Surveillance OBS active
        </div>
      </aside>
      <main className="main">
        {route.page === 'library' && (
          <Library videos={videos} games={games} onOpen={id => setRoute({ page: 'video', id })} />
        )}
        {route.page === 'video' && (
          <VideoView
            id={route.id}
            games={games}
            summary={videos.find(v => v.id === route.id)}
            onBack={() => setRoute({ page: 'library' })}
          />
        )}
        {route.page === 'settings' && <SettingsPage games={games} />}
      </main>
    </div>
  )
}
