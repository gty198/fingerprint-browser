import { useState } from 'react'
import { api } from '../api'
import type { Capabilities, Profile } from '../types'

const PLATFORMS = ['macos', 'windows', 'linux']
const TIMEZONES = [
  'America/New_York', 'America/Los_Angeles', 'Europe/London', 'Europe/Berlin',
  'Asia/Singapore', 'Asia/Tokyo', 'Asia/Shanghai', 'Australia/Sydney',
]
const LOCALES = ['en-US', 'en-GB', 'de-DE', 'en-SG', 'ja-JP', 'zh-CN', 'en-AU']

interface Props {
  profile: Profile | null   // null = 新建
  caps: Capabilities | null
  onClose: () => void
  onSaved: () => Promise<void>
  notify: (text: string, kind?: 'ok' | 'err') => void
}

export function ProfileModal({ profile, caps, onClose, onSaved, notify }: Props) {
  const isNew = profile === null
  const [name, setName] = useState(profile?.name ?? '')
  const [platform, setPlatform] = useState(profile?.platform ?? 'macos')
  const [timezone, setTimezone] = useState(profile?.timezone ?? '')
  const [locale, setLocale] = useState(profile?.locale ?? '')
  const [viewport, setViewport] = useState(
    profile?.viewport_width ? `${profile.viewport_width}×${profile.viewport_height}` : '',
  )
  const [cores, setCores] = useState(profile?.hardware_concurrency?.toString() ?? '')
  const [colorScheme, setColorScheme] = useState(profile?.color_scheme ?? 'light')
  const [humanize, setHumanize] = useState(profile?.humanize ?? false)
  const [proxy, setProxy] = useState(profile?.proxy_server ?? '')
  const [notes, setNotes] = useState(profile?.notes ?? '')
  const [busy, setBusy] = useState(false)

  const save = async () => {
    if (!name.trim()) return notify('请填写名称', 'err')
    setBusy(true)
    try {
      let w: number | undefined, h: number | undefined
      const m = viewport.match(/^(\d+)[x×](\d+)$/)
      if (m) { w = +m[1]; h = +m[2] }
      const body = {
        name: name.trim(),
        platform,
        timezone: timezone || null,
        locale: locale || null,
        viewport_width: w,
        viewport_height: h,
        hardware_concurrency: cores ? +cores : null,
        color_scheme: colorScheme,
        humanize,
        proxy_server: proxy || null,
        notes,
      }
      if (isNew) await api.createProfile(body)
      else await api.updateProfile(profile!.id, body)
      await onSaved()
    } catch (e) { notify((e as Error).message, 'err') }
    finally { setBusy(false) }
  }

  const regenerate = async () => {
    if (!profile) return
    try {
      const p = await api.regenerate(profile.id)
      setPlatform(p.platform ?? 'macos')
      setTimezone(p.timezone ?? '')
      setLocale(p.locale ?? '')
      setViewport(p.viewport_width ? `${p.viewport_width}×${p.viewport_height}` : '')
      setCores(p.hardware_concurrency?.toString() ?? '')
      setColorScheme(p.color_scheme ?? 'light')
      notify('已重新生成一套指纹(会避开其它 profile)')
    } catch (e) { notify((e as Error).message, 'err') }
  }

  const geoip = async () => {
    try {
      const r = await api.geoip(profile?.id ?? '', proxy, true)
      if (!r.ok) { notify(r.reason ?? 'geoip 失败', 'err'); return }
      if (r.timezone) setTimezone(r.timezone)
      if (r.locale) setLocale(r.locale)
      notify(`匹配到 ${r.country ?? ''} (${r.ip ?? ''}) 时区 ${r.timezone} 语言 ${r.locale}`)
    } catch (e) { notify((e as Error).message, 'err') }
  }

  const field = (label: string, supported: boolean) => (
    <span className="text-xs text-slate-400">
      {label}{supported ? '' : ' ⚠️免费版不生效'}
    </span>
  )

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-6 shadow-xl dark:bg-slate-900"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold">{isNew ? '新建 Profile' : `编辑「${profile!.name}」`}</h2>

        <label className="mb-3 block">
          <span className="mb-1 block text-sm font-medium">名称</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800"
            placeholder="例如: 账号-亚马逊-01"
          />
        </label>

        <div className="mb-3 grid grid-cols-2 gap-3">
          <label className="block">
            <span className="mb-1 block text-sm font-medium">{field('平台', caps?.platform ?? true)}</span>
            <select value={platform} onChange={(e) => setPlatform(e.target.value)} className="w-full rounded border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800">
              {PLATFORMS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium">{field('时区', caps?.timezone ?? true)}</span>
            <select value={timezone} onChange={(e) => setTimezone(e.target.value)} className="w-full rounded border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800">
              <option value="">自动</option>
              {TIMEZONES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium">{field('语言', caps?.locale ?? true)}</span>
            <select value={locale} onChange={(e) => setLocale(e.target.value)} className="w-full rounded border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800">
              <option value="">自动</option>
              {LOCALES.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium">{field('屏幕', caps?.screen ?? true)}</span>
            <input
              value={viewport}
              onChange={(e) => setViewport(e.target.value)}
              placeholder="1440×900"
              className="w-full rounded border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium">{field('硬件并发', caps?.hardware_concurrency ?? true)}</span>
            <input
              value={cores}
              onChange={(e) => setCores(e.target.value)}
              placeholder="自动"
              className="w-full rounded border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium">{field('配色', caps?.color_scheme ?? true)}</span>
            <select value={colorScheme} onChange={(e) => setColorScheme(e.target.value)} className="w-full rounded border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800">
              <option value="light">浅色</option>
              <option value="dark">深色</option>
              <option value="no-preference">跟随系统</option>
            </select>
          </label>
        </div>

        <label className="mb-1 block">
          <span className="mb-1 block text-sm font-medium">代理(HTTP/SOCKS5,可选)</span>
          <div className="flex gap-2">
            <input
              value={proxy}
              onChange={(e) => setProxy(e.target.value)}
              placeholder="http://user:pass@host:port"
              className="w-full rounded border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800"
            />
            <button onClick={geoip} className="shrink-0 rounded border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800" title="根据代理 IP 自动匹配时区/语言">
              按 IP 匹配
            </button>
          </div>
        </label>

        <label className="mb-3 block">
          <span className="mb-1 block text-sm font-medium">备注</span>
          <input value={notes} onChange={(e) => setNotes(e.target.value)} className="w-full rounded border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800" />
        </label>

        <label className="mb-4 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={humanize} onChange={(e) => setHumanize(e.target.checked)} className="h-4 w-4" />
          行为拟人(鼠标/键盘/滚动更像真人)
        </label>

        <div className="flex items-center justify-between">
          {!isNew && (
            <button onClick={regenerate} className="rounded border border-amber-400 px-3 py-2 text-sm text-amber-600 hover:bg-amber-50 dark:border-amber-600 dark:text-amber-400 dark:hover:bg-amber-950/30">
              重新生成指纹
            </button>
          )}
          <div className="ml-auto flex gap-2">
            <button onClick={onClose} className="rounded px-4 py-2 text-sm text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">取消</button>
            <button onClick={save} disabled={busy} className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50">
              {busy ? '保存中…' : '保存'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
