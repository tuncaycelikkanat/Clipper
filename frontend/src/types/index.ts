export interface PipelineJob {
  id: string
  video_url: string
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
  progress: number
  current_step: string | null
  result: Clip[] | null
  logs?: { time?: string; step?: string; progress?: number; message: string }[]
  error_msg: string | null
  created_at: string
  updated_at: string
}

export interface Clip {
  id: string
  video_id: string
  rank: number
  title: string
  description: string | null
  tags: string | null
  hook_caption: string | null
  category: string | null
  start_time: number
  end_time: number
  duration: number
  score: number
  score_band?: string | null
  rationale?: string | null
  signals?: Record<string, any> | null
  thumbnail_path: string | null
  render_path: string | null
  render_mode: string | null
  has_facecam: boolean
  created_at: string
  publish_status?: string | null
  scheduled_at?: string | null
}

export interface Video {
  id: string
  url: string
  title: string
  uploader: string
  duration: number
  upload_date: string | null
  view_count: number
  status: 'pending' | 'processing' | 'done' | 'failed'
  clip_count?: number
  process_after?: string | null
  delay_hours?: number
}

export interface VideoPreview {
  id: string
  url?: string
  title: string
  uploader: string
  duration: number
  duration_formatted: string
  thumbnail: string | null
  view_count?: number
  duration_minutes: number
  recommended_clips: number
  clip_range?: string
  tier_label: string
  explanation: string
  ranges?: number[]
}

export interface Channel {
  id: string
  url: string
  name: string
  is_tracked: boolean
  active: boolean
  min_score: number
  check_interval_h: number
  auto_upload: boolean
  last_checked: string | null
  last_video_id: string | null
}

export interface QueueItem {
  id: string
  clip_id: string
  channel_id: string | null
  scheduled_at: string | null
  status: 'pool' | 'scheduled' | 'publishing' | 'published' | 'failed' | 'cancelled'
  youtube_url: string | null
  instagram_url: string | null
  tiktok_url: string | null
  title: string
  viral_score?: number
  render_path?: string | null
  thumbnail_path?: string | null
  description?: string | null
  created_at: string
}

export interface CalendarDay {
  date: string
  label: string
  slots: {
    time: string
    item: QueueItem | null
  }[]
}

export interface SSEProgressEvent {
  step: string
  progress: number
  message: string
}

export interface PipelineRunRequest {
  url: string;
  target_clips?: number;
  render_mode?: string;
  add_subtitles?: boolean;
  add_hook_card?: boolean;
  enhance_colors?: boolean;
  api_key?: string | null;
}

export interface SettingsStatus {
  youtube_connected: boolean;
  gemini_key_set: boolean;
  openrouter_key_set: boolean;
  instagram_configured: boolean;
  tiktok_configured: boolean;
}

export interface CreateChannelRequest {
  url: string;
  name: string;
  min_score?: number;
  check_interval_h?: number;
  auto_upload?: boolean;
  target_playlist?: string;
}

export interface ScoringConfig {
  hook_strength_weight: number;
  emotion_weight: number;
  story_completeness_weight: number;
  signal_validation_weight: number;
  categories: string[];
  score_bands: { label: string; min: number; max: number }[];
  band_labels_enabled: boolean;
  ensemble_runs: number;
  mundane_score_cap: number;
}
