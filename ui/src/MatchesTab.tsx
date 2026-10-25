import { CheckCircle, FilmReel, Question, Skull, Sparkle, YoutubeLogo } from '@phosphor-icons/react'
import { fmtTime, type Analysis, type Render } from './api'
import { eventStyle, Spinner } from './ui'

const OUTCOME = {
  extracted: { label: 'Extraction réussie', icon: CheckCircle, color: 'var(--success)' },
  dead: { label: 'Mort au combat', icon: Skull, color: 'var(--danger)' },
  unknown: { label: 'Issue inconnue', icon: Question, color: 'var(--text-3)' },
}

type Props = {
  analysis: Analysis; renders: Render[]; busy: boolean
  onSeek: (t: number, until?: number) => void; onRender: (matchId: number) => void; onLongform: (matchId: number) => void
}

/** Une partie = début → fin, et le résumé qui la raconte en chapitres. */
export default function MatchesTab({ analysis, renders, busy, onSeek, onRender, onLongform }: Props) {
  const matches = analysis.matches ?? []
  if (!matches.length) {
    return (
      <div className="empty" style={{ padding: '32px 12px' }}>
        <p>Aucune partie reconnue dans cette vidéo.</p>
        <p className="faint" style={{ fontSize: 13 }}>Clipper repère une partie grâce à « La chasse est ouverte » et « Résumé de mission ». Relance l'analyse si la vidéo date d'avant cette fonction.</p>
      </div>
    )
  }
  return (
    <div className="matches">
      {matches.map(m => {
        const o = OUTCOME[m.outcome]
        const OI = o.icon
        const story = renders.find(r => r.kind === 'story' && r.moment_id === m.id)
        const youtube = renders.find(r => r.kind === 'longform' && r.moment_id === m.id)
        const length = m.chapters.reduce((s, c) => s + c.end - c.start, 0)
        return (
          <section key={m.id} className={`match ${m.worth ? '' : 'dim'}`}>
            <div className="match-head">
              <div className="grow">
                <div className="moment-title">Partie {m.id + 1}</div>
                <div className="moment-time">{fmtTime(m.start)} → {fmtTime(m.end)} · {Math.round((m.end - m.start) / 60)} min</div>
              </div>
              <span className="chip" style={{ color: o.color }}><OI size={13} weight="fill" aria-hidden />{o.label}</span>
              <span className="potential" title="Potentiel du résumé : victoire, kills, prime, boss">{m.potential}</span>
            </div>
            {!m.worth && <div className="faint" style={{ fontSize: 12 }}>Partie perdue sans kill : pas de résumé automatique (tu peux le lancer quand même).</div>}
            <div className="match-stats">
              <span><b>{m.clues}</b> indice{m.clues > 1 ? 's' : ''}</span>
              <span><b>{m.kills}</b> kill{m.kills > 1 ? 's' : ''}</span>
              <span><b>{m.bounty ? 'Oui' : 'Non'}</b> prime</span>
            </div>
            <ol className="chapters" aria-label={`Chapitres du résumé de la partie ${m.id + 1}`}>
              {m.chapters.map((c, i) => {
                const { color, icon: I } = eventStyle(c.type)
                return (
                  <li key={i}>
                    <button className="chapter" onClick={() => onSeek(c.start, c.end)}>
                      <i style={{ background: color }}><I size={11} weight="fill" aria-hidden /></i>
                      <span className="grow ellipsis">{c.label}</span>
                      <span className="mono faint">{fmtTime(c.t)}</span>
                    </button>
                  </li>
                )
              })}
            </ol>
            <div className="row">
              <span className="faint" style={{ fontSize: 12 }}>~{Math.round(length)} s avant accélérations</span>
              <span className="grow" />
              {story && <span className="chip" style={{ color: 'var(--success)' }}><FilmReel size={13} weight="fill" aria-hidden />Résumé prêt</span>}
              <button className="btn sm" disabled={busy} onClick={() => onLongform(m.id)} title="Vidéo 16:9 pour YouTube, avec chapitres, sous-titres .srt et miniature">
                <YoutubeLogo size={14} weight="fill" color="#ff3b3b" aria-hidden /> {youtube ? 'Refaire' : 'YouTube'}
              </button>
              <button className="btn sm primary" disabled={busy} onClick={() => onRender(m.id)}>
                {busy ? <Spinner /> : <Sparkle size={14} weight="fill" aria-hidden />} {story ? 'Re-rendre' : 'Short'}
              </button>
            </div>
          </section>
        )
      })}
    </div>
  )
}
