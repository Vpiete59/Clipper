import { ClosedCaptioning, DeviceMobile, FilmReel, FolderOpen, MagicWand, PaperPlaneTilt, Plus, Target, Trash, VideoCamera } from '@phosphor-icons/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { api, type Game, type Settings } from './api'
import { Switch, useToast } from './ui'

const EFFECTS: [string, string, string][] = [
  ['teaser', 'Teaser d\'ouverture', 'Le pic de l\'action en premier, puis retour au début'],
  ['speed_ramp', 'Accélération des temps morts', 'x1,8 quand il ne se passe rien, jamais pendant que tu parles'],
  ['sfx', 'Sons d\'impact', 'Whoosh et coups sourds calés sur les zooms et les kills'],
  ['punch_zoom', 'Zoom punch', 'Zoom brusque sur l\'action, retour en douceur'],
  ['slowmo', 'Ralenti', 'x0,5 autour des fusillades et des morts'],
  ['shake', 'Tremblement', 'Secousse de caméra amortie sur les tirs'],
  ['flash', 'Flash blanc', 'Éclair sur les explosions et les morts'],
  ['hook_title', 'Bandeau d\'accroche', 'Ta phrase forte en haut pendant 2,8 s'],
  ['progress_bar', 'Barre de progression', 'Incite à regarder jusqu\'au bout'],
]
const LAYOUTS: [string, string, ReactNode][] = [
  ['center_crop', 'Recadrage centré', <><div className="game" /><div className="xhair" /></>],
  ['facecam_split', 'Facecam + jeu', <><div className="game" /><div className="cam" /></>],
  ['blur_fit', 'Image entière', <><div className="blurbg" /><div className="fit" /></>],
]
const SUB_STYLES: [string, string, React.CSSProperties][] = [
  ['bold_pop', 'Bold pop', { fontFamily: '"Arial Black", sans-serif' }],
  ['fire', 'Impact', { fontFamily: 'Impact, sans-serif', color: '#ff7a33' }],
  ['clean', 'Sobre', { fontFamily: '"Segoe UI Semibold", sans-serif', fontWeight: 600 }],
]
const SECTIONS: [string, string, ReactNode][] = [
  ['rec', 'Enregistrements', <VideoCamera size={17} aria-hidden />],
  ['detect', 'Détection', <Target size={17} aria-hidden />],
  ['subs', 'Sous-titres', <ClosedCaptioning size={17} aria-hidden />],
  ['format', 'Format & effets', <MagicWand size={17} aria-hidden />],
  ['stories', 'Résumés', <FilmReel size={17} aria-hidden />],
  ['publish', 'Publication', <PaperPlaneTilt size={17} aria-hidden />],
]

