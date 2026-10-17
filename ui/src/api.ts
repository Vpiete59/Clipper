export type Video = {
  id: string; path: string; name: string; size: number; duration: number | null
  orientation: string | null; game: string; status: string; stage: string | null
  progress: number; error: string | null; n_moments: number; best_score: number; added_at: number
}
export type Word = { start: number; end: number; word: string; prob: number }
export type Segment = { start: number; end: number; text: string; words: Word[] }
export type GameEvent = {
  t: number; start: number; end: number; type: string; source: string; strength: number
  score: number; label: string; text?: string; effects: string[]
}
export type Moment = {
  id: number; start: number; end: number; score: number; title: string; peak: number
  events: GameEvent[]; hook?: string; excluded?: boolean; manual?: boolean
}
export type Analysis = {
  video_id: string; game: string; orientation: string; duration: number; fps: number
  segments: Segment[]; events: GameEvent[]; moments: Moment[]
  timeline: Record<string, number[]>; timeline_step: number
}
export type Render = { id: number; video_id: string; moment_id: number | null; kind: string; path: string; created_at: number }
export type Game = { id: string; name: string; description: string }
export type InboxFile = { path: string; name: string; size: number; mtime: number }
export type Settings = {
  watch_folders: string[]; output_folder: string; auto_process: boolean; default_game: string
  language: string; whisper_model: string; audio_track: number; max_clips: number
  clip_min_s: number; clip_max_s: number; min_score: number; subtitle_style: string; subtitle_y: number; subtitle_y_portrait: number
  layout: string; facecam_rect: number[]; effects: Record<string, boolean>; custom_keywords: string[]
}

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail ?? `Erreur ${res.status}`)
  }
  return res.json()
}

export const api = {
  videos: () => req<Video[]>('GET', '/api/videos'),
  inbox: () => req<InboxFile[]>('GET', '/api/inbox'),
  video: (id: string) => req<{ video: Video; analysis: Analysis | null; renders: Render[] }>('GET', `/api/videos/${id}`),
  importVideo: (path: string, game?: string) => req<Video>('POST', '/api/videos', { path, game }),
  deleteVideo: (id: string) => req('DELETE', `/api/videos/${id}`),
  analyze: (id: string) => req('POST', `/api/videos/${id}/analyze`),
  setGame: (id: string, game: string) => req<{ needs_reanalyze?: boolean }>('POST', `/api/videos/${id}/game`, { game }),
  patchMoment: (id: string, mid: number, patch: Partial<Moment>) => req<Moment>('PATCH', `/api/videos/${id}/moments/${mid}`, patch),
  addMoment: (id: string, start: number, end: number, hook: string) => req<Analysis>('POST', `/api/videos/${id}/moments`, { start, end, hook }),
  editWord: (id: string, segment: number, word: number, text: string) => req('PUT', `/api/videos/${id}/words`, { segment, word, text }),
  render: (id: string, moment_ids: number[] | null, montage: boolean) => req('POST', `/api/videos/${id}/render`, { moment_ids, montage }),
  games: () => req<Game[]>('GET', '/api/games'),
  settings: () => req<Settings>('GET', '/api/settings'),
  saveSettings: (patch: Partial<Settings>) => req<Settings>('PUT', '/api/settings', patch),
  reveal: (path: string) => req('POST', '/api/reveal', { path }),
}

export const fileUrl = (path: string) => `/media/file?path=${encodeURIComponent(path)}`

export function fmtTime(s: number): string {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

export function fmtSize(bytes: number): string {
  return bytes > 1e9 ? `${(bytes / 1e9).toFixed(1)} Go` : `${Math.round(bytes / 1e6)} Mo`
}

export const STATUS_LABEL: Record<string, string> = {
  new: 'Nouveau', queued: 'En file', analyzing: 'Analyse', analyzed: 'Analysé',
  rendering_queued: 'Rendu en file', rendering: 'Rendu', done: 'Terminé', error: 'Erreur',
}

export const STAGE_LABEL: Record<string, string> = {
  audio: 'Extraction audio', transcription: 'Transcription', sons: 'Sons', image: 'Lecture du HUD',
  moments: 'Moments forts', rendu: 'Rendu des clips', montage: 'Montage',
}

export const EVENT_COLOR: Record<string, string> = {
  gunfight: '#ff5a4e', death: '#a78bfa', bounty: '#ffe500', extract: '#34d399', banish: '#f97316',
  clue: '#60a5fa', revive: '#2dd4bf', laughter: '#f472b6', scream: '#fb7185', explosion: '#f59e0b',
  loud: '#94a3b8', hype_talk: '#c084fc', keyword: '#38bdf8', bookmark: '#ffffff',
}
