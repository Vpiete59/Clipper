import { useEffect, useState } from 'react'
import { api, type Game, type Settings } from './api'

const EFFECTS: [string, string][] = [
  ['punch_zoom', 'Zoom punch sur l\'action'],
  ['slowmo', 'Ralenti sur les fusillades et morts'],
  ['shake', 'Tremblement de caméra'],
  ['flash', 'Flash blanc'],
  ['hook_title', 'Bandeau d\'accroche (2,8 s)'],
  ['progress_bar', 'Barre de progression'],
]

export default function SettingsPage({ games }: { games: Game[] }) {
  const [s, setS] = useState<Settings | null>(null)
  const [saved, setSaved] = useState(false)
  useEffect(() => { api.settings().then(setS) }, [])
  if (!s) return <div className="page muted">Chargement…</div>

  const save = async (patch: Partial<Settings>) => {
    setS(await api.saveSettings(patch))
    setSaved(true)
    setTimeout(() => setSaved(false), 1500)
  }
  const num = (k: keyof Settings) => (e: React.ChangeEvent<HTMLInputElement>) => save({ [k]: Number(e.target.value) } as Partial<Settings>)

  return (
    <div className="page">
      <div className="page-head"><h1>Réglages</h1>{saved && <span className="muted">Enregistré ✓</span>}</div>
      <div className="settings">
        <div className="card">
          <h2 style={{ marginBottom: 16 }}>Enregistrements</h2>
          <div className="field">
            <label>Dossiers surveillés</label>
            {s.watch_folders.map((f, i) => (
              <div key={i} className="folder-row">
                <input type="text" defaultValue={f} onBlur={e => {
                  const next = [...s.watch_folders]; next[i] = e.target.value; save({ watch_folders: next.filter(Boolean) })
                }} />
                <button className="btn small danger" onClick={() => save({ watch_folders: s.watch_folders.filter((_, j) => j !== i) })}>✕</button>
              </div>
            ))}
            <button className="btn small" style={{ alignSelf: 'flex-start' }} onClick={() => save({ watch_folders: [...s.watch_folders, ''] })}>+ Ajouter un dossier</button>
            <span className="hint">Détectés depuis ta config OBS (enregistrement + plugin Vertical Canvas).</span>
          </div>
          <label className="check"><input type="checkbox" checked={s.auto_process} onChange={e => save({ auto_process: e.target.checked })} />
            Analyser et rendre automatiquement chaque nouvel enregistrement</label>
          <div className="field">
            <label>Jeu par défaut</label>
            <select value={s.default_game} onChange={e => save({ default_game: e.target.value })}>
              {games.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Dossier de sortie des clips</label>
            <input type="text" defaultValue={s.output_folder} onBlur={e => save({ output_folder: e.target.value })} />
          </div>
        </div>

        <div className="card">
          <h2 style={{ marginBottom: 16 }}>Détection</h2>
          <div className="row">
            <div className="field grow"><label>Clips max par vidéo</label><input type="number" min={1} max={30} value={s.max_clips} onChange={num('max_clips')} /></div>
            <div className="field grow"><label>Score minimum</label><input type="number" min={0} step={1} value={s.min_score} onChange={num('min_score')} /></div>
          </div>
          <div className="row">
            <div className="field grow"><label>Durée min (s)</label><input type="number" min={3} value={s.clip_min_s} onChange={num('clip_min_s')} /></div>
            <div className="field grow"><label>Durée max (s)</label><input type="number" min={10} max={180} value={s.clip_max_s} onChange={num('clip_max_s')} /></div>
          </div>
          <div className="field">
            <label>Mots-clés perso (un par ligne)</label>
            <textarea rows={4} defaultValue={s.custom_keywords.join('\n')}
              onBlur={e => save({ custom_keywords: e.target.value.split('\n').map(x => x.trim()).filter(Boolean) })} />
            <span className="hint">Dis-les pendant ta partie (« clippe ça ») pour forcer un moment fort. Les réglages s'appliquent avec « Ré-analyser » ou au prochain enregistrement.</span>
          </div>
        </div>

        <div className="card">
          <h2 style={{ marginBottom: 16 }}>Sous-titres</h2>
          <div className="row">
            <div className="field grow">
              <label>Langue</label>
              <select value={s.language} onChange={e => save({ language: e.target.value })}>
                <option value="fr">Français</option><option value="en">Anglais</option><option value="auto">Détection auto</option>
              </select>
            </div>
            <div className="field grow">
              <label>Modèle Whisper</label>
              <select value={s.whisper_model} onChange={e => save({ whisper_model: e.target.value })}>
                <option value="large-v3">large-v3 (le plus précis)</option>
                <option value="large-v3-turbo">large-v3-turbo (rapide)</option>
                <option value="medium">medium</option>
              </select>
            </div>
          </div>
          <div className="row">
            <div className="field grow">
              <label>Style</label>
              <select value={s.subtitle_style} onChange={e => save({ subtitle_style: e.target.value })}>
                <option value="bold_pop">Bold pop (jaune)</option><option value="fire">Impact (orange)</option><option value="clean">Sobre</option>
              </select>
            </div>
          </div>
          <div className="row">
            <div className="field grow">
              <label>Hauteur, vidéos 16:9 ({Math.round(s.subtitle_y * 100)} %)</label>
              <input type="range" min={0.3} max={0.9} step={0.01} value={s.subtitle_y} onChange={e => save({ subtitle_y: Number(e.target.value) })} />
            </div>
            <div className="field grow">
              <label>Hauteur, vidéos verticales ({Math.round(s.subtitle_y_portrait * 100)} %)</label>
              <input type="range" min={0.2} max={0.9} step={0.01} value={s.subtitle_y_portrait} onChange={e => save({ subtitle_y_portrait: Number(e.target.value) })} />
            </div>
          </div>
          <div className="field">
            <label>Piste audio à transcrire</label>
            <input type="number" min={0} max={5} value={s.audio_track} onChange={num('audio_track')} />
            <span className="hint">Astuce : dans OBS, mets ton micro seul sur une 2e piste et choisis 1 ici : les sous-titres seront bien plus propres.</span>
          </div>
        </div>

        <div className="card">
          <h2 style={{ marginBottom: 16 }}>Format 9:16 et effets</h2>
          <div className="field">
            <label>Cadrage des vidéos 16:9</label>
            <select value={s.layout} onChange={e => save({ layout: e.target.value })}>
              <option value="center_crop">Recadrage centré (viseur au milieu)</option>
              <option value="facecam_split">Facecam en haut + jeu en bas</option>
              <option value="blur_fit">Image entière sur fond flouté</option>
            </select>
            <span className="hint">Les enregistrements déjà verticaux (plugin Vertical Canvas) sont gardés tels quels.</span>
          </div>
          {s.layout === 'facecam_split' && (
            <div className="field">
              <label>Zone de la facecam (x0, y0, x1, y1 en fraction de l'image)</label>
              <input type="text" defaultValue={s.facecam_rect.join(', ')}
                onBlur={e => save({ facecam_rect: e.target.value.split(',').map(Number) })} />
            </div>
          )}
          {EFFECTS.map(([k, label]) => (
            <label key={k} className="check">
              <input type="checkbox" checked={!!s.effects[k]} onChange={e => save({ effects: { ...s.effects, [k]: e.target.checked } })} />
              {label}
            </label>
          ))}
        </div>
      </div>
    </div>
  )
}