export default function SettingsPage({ games }: { games: Game[] }) {
  const [s, setS] = useState<Settings | null>(null)
  const toast = useToast()
  const lastToast = useRef(0)
  useEffect(() => { api.settings().then(setS) }, [])
  if (!s) return <div className="page"><div className="skeleton" style={{ height: 500 }} /></div>

  const save = async (patch: Partial<Settings>) => {
    setS({ ...s, ...patch })
    setS(await api.saveSettings(patch))
    if (Date.now() - lastToast.current > 2500) { toast('Réglage enregistré', 'success'); lastToast.current = Date.now() }
  }
  const num = (k: keyof Settings) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const n = Number(e.target.value)
    if (e.target.value !== '' && !Number.isNaN(n)) save({ [k]: n } as Partial<Settings>)
  }

  return (
    <div className="page">
      <div className="page-head">
        <div className="grow">
          <div className="eyebrow">Configuration</div>
          <h1 className="page-title">Réglages</h1>
          <div className="page-sub">Chaque changement est enregistré tout de suite. Les réglages de détection s'appliquent au prochain enregistrement ou avec « Ré-analyser ».</div>
        </div>
      </div>

      <div className="settings-layout">
        <nav className="settings-nav" aria-label="Sections des réglages">
          {SECTIONS.map(([id, label, icon]) => <a key={id} href={`#${id}`}>{icon}{label}</a>)}
        </nav>

        <div className="settings-sections">
          <Section id="rec" icon={<VideoCamera size={20} />} title="Enregistrements" desc="Où Clipper trouve tes parties et où il dépose les clips.">
            <div className="fgrid">
              <div className="full">
                <span className="field-label">Dossiers surveillés</span>
                {s.watch_folders.map((f, i) => (
                  <div key={`${i}-${f}`} className="folder-row">
                    <input className="input" defaultValue={f} aria-label={`Dossier surveillé ${i + 1}`} placeholder="D:\Streaming"
                      onBlur={e => { const next = [...s.watch_folders]; next[i] = e.target.value.trim(); save({ watch_folders: next.filter(Boolean) }) }} />
                    <button className="btn icon" aria-label="Ouvrir le dossier" title="Ouvrir" onClick={() => api.reveal(f)}><FolderOpen size={16} /></button>
                    <button className="btn icon danger" aria-label="Retirer ce dossier" title="Retirer" onClick={() => save({ watch_folders: s.watch_folders.filter((_, j) => j !== i) })}><Trash size={16} /></button>
                  </div>
                ))}
                <button className="btn sm" onClick={() => setS({ ...s, watch_folders: [...s.watch_folders, ''] })}><Plus size={14} weight="bold" aria-hidden /> Ajouter un dossier</button>
                <div className="hint">Détectés automatiquement depuis ta config OBS (enregistrement et plugin Vertical Canvas).</div>
              </div>
              <div className="full">
                <Switch checked={s.auto_process} onChange={v => save({ auto_process: v })}
                  label="Traitement automatique" hint="Analyser puis rendre les clips dès qu'un enregistrement se termine" />
              </div>
              <NumberField id="min-auto" label="Durée minimale pour le traitement auto (s)" value={s.auto_min_duration} min={0} max={3600}
                onChange={num('auto_min_duration')}
                hint="Les vidéos plus courtes (extraits, vidéos Kinevir…) restent dans « Dans tes dossiers OBS » sans être analysées. Tu peux toujours les lancer à la main." />
              <div>
                <label className="field-label" htmlFor="default-game">Jeu par défaut</label>
                <select id="default-game" className="select" value={s.default_game} onChange={e => save({ default_game: e.target.value })}>
                  {games.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
                </select>
              </div>
              <div>
                <label className="field-label" htmlFor="out-folder">Dossier de sortie des clips</label>
                <input id="out-folder" className="input" defaultValue={s.output_folder} onBlur={e => save({ output_folder: e.target.value.trim() })} />
              </div>
            </div>
          </Section>

          <Section id="detect" icon={<Target size={20} />} title="Détection" desc="Combien de moments garder, et à partir de quand un moment compte.">
            <div className="fgrid">
              <NumberField id="max-clips" label="Clips max par vidéo" value={s.max_clips} min={1} max={30} onChange={num('max_clips')} />
              <NumberField id="min-score" label="Score minimum" value={s.min_score} min={0} max={100} onChange={num('min_score')}
                hint="Plus bas = plus de clips, plus haut = seulement les meilleurs" />
              <NumberField id="min-len" label="Durée minimum (s)" value={s.clip_min_s} min={3} max={60} onChange={num('clip_min_s')} />
              <NumberField id="max-len" label="Durée maximum (s)" value={s.clip_max_s} min={10} max={180} onChange={num('clip_max_s')} />
              <div className="full">
                <label className="field-label" htmlFor="kw">Mots-clés perso</label>
                <textarea id="kw" className="textarea" rows={3} defaultValue={s.custom_keywords.join('\n')} placeholder={'clippe ça\nquel tir'}
                  onBlur={e => save({ custom_keywords: e.target.value.split('\n').map(x => x.trim()).filter(Boolean) })} />
                <div className="hint">Un par ligne. Dis-les pendant ta partie pour forcer un moment fort.</div>
              </div>
            </div>
          </Section>

          <Section id="subs" icon={<ClosedCaptioning size={20} />} title="Sous-titres" desc="Transcription et apparence des sous-titres incrustés.">
            <div className="sub-preview-wrap">
              <div className="fgrid">
                <div>
                  <label className="field-label" htmlFor="lang">Langue</label>
                  <select id="lang" className="select" value={s.language} onChange={e => save({ language: e.target.value })}>
                    <option value="fr">Français</option><option value="en">Anglais</option><option value="auto">Détection auto</option>
                  </select>
                </div>
                <div>
                  <label className="field-label" htmlFor="model">Modèle Whisper</label>
                  <select id="model" className="select" value={s.whisper_model} onChange={e => save({ whisper_model: e.target.value })}>
                    <option value="large-v3">large-v3 (le plus précis)</option>
                    <option value="large-v3-turbo">large-v3-turbo (plus rapide)</option>
                    <option value="medium">medium</option>
                  </select>
                </div>
                <div className="full">
                  <span className="field-label">Style</span>
                  <div className="style-cards" role="radiogroup" aria-label="Style des sous-titres">
                    {SUB_STYLES.map(([k, label, css]) => (
                      <button key={k} className="style-card" role="radio" aria-checked={s.subtitle_style === k} onClick={() => save({ subtitle_style: k })}>
                        <span className="sample" style={css}>LET'S <span style={{ color: k === 'fire' ? '#ff7a33' : k === 'clean' ? '#fff' : '#ffe500' }}>GO</span></span>
                        <small>{label}</small>
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="field-label" htmlFor="y-land">Hauteur, sources 16:9 · <span className="mono">{Math.round(s.subtitle_y * 100)} %</span></label>
                  <input id="y-land" type="range" min={0.3} max={0.9} step={0.01} value={s.subtitle_y} onChange={e => setS({ ...s, subtitle_y: Number(e.target.value) })}
                    onPointerUp={e => save({ subtitle_y: Number((e.target as HTMLInputElement).value) })}
                    onKeyUp={e => save({ subtitle_y: Number((e.target as HTMLInputElement).value) })} />
                </div>
                <div>
                  <label className="field-label" htmlFor="y-port">Hauteur, sources verticales · <span className="mono">{Math.round(s.subtitle_y_portrait * 100)} %</span></label>
                  <input id="y-port" type="range" min={0.2} max={0.9} step={0.01} value={s.subtitle_y_portrait} onChange={e => setS({ ...s, subtitle_y_portrait: Number(e.target.value) })}
                    onPointerUp={e => save({ subtitle_y_portrait: Number((e.target as HTMLInputElement).value) })}
                    onKeyUp={e => save({ subtitle_y_portrait: Number((e.target as HTMLInputElement).value) })} />
                </div>
                <div className="full">
                  <NumberField id="track" label="Piste audio à transcrire" value={s.audio_track} min={0} max={5} onChange={num('audio_track')}
                    hint="Astuce : dans OBS, mets ton micro seul sur une 2e piste et choisis 1 ici. Les sous-titres ignoreront Discord et le jeu." />
                </div>
              </div>
              <SubPreview s={s} />
            </div>
          </Section>

          <Section id="format" icon={<MagicWand size={20} />} title="Format 9:16 et effets" desc="Comment tes parties 16:9 deviennent des clips verticaux.">
            <span className="field-label">Cadrage des vidéos 16:9</span>
            <div className="layout-options" role="radiogroup" aria-label="Cadrage">
              {LAYOUTS.map(([k, label, art]) => (
                <button key={k} className="layout-opt" role="radio" aria-checked={s.layout === k} onClick={() => save({ layout: k })}>
                  <div className="phone" aria-hidden>{art}</div>{label}
                </button>
              ))}
            </div>
            <div className="hint" style={{ marginBottom: 16 }}>
              <DeviceMobile size={13} style={{ verticalAlign: '-2px' }} aria-hidden /> Les enregistrements déjà verticaux (plugin Vertical Canvas) sont gardés tels quels.
            </div>
            {s.layout === 'facecam_split' && (
              <div style={{ marginBottom: 16 }}>
                <label className="field-label" htmlFor="cam">Zone de la facecam dans l'image 16:9 (x0, y0, x1, y1 en fractions)</label>
                <input id="cam" className="input mono" defaultValue={s.facecam_rect.join(', ')}
                  onBlur={e => { const r = e.target.value.split(',').map(Number); if (r.length === 4 && r.every(n => !Number.isNaN(n))) save({ facecam_rect: r }) }} />
              </div>
            )}
            <span className="field-label">Effets de rétention</span>
            <div className="effects-grid">
              {EFFECTS.map(([k, label, hint]) => (
                <Switch key={k} checked={!!s.effects[k]} label={label} hint={hint} onChange={v => save({ effects: { ...s.effects, [k]: v } })} />
              ))}
            </div>
          </Section>

          <Section id="stories" icon={<FilmReel size={20} />} title="Résumés de partie" desc="Le short qui raconte une partie, de l'indice à la sortie.">
            <div className="fgrid">
              <div className="full">
                <span className="field-label">Rythme</span>
                <div className="segmented" role="radiogroup" aria-label="Rythme des résumés">
                  {([['recit', 'Récit (~2 min)'], ['action', 'Action (~1 min 45)'], ['express', 'Express (~1 min 30)']] as const).map(([k, l]) => (
                    <button key={k} role="radio" aria-selected={s.story_preset === k} onClick={() => save({ story_preset: k })}>{l}</button>
                  ))}
                </div>
                <div className="hint">S'applique aux prochaines analyses, ou à « Ré-analyser ».</div>
              </div>
              <div className="full">
                <span className="field-label">Titres des chapitres</span>
                <div className="segmented" role="radiogroup" aria-label="Style des titres">
                  {([['center', 'Gros titre au centre'], ['hunt', 'Façon Hunt (doré)'], ['banner', 'Bandeau jaune']] as const).map(([k, l]) => (
                    <button key={k} role="radio" aria-selected={s.title_style === k} onClick={() => save({ title_style: k })}>{l}</button>
                  ))}
                </div>
              </div>
              <div className="full">
                <Switch checked={s.story_only_worth} onChange={v => save({ story_only_worth: v })}
                  label="Résumés automatiques seulement pour les bonnes parties" hint="Extraction réussie, ou au moins 2 kills. Les autres restent disponibles à la main." />
              </div>
            </div>
          </Section>

          <Section id="publish" icon={<PaperPlaneTilt size={20} />} title="Publication" desc="Ce que Clipper ajoute aux textes proposés pour YouTube, TikTok et Instagram.">
            <div className="fgrid">
              <div className="full">
                <label className="field-label" htmlFor="sig">Signature</label>
                <input id="sig" className="input" defaultValue={s.publish_signature} placeholder="Abonne-toi pour plus de Hunt 🔥"
                  onBlur={e => save({ publish_signature: e.target.value.trim() })} />
                <div className="hint">Ajoutée à chaque description, avant les hashtags.</div>
              </div>
              <div className="full">
                <label className="field-label" htmlFor="tags">Hashtags en plus</label>
                <input id="tags" className="input" defaultValue={s.extra_hashtags.map(t => `#${t.replace(/^#/, '')}`).join(' ')} placeholder="#vizile #twitchfr"
                  onBlur={e => save({ extra_hashtags: e.target.value.split(/[\s,]+/).map(t => t.replace(/^#/, '')).filter(Boolean) })} />
                <div className="hint">Ajoutés après ceux du jeu. Chaque plateforme en garde 5 au maximum.</div>
              </div>
            </div>
          </Section>
        </div>
      </div>
    </div>
  )
}

function Section({ id, icon, title, desc, children }: { id: string; icon: ReactNode; title: string; desc: string; children: ReactNode }) {
  return (
    <section id={id} className="card sset" aria-labelledby={`${id}-t`}>
      <div className="sset-head">
        <div className="sset-icon" aria-hidden>{icon}</div>
        <div><h2 id={`${id}-t`} className="section-title">{title}</h2><p>{desc}</p></div>
      </div>
      {children}
    </section>
  )
}

function NumberField({ id, label, value, min, max, onChange, hint }: {
  id: string; label: string; value: number; min: number; max: number; hint?: string
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void
}) {
  return (
    <div>
      <label className="field-label" htmlFor={id}>{label}</label>
      <input id={id} className="input mono" type="number" min={min} max={max} defaultValue={value} onBlur={onChange} />
      {hint && <div className="hint">{hint}</div>}
    </div>
  )
}

function SubPreview({ s }: { s: Settings }) {
  const hl = s.subtitle_style === 'fire' ? '#ff7a33' : s.subtitle_style === 'clean' ? '#ffffff' : '#ffe500'
  return (
    <div aria-label="Aperçu du clip">
      <span className="field-label" style={{ textAlign: 'center' }}>Aperçu</span>
      <div className="sub-preview">
        {s.effects.hook_title && <div className="hook">IL EST DOWN</div>}
        <div className={`line ${s.subtitle_style}`} style={{ top: `${s.subtitle_y_portrait * 100}%`, ['--hl' as string]: hl }}>
          JE L'AI <em>EU</em>
        </div>
        <div className="cam" />
        {s.effects.progress_bar && <div className="bar" />}
      </div>
      <div className="hint" style={{ textAlign: 'center' }}>Source verticale avec facecam</div>
    </div>
  )
}
