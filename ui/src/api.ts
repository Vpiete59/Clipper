export type MatchSummary = {
  vid: string; video: string; added_at: number; id: number; start: number; end: number
  outcome: 'extracted' | 'dead' | 'unknown'; clues: number; kills: number; bounty: boolean; boss: boolean
  potential: number; worth: boolean; chapters: number
}
export type ThumbOptions = {
  vid: string; t: number; text: string; subtitle: string; color: string; position: string
  boost: boolean; size: number; auto_frame: boolean
}
export type QueueState = { paused: boolean; running: { vid: string; kind: string } | null; pending: { vid: string; kind: string }[] }
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
export type Chapter = { type: string; label: string; t: number; start: number; end: number; score: number }
export type Match = {
  id: number; start: number; end: number; outcome: 'extracted' | 'dead' | 'unknown'
  clues: number; fights: number; kills: number; bounty: boolean; boss: boolean; chapters: Chapter[]
  potential: number; worth: boolean
}
export type Analysis = {
  video_id: string; game: string; orientation: string; duration: number; fps: number
  segments: Segment[]; events: GameEvent[]; moments: Moment[]; matches?: Match[]
  timeline: Record<string, number[]>; timeline_step: number
}
export type Render = {
  id: number; video_id: string; moment_id: number | null; kind: string; path: string; created_at: number
  published: string[]
}
export type PlatformDraft = {
  name: string; upload_url: string; title_max: number; caption_max: number; max_hashtags: number
  max_duration: number; title: string; caption: string; status: 'draft' | 'published'; url: string | null
}
export type PublishInfo = { duration: number; platforms: Record<string, PlatformDraft> }
export type LearnedSound = { label: string; hint: string; event: string }
export type Game = { id: string; name: string; description: string; learned_sounds: Record<string, LearnedSound> }
export type SoundExample = { id: string; game: string; kind: string; video_id: string; video_name: string; t: number; negative: boolean }
export type InboxFile = { path: string; name: string; size: number; mtime: number }
export type Settings = {
  watch_folders: string[]; output_folder: string; auto_process: boolean; default_game: string; auto_min_duration: number
  language: string; whisper_model: string; audio_track: number; max_clips: number
  clip_min_s: number; clip_max_s: number; min_score: number; subtitle_style: string; subtitle_y: number; subtitle_y_portrait: number
  layout: string; facecam_rect: number[]; effects: Record<string, boolean>; custom_keywords: string[]
  extra_hashtags: string[]; publish_signature: string
  story_preset: string; title_style: string; story_only_worth: boolean
  alert_phrases: string[]; ally_down_phrases: string[]; enemy_down_phrases: string[]
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
  queue: () => req<QueueState>('GET', '/api/queue'),
  allMatches: () => req<MatchSummary[]>('GET', '/api/matches'),
  compile: (items: [string, number][], title: string) => req('POST', '/api/compilations', { items, title }),
  thumbCandidates: (vid: string) => req<{ t: number; label: string }[]>('GET', `/api/thumbnail/candidates/${vid}`),
  thumbPreview: async (o: ThumbOptions) => {
    const res = await fetch('/api/thumbnail/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(o) })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? `Erreur ${res.status}`)
    return { url: URL.createObjectURL(await res.blob()), t: Number(res.headers.get('X-Frame-Time') ?? o.t) }
  },
  thumbSave: (o: ThumbOptions) => req<{ path: string; t: number }>('POST', '/api/thumbnail/save', o),
  pauseQueue: (paused: boolean) => req<QueueState>('POST', '/api/queue/pause', { paused }),
  unqueue: (vid: string) => req('DELETE', `/api/queue/${vid}`),
  clearQueue: () => req<{ cleared: number }>('DELETE', '/api/queue'),
  video: (id: string) => req<{ video: Video; analysis: Analysis | null; renders: Render[] }>('GET', `/api/videos/${id}`),
  importVideo: (path: string, game?: string) => req<Video>('POST', '/api/videos', { path, game }),
  deleteVideo: (id: string, source: boolean, clips: boolean) =>
    req<{ trashed: string[] }>('DELETE', `/api/videos/${id}?source=${source}&clips=${clips}`),
  renameVideo: (id: string, name: string) => req<Video>('PATCH', `/api/videos/${id}`, { name }),
  deleteRender: (path: string) => req('DELETE', `/api/renders?path=${encodeURIComponent(path)}`),
  deleteInbox: (path: string) => req('DELETE', `/api/inbox?path=${encodeURIComponent(path)}`),
  analyze: (id: string) => req('POST', `/api/videos/${id}/analyze`),
  setGame: (id: string, game: string) => req<{ needs_reanalyze?: boolean }>('POST', `/api/videos/${id}/game`, { game }),
  patchMoment: (id: string, mid: number, patch: Partial<Moment>) => req<Moment>('PATCH', `/api/videos/${id}/moments/${mid}`, patch),
  addMoment: (id: string, start: number, end: number, hook: string) => req<Analysis>('POST', `/api/videos/${id}/moments`, { start, end, hook }),
  editWord: (id: string, segment: number, word: number, text: string) => req('PUT', `/api/videos/${id}/words`, { segment, word, text }),
  editLine: (id: string, segment: number, text: string) => req('PUT', `/api/videos/${id}/segments/${segment}`, { text }),
  render: (id: string, moment_ids: number[] | null, montage: boolean, match_ids: number[] | null = null, longform = false) =>
    req('POST', `/api/videos/${id}/render`, { moment_ids, montage, match_ids, longform }),
  games: () => req<Game[]>('GET', '/api/games'),
  settings: () => req<Settings>('GET', '/api/settings'),
  saveSettings: (patch: Partial<Settings>) => req<Settings>('PUT', '/api/settings', patch),
  reveal: (path: string) => req('POST', '/api/reveal', { path }),
  sounds: (game: string) => req<SoundExample[]>('GET', `/api/sounds?game=${encodeURIComponent(game)}`),
  teachSound: (id: string, kind: string, t: number, negative: boolean, snap = false) =>
    req<{ t: number; analysis: Analysis }>('POST', `/api/videos/${id}/sounds`, { kind, t, negative, snap }),
  forgetSound: (soundId: string) => req('DELETE', `/api/sounds/${soundId}`),
  publishInfo: (path: string) => req<PublishInfo>('GET', `/api/publish?path=${encodeURIComponent(path)}`),
  savePublish: (path: string, platform: string, patch: Partial<Pick<PlatformDraft, 'title' | 'caption' | 'status' | 'url'>>) =>
    req('PUT', '/api/publish', { path, platform, ...patch }),
  openPublish: (path: string, platform: string) => req('POST', '/api/publish/open', { path, platform }),
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
  audio: 'Extraction audio', voix: 'Isolation des voix', transcription: 'Transcription', sons: 'Sons', image: 'Lecture du HUD',
  moments: 'Moments forts', rendu: 'Rendu des clips', montage: 'Montage', longue: 'Vidéo YouTube', compilation: 'Vidéo YouTube (compilation)',
}

export const EVENT_COLOR: Record<string, string> = {
  gunfight: '#ff5a4e', death: '#a78bfa', bounty: '#ffe500', extract: '#34d399', banish: '#f97316',
  clue: '#60a5fa', revive: '#2dd4bf', laughter: '#f472b6', scream: '#fb7185', explosion: '#f59e0b',
  loud: '#94a3b8', hype_talk: '#c084fc', keyword: '#38bdf8', bookmark: '#ffffff',
}
