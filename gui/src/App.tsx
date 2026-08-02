import { useCallback, useEffect, useRef, useState } from 'react'
import { api, fmtUptime } from './api'
import type { Capabilities, Profile, RunningItem } from './types'
import { ProfileModal } from './components/ProfileModal'

const PLATFORM_LABEL: Record<string, string> = {
  macos: 'macOS', windows: 'Windows', linux: 'Linux',
}
const CAP_LABELS: [keyof Capabilities, string][] = [
  ['platform', '平台/UA'], ['hardware_concurrency', '硬件并发'], ['timezone', '时区'],
  ['locale', '语言'], ['screen', '屏幕'], ['color_scheme', '配色'], ['fingerprint_seed', '噪声种子'],
]

interface Toast { id: number; text: string; kind: 'ok' | 'err' }

export default function App() {
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [running, setRunning] = useState<Map<string, RunningItem>>(new Map())
  const [caps, setCaps] = useState<Capabilities | null>(null)
  const [engineName, setEngineName] = useState('')
  const [editing, setEditing] = useState<Profile | 'new' | null>(null)
  const [toasts, setToasts] = useState<Toast[]>([])
  const toastId = useRef(0)

  const notify = useCallback((text: string, kind: 'ok' | 'err' = 'ok') => {
    const id = ++toastId.current
    setToasts((t) => [...t, { id, text, kind }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3500)
  }, [])

  const refresh = useCallback(async () => {
    try {
      const [ps, rs] = await Promise.all([api.profiles(), api.running()])
      setProfiles(ps)
      setRunning(new Map(rs.running.map((r) => [r.profile_id, r])))
    } catch (e) {
      notify(`后端未连接: ${(e as Error).message}`, 'err')
    }
  }, [notify])

  // 引擎信息只拉一次;profile/运行状态每 2s 轮询
  useEffect(() => {
    api.engine().then((e) => { setCaps(e.capabilities); setEngineName(e.name) }).catch(() => {})
    refresh()
    const t = setInterval(refresh, 2000)
    return () => clearInterval(t)
  }, [refresh])

  const launch = async (p: Profile) => {
    try {
      const r = await api.launch(p.id, false)
      if (r.status === 'launched') notify(`「${p.name}」已启动`)
      else if (r.status === 'already_running') notify(`「${p.name}」已在运行`)
      else notify(`启动失败: ${r.status}`, 'err')
      refresh()
    } catch (e) { notify((e as Error).message, 'err') }
  }
  const stop = async (p: Profile) => {
    try {
      await api.close(p.id)
      notify(`「${p.name}」已停止`)
      refresh()
    } catch (e) { notify((e as Error).message, 'err') }
  }
  const remove = async (p: Profile) => {
    if (!confirm(`删除 profile「${p.name}」?其浏览器数据(独立目录)将一并删除。`)) return
    try { await api.deleteProfile(p.id); notify('已删除'); refresh() }
    catch (e) { notify((e as Error).message, 'err') }
  }
  const exportCookies = async (p: Profile) => {
    try {
      const r = await api.cookies(p.id)
      const blob = new Blob([JSON.stringify(r.cookies, null, 2)], { type: 'application/json' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `${p.name}-cookies.json`
      a.click()
      URL.revokeObjectURL(a.href)
      notify(`导出 ${r.cookies.length} 条 cookie`)
    } catch (e) { notify((e as Error).message, 'err') }
  }
  const importCookies = async (p: Profile) => {
    const input = document.createElement('input')
    input.type = 'file'; input.accept = '.json,application/json'
    input.onchange = async () => {
      const f = input.files?.[0]; if (!f) return
      try {
        const arr = JSON.parse(await f.text())
        if (!Array.isArray(arr)) throw new Error('cookie 文件应为数组')
        const r = await api.importCookies(p.id, arr)
        notify(`导入 ${r.imported} 条 cookie`)
      } catch (e) { notify((e as Error).message, 'err') }
    }
    input.click()
  }

  const unsupported = caps ? Object.entries(caps).filter(([, v]) => !v).map(([k]) => k) : []

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      {/* 顶部 */}
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">指纹浏览器</h1>
          <p className="text-sm text-slate-500">
            引擎 <span className="font-mono">{engineName || '…'}</span>
            {' · '}已开 <span className="font-semibold text-emerald-600">{running.size}</span> 个
          </p>
        </div>
        <button
          onClick={() => setEditing('new')}
          className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white shadow hover:bg-indigo-500"
        >
          + 新建 Profile
        </button>
      </header>

      {/* 引擎能力提示 */}
      {unsupported.length > 0 && (
        <div className="mb-6 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200">
          ⚠️ 当前引擎免费版不支持:{' '}
          {unsupported.map((k) => CAP_LABELS.find(([x]) => x === k)?.[1] ?? k).join('、')}。
          这些维度将沿用宿主机真实值(语言固定为系统语言,Mac 屏幕固定)。
        </div>
      )}

      {/* Profile 列表 */}
      {profiles.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 p-16 text-center text-slate-400">
          还没有 Profile。点右上角「新建 Profile」开始 —— 每个 Profile 是一套独立指纹 + 独立浏览器数据。
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {profiles.map((p) => {
            const r = running.get(p.id)
            return (
              <div key={p.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <div className="mb-2 flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">{p.name}</span>
                      <span className={`rounded px-1.5 py-0.5 text-xs ${r ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' : 'bg-slate-100 text-slate-500 dark:bg-slate-800'}`}>
                        {r ? `运行中 ${fmtUptime(r.uptime_seconds)}` : '已停止'}
                      </span>
                    </div>
                    <div className="mt-0.5 text-xs text-slate-400">ID {p.id}</div>
                  </div>
                  {p.platform && (
                    <span className="rounded bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-600 dark:bg-indigo-950/50 dark:text-indigo-300">
                      {PLATFORM_LABEL[p.platform] ?? p.platform}
                    </span>
                  )}
                </div>

                <dl className="mb-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                  <dt className="text-slate-400">时区</dt><dd className="text-right font-mono">{p.timezone ?? '—'}</dd>
                  <dt className="text-slate-400">语言</dt><dd className="text-right font-mono">{p.locale ?? '—'}</dd>
                  <dt className="text-slate-400">屏幕</dt>
                  <dd className="text-right font-mono">{p.viewport_width ? `${p.viewport_width}×${p.viewport_height}` : '—'}</dd>
                  <dt className="text-slate-400">核心</dt><dd className="text-right font-mono">{p.hardware_concurrency ?? '—'}</dd>
                  <dt className="text-slate-400">代理</dt>
                  <dd className="truncate text-right font-mono" title={p.proxy_server ?? ''}>{p.proxy_server ? '✓ 已配置' : '未配置'}</dd>
                  <dt className="text-slate-400">行为拟人</dt><dd className="text-right">{p.humanize ? '开' : '关'}</dd>
                </dl>

                <div className="flex flex-wrap gap-2">
                  {r ? (
                    <button onClick={() => stop(p)} className="rounded bg-rose-600 px-3 py-1.5 text-sm text-white hover:bg-rose-500">停止</button>
                  ) : (
                    <button onClick={() => launch(p)} className="rounded bg-emerald-600 px-3 py-1.5 text-sm text-white hover:bg-emerald-500">启动</button>
                  )}
                  <button onClick={() => setEditing(p)} className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">编辑</button>
                  <button onClick={() => exportCookies(p)} className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800" title="导出 Cookie(需先启动)">导出 Cookie</button>
                  <button onClick={() => importCookies(p)} className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800" title="导入 Cookie(需先启动)">导入</button>
                  <button onClick={() => remove(p)} className="ml-auto rounded px-2 py-1.5 text-sm text-slate-400 hover:bg-slate-100 hover:text-rose-600 dark:hover:bg-slate-800">删除</button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* 新建/编辑弹窗 */}
      {editing !== null && (
        <ProfileModal
          profile={editing === 'new' ? null : editing}
          caps={caps}
          onClose={() => setEditing(null)}
          onSaved={async () => { setEditing(null); await refresh(); notify('已保存') }}
          notify={notify}
        />
      )}

      {/* Toast */}
      <div className="pointer-events-none fixed bottom-6 right-6 z-50 flex flex-col gap-2">
        {toasts.map((t) => (
          <div key={t.id} className={`pointer-events-auto rounded-lg px-4 py-2 text-sm text-white shadow-lg ${t.kind === 'ok' ? 'bg-slate-800 dark:bg-slate-700' : 'bg-rose-600'}`}>
            {t.text}
          </div>
        ))}
      </div>
    </div>
  )
}
