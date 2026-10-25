import { Pause, Play, X } from '@phosphor-icons/react'
import { useState } from 'react'
import { api, STAGE_LABEL, type QueueState, type Video } from './api'
import { useToast } from './ui'

const KIND = { analyze: 'Analyse', render: 'Rendu' } as Record<string, string>

/** File de tâches dans la barre latérale : pause, retrait d'une vidéo, annulation, vider la file. */
export default function QueuePanel({ queue, videos, onChange }: { queue: QueueState | null; videos: Video[]; onChange: () => void }) {
  const [expanded, setExpanded] = useState(false)
  const toast = useToast()
  const byId = new Map(videos.map(v => [v.id, v]))
  if (!queue) return null
  const running = queue.running ? byId.get(queue.running.vid) : undefined
  const pending = queue.pending.filter(p => byId.has(p.vid))
  const shown = expanded ? pending : pending.slice(0, 4)

  const act = async (fn: () => Promise<unknown>, msg: string) => {
    try { await fn(); toast(msg, 'success'); onChange() } catch (e) { toast((e as Error).message, 'error') }
  }

  const status = queue.paused ? 'En pause' : running ? 'Au travail' : pending.length ? 'En attente' : 'Surveillance OBS active'
  return (
    <div className="queue" aria-live="polite">
      <div className="queue-title">
        <span className={`live-dot ${queue.paused ? 'paused' : running ? 'on' : 'ok'}`} aria-hidden />
        <span className="grow">{status}</span>
        {(running || pending.length > 0 || queue.paused) && (
          <button className="btn sm icon ghost" onClick={() => act(() => api.pauseQueue(!queue.paused), queue.paused ? 'File relancée' : 'File en pause : le travail en cours se termine, rien d\'autre ne démarre')}
            aria-label={queue.paused ? 'Reprendre la file' : 'Mettre la file en pause'} title={queue.paused ? 'Reprendre' : 'Pause'}>
            {queue.paused ? <Play size={14} weight="fill" /> : <Pause size={14} weight="fill" />}
          </button>
        )}
      </div>

      {running && queue.running && (
        <div className="queue-item">
          <div className="row" style={{ gap: 4 }}>
            <div className="ellipsis grow" title={running.name}>{running.name}</div>
            <button className="queue-x" onClick={() => act(() => api.unqueue(running.id), `${KIND[queue.running!.kind]} de ${running.name} annulé`)}
              aria-label={`Annuler ${running.name}`} title="Annuler"><X size={12} weight="bold" /></button>
          </div>
          <div className="row faint" style={{ justifyContent: 'space-between', margin: '2px 0 5px' }}>
            <span>{running.stage ? STAGE_LABEL[running.stage] ?? running.stage : KIND[queue.running.kind]}</span>
            <span className="mono">{Math.round(running.progress * 100)} %</span>
          </div>
          <div className="progress"><div style={{ width: `${running.progress * 100}%` }} /></div>
        </div>
      )}

      {pending.length > 0 && (
        <ul className="queue-list">
          {shown.map(p => {
            const v = byId.get(p.vid)!
            return (
              <li key={`${p.vid}-${p.kind}`}>
                <span className="faint queue-kind">{KIND[p.kind]}</span>
                <span className="ellipsis grow" title={v.name}>{v.name}</span>
                <button className="queue-x" onClick={() => act(() => api.unqueue(p.vid), `${v.name} retiré de la file`)}
                  aria-label={`Retirer ${v.name} de la file`} title="Retirer de la file"><X size={12} weight="bold" /></button>
              </li>
            )
          })}
        </ul>
      )}
      {pending.length > 4 && (
        <button className="queue-link" onClick={() => setExpanded(!expanded)}>{expanded ? 'Réduire' : `+ ${pending.length - 4} autres`}</button>
      )}
      {pending.length > 1 && (
        <button className="queue-link danger" onClick={() => act(() => api.clearQueue(), 'File d\'attente vidée')}>Vider la file d'attente</button>
      )}
      {!running && !pending.length && !queue.paused && (
        <div className="faint" style={{ marginTop: 4 }}>Chaque enregistrement de plus de quelques minutes est analysé tout seul.</div>
      )}
    </div>
  )
}
