import {
  ArrowSquareOut, CheckCircle, Copy, InstagramLogo, LinkSimple, PaperPlaneTilt, TiktokLogo, Warning, X,
  YoutubeLogo, type Icon,
} from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { api, fileUrl, fmtTime, type PlatformDraft, type PublishInfo, type Render } from './api'
import { Spinner, useToast } from './ui'

export const PLATFORM_META: Record<string, { icon: Icon; color: string; short: string }> = {
  youtube: { icon: YoutubeLogo, color: '#ff3b3b', short: 'YouTube' },
  tiktok: { icon: TiktokLogo, color: '#25f4ee', short: 'TikTok' },
  instagram: { icon: InstagramLogo, color: '#e1306c', short: 'Instagram' },
}

const STEPS: Record<string, string[]> = {
  youtube: ['Glisse le fichier depuis l\'Explorateur dans la page YouTube', 'Colle le titre et la description (Ctrl+V)', 'Publie en « Public »'],
  tiktok: ['Glisse le fichier dans TikTok Studio', 'Colle la légende (Ctrl+V)', 'Clique sur « Publier »'],
  instagram: ['Clique sur « Créer » puis glisse le fichier', 'Choisis « Reel » et colle la légende (Ctrl+V)', 'Clique sur « Partager »'],
}

