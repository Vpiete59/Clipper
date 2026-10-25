import { FloppyDisk, FolderOpen, Image as ImageIcon, MagicWand, X } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { api, fmtTime, type ThumbOptions } from './api'
import { Spinner, Switch, useToast } from './ui'

const COLORS: [string, string][] = [['jaune', '#FFE500'], ['rouge', '#FF3B30'], ['orange', '#FF8A1F'], ['vert', '#3DD68C'], ['blanc', '#FFFFFF']]
const POSITIONS: [string, string][] = [['haut', 'En haut'], ['centre', 'Au centre'], ['bas', 'En bas']]
const IDEAS = ["ON S'EN SORT !", 'IL M\'A EU…', 'TEAM WIPE', '1 CONTRE 3', 'PRIME VOLÉE', 'CLUTCH !', 'QUEL TIR']

/** Éditeur de miniature YouTube : image, texte, couleur, position, aperçu en direct, export 1280x720. */
export default function ThumbnailDialog({ vid, time, onClose }: { vid: string; time: number; onClose: () => void }) {
  const [opts, setOpts] = useState<ThumbOptions>({
    vid, t: time, text: IDEAS[0], subtitle: 'HUNT: SHOWDOWN 1896', color: 'jaune', position: 'bas', boost: true, size: 118, auto_frame: true,
  })
  const [candidates, setCandidates] = useState<{ t: number; label: string }[]>([])
  const [preview, setPreview] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [saved, setSaved] = useState<string | null>(null)
  const toast = useToast()
  const timer = useRef<number>(0)
  const last = useRef<string | null>(null)

  useEffect(() => {
    api.thumbCandidates(vid).then(list => {
      setCandidates(list)
      // lecture au tout début (menus du jeu) : on part plutôt du meilleur moment de la vidéo
      if (time < 5 && list.length) setOpts(o => ({ ...o, t: list[0].t }))
    }).catch(() => {})
  }, [vid, time])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // aperçu recalculé 400 ms après la dernière modification
  useEffect(() => {
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(async () => {
      setLoading(true)
      try {
        const r = await api.thumbPreview(opts)
        if (last.current) URL.revokeObjectURL(last.current)
        last.current = r.url
        setPreview(r.url)
      } catch (e) {
        toast((e as Error).message, 'error')
      } finally {
        setLoading(false)
      }
    }, 400)
    return () => window.clearTimeout(timer.current)
  }, [opts, toast])

  const set = (patch: Partial<ThumbOptions>) => { setOpts(o => ({ ...o, ...patch })); setSaved(null) }
  const save = async () => {
    try {
      const r = await api.thumbSave(opts)
      setSaved(r.path)
      toast('Miniature enregistrée', 'success')
    } catch (e) {
      toast((e as Error).message, 'error')
    }
  }

  return createPortal(
    <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}>
      <div className="modal thumb-modal" role="dialog" aria-modal="true" aria-labelledby="thumb-title">
        <div className="modal-head">
          <ImageIcon size={22} weight="fill" color="var(--accent)" aria-hidden />
          <h2 id="thumb-title" className="section-title">Créer une miniature</h2>
          <span className="grow" />
          <button className="btn icon ghost" onClick={onClose} aria-label="Fermer"><X size={18} /></button>
        </div>
        <div className="thumb-body">
          <div className="thumb-left">
            <div className="thumb-preview">
              {preview && <img src={preview} alt="Aperçu de la miniature" />}
              {loading && <div className="thumb-loading"><Spinner size={22} /></div>}
            </div>
            <span className="field-label">Image</span>
            <div className="thumb-strip">
              <button className={`thumb-cand ${Math.abs(opts.t - time) < 0.5 ? 'on' : ''}`} onClick={() => set({ t: time })} title="Position actuelle de la lecture">
                <img src={`/media/thumb/${vid}?t=${time.toFixed(1)}`} alt="" /><span>Lecture · {fmtTime(time)}</span>
              </button>
              {candidates.map(c => (
                <button key={c.t} className={`thumb-cand ${Math.abs(opts.t - c.t) < 0.5 ? 'on' : ''}`} onClick={() => set({ t: c.t })} title={c.label}>
                  <img src={`/media/thumb/${vid}?t=${c.t.toFixed(1)}`} alt="" loading="lazy" /><span>{c.label}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="thumb-form">
            <div>
              <label className="field-label" htmlFor="thumb-text">Texte principal</label>
              <input id="thumb-text" className="input" value={opts.text} maxLength={28} onChange={e => set({ text: e.target.value.toUpperCase() })} />
              <div className="thumb-ideas">
                {IDEAS.map(i => <button key={i} className="chip" onClick={() => set({ text: i })}>{i}</button>)}
              </div>
              <div className="hint">Court et fort : 2 à 4 mots se lisent même en tout petit sur mobile.</div>
            </div>
            <div>
              <label className="field-label" htmlFor="thumb-sub">Petit texte</label>
              <input id="thumb-sub" className="input" value={opts.subtitle} maxLength={40} onChange={e => set({ subtitle: e.target.value })} />
            </div>
            <div>
              <span className="field-label">Couleur</span>
              <div className="swatches" role="radiogroup" aria-label="Couleur du texte">
                {COLORS.map(([k, hex]) => (
                  <button key={k} role="radio" aria-checked={opts.color === k} aria-label={k} title={k}
                    className="swatch" style={{ background: hex }} onClick={() => set({ color: k })} />
                ))}
              </div>
            </div>
            <div>
              <span className="field-label">Position du texte</span>
              <div className="segmented" role="radiogroup" aria-label="Position du texte">
                {POSITIONS.map(([k, l]) => <button key={k} role="radio" aria-selected={opts.position === k} onClick={() => set({ position: k })}>{l}</button>)}
              </div>
            </div>
            <div>
              <label className="field-label" htmlFor="thumb-size">Taille du texte · <span className="mono">{opts.size}</span></label>
              <input id="thumb-size" type="range" min={70} max={170} value={opts.size} onChange={e => set({ size: Number(e.target.value) })} />
            </div>
            <Switch checked={opts.auto_frame} onChange={v => set({ auto_frame: v })} label="Image la plus lisible autour du moment"
              hint="Cherche dans les 4 s précédentes l'image la plus claire et contrastée" />
            <Switch checked={opts.boost} onChange={v => set({ boost: v })} label="Couleurs renforcées" hint="Saturation et contraste un peu poussés, comme les miniatures qui se cliquent" />
          </div>
        </div>
        <div className="confirm-actions">
          {saved && <button className="btn ghost" onClick={() => api.reveal(saved)}><FolderOpen size={16} aria-hidden /> Ouvrir le dossier</button>}
          <span className="grow" />
          <button className="btn" onClick={() => set({ auto_frame: true })} title="Laisser Clipper choisir l'image"><MagicWand size={16} aria-hidden /> Image auto</button>
          <button className="btn primary" onClick={save}><FloppyDisk size={16} weight="fill" aria-hidden /> Enregistrer (1280×720)</button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
