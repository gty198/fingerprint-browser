import type { Capabilities, GeoipResult, Profile, RunningItem } from './types'

// 开发环境(vite)有 /api 代理,用相对路径即可;
// 生产打包后没有代理,必须直连后端绝对地址,否则 fetch('/api') 会打到
// tauri://localhost 资源协议上 → WKWebView 报 "The string did not match the expected pattern"。
const BASE = import.meta.env.DEV ? '' : 'http://127.0.0.1:8000'

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}/api${path}`, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const d = await res.json()
      detail = d.detail ?? detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  health: () => req<{ status: string }>('GET', '/health'),
  engine: () => req<{ name: string; capabilities: Capabilities; binary: string }>('GET', '/engine'),
  profiles: () => req<Profile[]>('GET', '/profiles'),
  profile: (id: string) => req<Profile>('GET', `/profiles/${id}`),
  createProfile: (body: Partial<Profile> & { name: string }) => req<Profile>('POST', '/profiles', body),
  updateProfile: (id: string, body: Partial<Profile>) => req<Profile>('PATCH', `/profiles/${id}`, body),
  deleteProfile: (id: string) => req<void>('DELETE', `/profiles/${id}`),
  regenerate: (id: string) => req<Profile>('POST', `/profiles/${id}/fingerprint/regenerate`),
  launch: (id: string, headless = false, openUrl?: string) =>
    req<{ status: string; profile_id: string }>('POST', `/profiles/${id}/launch`, { headless, open_url: openUrl }),
  close: (id: string) => req<{ closed: boolean }>('POST', `/profiles/${id}/close`),
  running: () => req<{ running: RunningItem[] }>('GET', '/running'),
  geoip: (id: string, proxyServer?: string, apply = false) =>
    req<GeoipResult>('POST', `/profiles/${id}/geoip`, { proxy_server: proxyServer, apply }),
  cookies: (id: string) => req<{ cookies: Record<string, unknown>[] }>('GET', `/profiles/${id}/cookies`),
  importCookies: (id: string, cookies: Record<string, unknown>[]) =>
    req<{ imported: number }>('POST', `/profiles/${id}/cookies`, { cookies }),
}

export function fmtUptime(sec: number): string {
  if (sec < 60) return `${sec}s`
  const m = Math.floor(sec / 60)
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  return `${h}h${m % 60}m`
}

export function fmtDate(ts: number): string {
  return new Date(ts * 1000).toLocaleString('zh-CN', { hour12: false })
}
