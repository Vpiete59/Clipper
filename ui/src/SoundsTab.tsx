import { Ear, Plus, ThumbsDown, ThumbsUp, Trash, Play } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import { api, fmtTime, type Analysis, type Game, type SoundExample } from './api'
import { Spinner, useToast } from './ui'

type Props = {
  vid: string; game: Game | undefined; analysis: Analysis; time: number
  onSeek: (t: number, until?: number) => void; onChanged: () => void
}

/** Apprentissage par l'exemple : on confirme ou on rejette les sons détectés, et la détection s'affine. */
export default function SoundsTab({ vid, game, analysis, time, onSeek, onChanged }: Props) {
  const [examples, setExamples] = useState<SoundExample[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const toast = useToast()
  const load = () => game && api.sounds(game.id).then(setExamples)
  useEffect(() => { load() }, [game?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!game || !Object.keys(game.learned_sounds ?? {}).length) {
    return <p className="faint" style={{ padding: 8 }}>Ce profil de jeu n'a pas de son à apprendre.</p>
  }

  const teach = async (kind: string, t: number, negative: boolean, snap = false) => {
    setBusy(`${kind}-${t}-${negative}`)
    try {
      const r = await api.teachSound(vid, kind, t, negative, snap)
      toast(negative ? 'Contre-exemple ajouté : les sons de ce genre seront ignorés' : `Exemple ajouté à ${fmtTime(r.t)} : la détection s'affine`, 'success')
      await load()
      onChanged()
    } catch (e) {
      toast((e as Error).message, 'error')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="sounds">
      {Object.entries(game.learned_sounds).map(([kind, spec]) => {
        const mine = examples.filter(x => x.kind === kind)
        const pos = mine.filter(x => !x.negative).length
        const neg = mine.length - pos
        const found = analysis.events.filter(e => e.type === spec.event)
        const judged = (t: number) => mine.find(x => x.video_id === vid && Math.abs(x.t - t) < 1.5)
        return (
          <section key={kind} className="sound-kind">
            <div className="sound-head">
              <div className="sset-icon" aria-hidden><Ear size={18} weight="fill" /></div>
              <div className="grow">
                <div className="moment-title">{spec.label}</div>
                <div className="faint" style={{ fontSize: 12 }}>{spec.hint}</div>
              </div>
            </div>
            <div className="sound-stats">
              <span><b>{pos}</b> exemple{pos > 1 ? 's' : ''}</span>
              <span><b>{neg}</b> contre-exemple{neg > 1 ? 's' : ''}</span>
              <span><b>{found.length}</b> détecté{found.length > 1 ? 's' : ''} ici</span>
            </div>
            <p className="sound-help">
              Écoute chaque détection : <ThumbsUp size={13} weight="fill" aria-hidden /> si c'est bien un {spec.label.toLowerCase()},
              {' '}<ThumbsDown size={13} weight="fill" aria-hidden /> sinon (chien, explosion…). Une dizaine de réponses suffit pour que la détection devienne fiable sur toutes tes parties.
            </p>
            <button className="btn sm" style={{ width: '100%' }} disabled={!!busy} onClick={() => teach(kind, time, false, true)}>
              {busy?.startsWith(`${kind}-${time}`) ? <Spinner /> : <Plus size={14} weight="bold" aria-hidden />}
              C'est un {spec.label.toLowerCase()} ici ({fmtTime(time)})
            </button>
            <div className="sound-list">
              {found.length === 0 && <p className="faint" style={{ fontSize: 13, padding: '8px 4px' }}>Aucun détecté dans cette vidéo. Place la lecture juste après un cri et clique le bouton ci-dessus.</p>}
              {found.map(e => {
                const verdict = judged(e.t)
                const key = (n: boolean) => `${kind}-${e.t}-${n}`
                return (
                  <div key={e.t} className={`sound-row ${verdict ? (verdict.negative ? 'rejected' : 'confirmed') : ''}`}>
                    <button className="btn sm icon" onClick={() => onSeek(e.t - 3, e.t + 2)} aria-label={`Écouter à ${fmtTime(e.t)}`}><Play size={13} weight="fill" /></button>
                    <span className="mono">{fmtTime(e.t)}</span>
                    <span className="faint" style={{ fontSize: 12 }}>{Math.round(e.strength * 100)} %</span>
                    <span className="grow" />
                    {verdict ? (
                      <>
                        <span className="faint" style={{ fontSize: 12 }}>{verdict.negative ? 'Rejeté' : 'Confirmé'}</span>
                        <button className="btn sm icon ghost" aria-label="Annuler ma réponse" title="Annuler ma réponse"
                          onClick={async () => { await api.forgetSound(verdict.id); await load(); onChanged() }}><Trash size={14} /></button>
                      </>
                    ) : (
                      <>
                        <button className="btn sm icon" disabled={!!busy} onClick={() => teach(kind, e.t, false)} aria-label="Oui, c'est ce son" title="Oui, c'est ce son">
                          {busy === key(false) ? <Spinner /> : <ThumbsUp size={14} weight="fill" color="var(--success)" />}
                        </button>
                        <button className="btn sm icon" disabled={!!busy} onClick={() => teach(kind, e.t, true)} aria-label="Non, ce n'est pas ce son" title="Non, ce n'est pas ce son">
                          {busy === key(true) ? <Spinner /> : <ThumbsDown size={14} weight="fill" color="var(--danger)" />}
                        </button>
                      </>
                    )}
                  </div>
                )
              })}
            </div>
          </section>
        )
      })}
    </div>
  )
}