export default function PublishDialog({ render, label, onClose }: { render: Render; label: string; onClose: () => void }) {
  const [info, setInfo] = useState<PublishInfo | null>(null)
  const [tab, setTab] = useState('youtube')
  const [opening, setOpening] = useState(false)
  const dialog = useRef<HTMLDivElement>(null)
  const toast = useToast()

  useEffect(() => { api.publishInfo(render.path).then(setInfo).catch(e => toast((e as Error).message, 'error')) }, [render.path, toast])

  // Échap ferme, le focus reste dans la fenêtre
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    dialog.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'Tab' && dialog.current) {
        const items = dialog.current.querySelectorAll<HTMLElement>('button, input, textarea, video, [tabindex="0"]')
        const first = items[0], last = items[items.length - 1]
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => { window.removeEventListener('keydown', onKey); previous?.focus() }
  }, [onClose])

  const draft = info?.platforms[tab]
  const update = (patch: Partial<PlatformDraft>) => {
    if (!info || !draft) return
    setInfo({ ...info, platforms: { ...info.platforms, [tab]: { ...draft, ...patch } } })
  }
  const persist = (patch: Partial<Pick<PlatformDraft, 'title' | 'caption' | 'status' | 'url'>>) => api.savePublish(render.path, tab, patch)

  const copy = async (text: string, message: string) => {
    try {
      await navigator.clipboard.writeText(text)
      toast(message, 'success')
    } catch {
      toast('Impossible d\'accéder au presse-papiers', 'error')
    }
  }

  const go = async () => {
    if (!draft) return
    setOpening(true)
    await persist({ title: draft.title, caption: draft.caption })
    // YouTube a deux champs : on copie la description, le titre a son propre bouton
    await copy(draft.caption, tab === 'youtube' ? 'Description copiée, colle-la dans YouTube' : 'Légende copiée, colle-la dans la publication')
    await api.openPublish(render.path, tab)
    setOpening(false)
  }

  const markPublished = async (published: boolean) => {
    if (!draft) return
    await persist({ status: published ? 'published' : 'draft', url: draft.url ?? undefined })
    update({ status: published ? 'published' : 'draft' })
    toast(published ? `Marqué comme publié sur ${PLATFORM_META[tab].short}` : 'Remis en brouillon', 'success')
  }

  const tooLong = info && draft && info.duration > draft.max_duration
  const hashtagCount = draft ? (draft.caption.match(/#[\p{L}\d_]+/gu) ?? []).length : 0

  // rendue dans <body> : un ancêtre animé (transform) décalerait la position fixe
  return createPortal(
    <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}>
      <div ref={dialog} className="modal" role="dialog" aria-modal="true" aria-labelledby="publish-title" tabIndex={-1}>
        <div className="modal-head">
          <PaperPlaneTilt size={22} weight="fill" color="var(--accent)" aria-hidden />
          <h2 id="publish-title" className="section-title">Publier · {label}</h2>
          <span className="grow" />
          <button className="btn icon ghost" onClick={onClose} aria-label="Fermer"><X size={18} /></button>
        </div>

        <div className="modal-body">
          <div className="publish-preview">
            <video src={`${fileUrl(render.path)}&v=${render.created_at}`} controls preload="metadata" />
            {info && <div className="faint mono" style={{ fontSize: 12, textAlign: 'center' }}>{fmtTime(info.duration)} · 1080×1920</div>}
          </div>

          <div className="publish-form">
            <div className="platform-tabs" role="tablist" aria-label="Plateforme">
              {Object.entries(PLATFORM_META).map(([key, meta]) => {
                const I = meta.icon
                const done = info?.platforms[key]?.status === 'published'
                return (
                  <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
                    style={{ ['--brand' as string]: meta.color }}>
                    <I size={18} weight="fill" aria-hidden /> {meta.short}
                    {done && <CheckCircle size={15} weight="fill" color="var(--success)" aria-label="publié" />}
                  </button>
                )
              })}
            </div>

            {!info || !draft ? (
              <div style={{ display: 'grid', gap: 12 }}><div className="skeleton" style={{ height: 38 }} /><div className="skeleton" style={{ height: 160 }} /></div>
            ) : (
              <>
                {tooLong && (
                  <div className="notice warn" role="alert">
                    <Warning size={16} weight="fill" aria-hidden />
                    {draft.name} limite les vidéos à {fmtTime(draft.max_duration)} : ce fichier dure {fmtTime(info.duration)}.
                  </div>
                )}

                {draft.title_max > 0 && (
                  <div>
                    <div className="field-row">
                      <label className="field-label" htmlFor="pub-title">Titre</label>
                      <span className={`counter ${draft.title.length > draft.title_max ? 'over' : ''}`}>{draft.title.length}/{draft.title_max}</span>
                    </div>
                    <div className="input-copy">
                      <input id="pub-title" className="input" value={draft.title}
                        onChange={e => update({ title: e.target.value })} onBlur={() => persist({ title: draft.title })} />
                      <button className="btn icon" onClick={() => copy(draft.title, 'Titre copié')} aria-label="Copier le titre" title="Copier le titre"><Copy size={16} /></button>
                    </div>
                  </div>
                )}

                <div>
                  <div className="field-row">
                    <label className="field-label" htmlFor="pub-caption">{tab === 'youtube' ? 'Description' : 'Légende'}</label>
                    <span className={`counter ${hashtagCount > draft.max_hashtags ? 'over' : ''}`} title={`${draft.max_hashtags} hashtags conseillés au maximum`}>
                      {hashtagCount}/{draft.max_hashtags} hashtags</span>
                    <span className={`counter ${draft.caption.length > draft.caption_max ? 'over' : ''}`}>{draft.caption.length}/{draft.caption_max}</span>
                  </div>
                  <div className="input-copy">
                    <textarea id="pub-caption" className="textarea" rows={6} value={draft.caption}
                      onChange={e => update({ caption: e.target.value })} onBlur={() => persist({ caption: draft.caption })} />
                    <button className="btn icon" onClick={() => copy(draft.caption, tab === 'youtube' ? 'Description copiée' : 'Légende copiée')}
                      aria-label="Copier le texte" title="Copier le texte" style={{ alignSelf: 'flex-start' }}><Copy size={16} /></button>
                  </div>
                </div>

                <ol className="publish-steps">
                  {STEPS[tab].map((s, i) => <li key={i}>{s}</li>)}
                </ol>

                <div className="publish-actions">
                  <button className="btn primary lg" onClick={go} disabled={opening}>
                    {opening ? <Spinner size={16} /> : <ArrowSquareOut size={18} weight="bold" aria-hidden />}
                    Copier et ouvrir {PLATFORM_META[tab].short}
                  </button>
                </div>

                <div className="publish-done">
                  <div className="input-copy">
                    <span className="input-icon"><LinkSimple size={15} aria-hidden /></span>
                    <input className="input" placeholder="Lien de la publication (facultatif)" aria-label="Lien de la publication"
                      value={draft.url ?? ''} onChange={e => update({ url: e.target.value })}
                      onBlur={() => persist({ url: draft.url ?? '' })} />
                  </div>
                  {draft.status === 'published' ? (
                    <button className="btn" onClick={() => markPublished(false)}><CheckCircle size={16} weight="fill" color="var(--success)" aria-hidden /> Publié</button>
                  ) : (
                    <button className="btn" onClick={() => markPublished(true)}><CheckCircle size={16} aria-hidden /> Marquer comme publié</button>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  )
}
