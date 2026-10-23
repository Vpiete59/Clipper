import {
  BookmarkSimple, Bomb, ChatCircleDots, CheckCircle, CircleNotch, Coins, Crosshair, Fire, FirstAid,
  Info, MagnifyingGlass, Megaphone, Quotes, SignOut, Skull, Smiley, SpeakerHigh, Sparkle, Warning,
  type Icon,
} from '@phosphor-icons/react'
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'

/* --- événements : couleur + icône (jamais la couleur seule) --- */
export const EVENTS: Record<string, { color: string; icon: Icon }> = {
  gunfight: { color: '#ff6b5e', icon: Crosshair },
  death: { color: '#c4a1ff', icon: Skull },
  bounty: { color: '#ffb938', icon: Coins },
  extract: { color: '#3dd68c', icon: SignOut },
  banish: { color: '#ff8a3d', icon: Fire },
  clue: { color: '#5ab4ff', icon: MagnifyingGlass },
  revive: { color: '#2dd4bf', icon: FirstAid },
  laughter: { color: '#f78fc5', icon: Smiley },
  scream: { color: '#ff7a8a', icon: Megaphone },
  explosion: { color: '#f5a524', icon: Bomb },
  loud: { color: '#8b8b96', icon: SpeakerHigh },
  hype_talk: { color: '#b98cff', icon: ChatCircleDots },
  keyword: { color: '#56c2ff', icon: Quotes },
  bookmark: { color: '#f4f4f5', icon: BookmarkSimple },
}
export const eventStyle = (type: string) => EVENTS[type] ?? { color: '#8b8b96', icon: Sparkle }

export function EventChip({ type, label }: { type: string; label: string }) {
  const { color, icon: I } = eventStyle(type)
  return (
    <span className="chip" style={{ color }}>
      <I size={13} weight="fill" aria-hidden />
      {label}
    </span>
  )
}

/* --- score : anneau qui se remplit, plafonné à 60 points --- */
export function ScoreRing({ score, size = 40 }: { score: number; size?: number }) {
  const r = (size - 5) / 2
  const c = 2 * Math.PI * r
  const pct = Math.min(1, score / 60)
  const color = score >= 40 ? '#ffb938' : score >= 20 ? '#ffd27a' : '#8b8b96'
  return (
    <svg className="score-ring" width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Score ${Math.round(score)}`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="3.5" />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="3.5" strokeLinecap="round"
        strokeDasharray={`${c * pct} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: 'stroke-dasharray 0.6s cubic-bezier(0.22,1,0.36,1)' }} />
      <text x="50%" y="53%" dominantBaseline="middle" textAnchor="middle" fill={color}
        style={{ font: `700 ${size * 0.36}px 'Barlow Condensed', sans-serif` }}>{Math.round(score)}</text>
    </svg>
  )
}

export function Switch({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string }) {
  return (
    <label className="switch">
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} />
      <span className="track" aria-hidden />
      <span className="switch-text">{label}{hint && <small>{hint}</small>}</span>
    </label>
  )
}

export function Spinner({ size = 14 }: { size?: number }) {
  return <CircleNotch size={size} className="spin" aria-hidden />
}

/* --- toasts (aria-live, auto-fermeture 3,5 s) --- */
type ToastKind = 'info' | 'success' | 'error'
type ToastItem = { id: number; text: string; kind: ToastKind }
const ToastCtx = createContext<(text: string, kind?: ToastKind) => void>(() => {})
export const useToast = () => useContext(ToastCtx)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const nextId = useRef(0)
  const push = useCallback((text: string, kind: ToastKind = 'info') => {
    const id = ++nextId.current
    setItems(list => [...list.slice(-2), { id, text, kind }])
    setTimeout(() => setItems(list => list.filter(t => t.id !== id)), 3500)
  }, [])
  const icons = { info: Info, success: CheckCircle, error: Warning }
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map(t => {
          const I = icons[t.kind]
          return <div key={t.id} className={`toast ${t.kind}`}><I size={18} weight="fill" aria-hidden />{t.text}</div>
        })}
      </div>
    </ToastCtx.Provider>
  )
}
