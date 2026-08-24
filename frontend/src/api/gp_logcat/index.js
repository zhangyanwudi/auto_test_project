/**
 * GP 商业化日志 API
 */
import { requestWithToken, getToken } from '../../common/request.js'

const BASE = '/api/gp_logcat'

function getBackendOrigin() {
  try {
    if (import.meta.env?.DEV && String(import.meta.env.VITE_USE_VITE_PROXY || '') !== '1') {
      const host = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
        ? '127.0.0.1'
        : window.location.hostname
      return String(import.meta.env.VITE_DEV_API_ORIGIN || `http://${host}:8000`).replace(/\/$/, '')
    }
  } catch { /* non-Vite */ }
  return `${window.location.protocol}//${window.location.host}`
}

/* ---- SSE 流 ---- */

export function getStreamUrl() {
  const token = getToken()
  if (!token) return null

  let origin = ''
  try {
    if (import.meta.env?.DEV && String(import.meta.env.VITE_USE_VITE_PROXY || '') !== '1') {
      const host = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
        ? '127.0.0.1'
        : window.location.hostname
      origin = String(import.meta.env.VITE_DEV_API_ORIGIN || `http://${host}:8000`).replace(/\/$/, '')
    }
  } catch { /* non-Vite */ }

  return `${origin}${BASE}/stream/?token=${encodeURIComponent(token)}`
}

/**
 * 一键启动本地代理的 bootstrap URL
 * @param {'sh'|'command'|'bat'} format
 */
export function getAgentBootstrapUrl(format = 'sh') {
  const token = getToken() || ''
  const server = getBackendOrigin()
  const qs = new URLSearchParams({
    token,
    server,
    format,
  })
  return `${server}${BASE}/agent/bootstrap/?${qs.toString()}`
}

/** 终端一键启动命令（检测 Python → 下载代理 → 启动） */
export function getAgentOneClickCommand() {
  const url = getAgentBootstrapUrl('sh')
  return `curl -fsSL "${url}" | bash`
}

/* ---- 启停控制 ---- */

/** 启动 adb logcat（mode: 'server' | 'local'） */
export async function startLogcat(filter = '', mode = 'server') {
  const res = await requestWithToken(`${BASE}/start/`, {
    method: 'POST',
    body: JSON.stringify({ filter, mode }),
  })
  return res.json()
}

/** 停止服务器端 adb logcat */
export async function stopLogcat() {
  const res = await requestWithToken(`${BASE}/stop/`, {
    method: 'POST',
  })
  return res.json()
}

/* ---- 辅助 ---- */

/** 查询日志缓冲区及 adb 状态 */
export async function getStatus() {
  const res = await requestWithToken(`${BASE}/status/`)
  return res.json()
}

/** 清空日志缓冲区 */
export async function clearLogs() {
  const res = await requestWithToken(`${BASE}/clear/`, { method: 'POST' })
  return res.json()
}
