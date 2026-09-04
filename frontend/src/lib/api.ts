import { PipelineJob, Clip, Video, Channel, QueueItem, CalendarDay, PipelineRunRequest, SettingsStatus, CreateChannelRequest } from '../types';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const isFormData = options?.body instanceof FormData;
  const headers: Record<string, string> = {
    ...(!isFormData ? { 'Content-Type': 'application/json' } : {}),
    ...(options?.headers as Record<string, string>),
  };
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });
  if (!response.ok) {
    let errDetail = response.statusText;
    try {
      const errJson = await response.json();
      if (errJson?.detail) errDetail = errJson.detail;
    } catch {}
    throw new Error(`API error: ${response.status} ${errDetail}`);
  }
  return response.json();
}

function get<T>(endpoint: string, params?: Record<string, any>) {
  const url = params ? `${endpoint}?${new URLSearchParams(params)}` : endpoint;
  return request<T>(url);
}

function post<T>(endpoint: string, body: any) {
  return request<T>(endpoint, { method: 'POST', body: JSON.stringify(body) });
}

function patch<T>(endpoint: string, body: any) {
  return request<T>(endpoint, { method: 'PATCH', body: JSON.stringify(body) });
}

function del<T>(endpoint: string) {
  return request<T>(endpoint, { method: 'DELETE' });
}

export const api = {
  pipeline: {
    run: (body: PipelineRunRequest) => post<{job_id: string, status: string}>('/api/pipeline/run', body),
    getJob: (id: string) => get<PipelineJob>(`/api/pipeline/jobs/${id}`),
    listJobs: () => get<PipelineJob[]>('/api/pipeline/jobs'),
    cancelJob: (id: string) => del(`/api/pipeline/jobs/${id}`),
    streamUrl: (id: string) => `${API_BASE}/api/pipeline/jobs/${id}/stream`,
  },
  clips: {
    list: (params?: {video_id?: string, limit?: number, offset?: number}) => get<Clip[]>('/api/clips', params),
    get: (id: string) => get<Clip>(`/api/clips/${id}`),
    update: (id: string, body: Partial<Clip>) => patch<Clip>(`/api/clips/${id}`, body),
    delete: (id: string) => del(`/api/clips/${id}`),
    batchDelete: (clip_ids: string[]) => post<{ deleted_count: number }>('/api/clips/batch-delete', { clip_ids }),
    uploadVideoThumbnail: (clipId: string, file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      return request<{ success: boolean; video_id: string; thumbnail_path: string; updated_clips_count: number }>(
        `/api/clips/${clipId}/upload-video-thumbnail`,
        { method: 'POST', body: fd }
      );
    },
    fileUrl: (id: string) => `${API_BASE}/api/clips/${id}/file`,
    thumbnailUrl: (id: string) => `${API_BASE}/api/clips/${id}/thumbnail`,
  },
  videos: {
    list: () => get<Video[]>('/api/videos'),
    get: (id: string) => get<Video>(`/api/videos/${id}`),
    uploadThumbnail: (videoId: string, file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      return request<{ success: boolean; video_id: string; thumbnail_path: string; updated_clips_count: number }>(
        `/api/videos/${videoId}/thumbnail`,
        { method: 'POST', body: fd }
      );
    },
  },
  channels: {
    list: (params?: {is_tracked?: boolean}) => get<Channel[]>('/api/channels', params),
    create: (body: CreateChannelRequest) => post<Channel>('/api/channels', body),
    update: (id: string, body: Partial<Channel>) => patch<Channel>(`/api/channels/${id}`, body),
    delete: (id: string) => del(`/api/channels/${id}`),
  },
  queue: {
    list: (params?: {status?: string}) => get<QueueItem[]>('/api/queue', params),
    add: (body: {clip_id: string, scheduled_at?: string}) => post<QueueItem>('/api/queue', body),
    update: (id: string, body: {scheduled_at?: string | null, status?: string}) => patch<QueueItem>(`/api/queue/${id}`, body),
    delete: (id: string) => del(`/api/queue/${id}`),
    calendar: () => get<CalendarDay[]>('/api/calendar'),
    shuffle: (selected_dates?: string[]) => post('/api/queue/shuffle', { selected_dates }),
  },
  scheduler: {
    start: (interval_hours: number) => post('/api/scheduler/start', {interval_hours}),
    stop: () => post('/api/scheduler/stop', {}),
    status: () => get<{running: boolean, interval_hours: number, last_run: string|null, next_run: string|null}>('/api/scheduler/status'),
  },
  upload: {
    youtube: (clip_id: string) => post(`/api/upload/youtube/${clip_id}`, {}),
    instagram: (clip_id: string) => post(`/api/upload/instagram/${clip_id}`, {}),
    tiktok: (clip_id: string) => post(`/api/upload/tiktok/${clip_id}`, {}),
  },
  auth: {
    youtubeUrl: () => get<{url: string}>('/api/auth/youtube/url'),
    youtubeStatus: () => get<{authenticated: boolean, email?: string}>('/api/auth/youtube/status'),
  },
  settings: {
    get: () => get<SettingsStatus>('/api/settings'),
    updateEnv: (key: string, value: string) => post('/api/settings/env', {key, value}),
    clearCache: () => post('/api/settings/cache/clear', {}),
    clearDatabase: (keep_channels?: boolean) => post('/api/settings/db/clear', {keep_channels}),
    disk: () => get<{total_bytes: number, clip_count: number}>('/api/settings/disk'),
    getScoring: () => get<import('../types').ScoringConfig>('/api/settings/scoring'),
    updateScoring: (body: Partial<import('../types').ScoringConfig>) => post<{updated: boolean}>('/api/settings/scoring', body),
  },
}
