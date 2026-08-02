export interface Profile {
  id: string
  name: string
  user_data_dir: string
  user_agent: string | null
  platform: string | null
  timezone: string | null
  locale: string | null
  viewport_width: number | null
  viewport_height: number | null
  color_scheme: string | null
  hardware_concurrency: number | null
  humanize: boolean
  proxy_server: string | null
  notes: string
  created_at: number
  updated_at: number
  fingerprint_ready: boolean
}

export interface RunningItem {
  profile_id: string
  engine: string
  uptime_seconds: number
}

export interface Capabilities {
  platform: boolean
  user_agent: boolean
  hardware_concurrency: boolean
  timezone: boolean
  color_scheme: boolean
  fingerprint_seed: boolean
  locale: boolean
  screen: boolean
  [k: string]: boolean
}

export interface GeoipResult {
  ok: boolean
  timezone?: string
  locale?: string
  country?: string
  ip?: string
  reason?: string
}
