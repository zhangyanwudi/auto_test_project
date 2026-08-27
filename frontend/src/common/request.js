/**
 * 公共请求与 token：token 存取、过期校验、带 token 的请求及 401 统一处理。
 * 后续新增需要登录的接口时，直接使用 requestWithToken 即可自动带 token 并处理过期。
 */
const TOKEN_KEY = 'admin_token'
const EXPIRES_AT_KEY = 'admin_token_expires_at'
const USERNAME_KEY = 'admin_username'
const USER_CN_NAME_KEY = 'admin_user_cn_name'
const IS_SUPER_ADMIN_KEY = 'admin_is_super_admin'
const PAGE_TITLE_KEY = 'admin_page_title'
const SSO_ENABLED_KEY = 'admin_sso_enabled'

/** 401 时的回调 (message: string) => void，在 main.js 中设置为提示并跳转登录 */
let onUnauthorized = () => {}

/**
 * 开发环境默认把 /api 直连到 Django，绕开 Vite 代理。
 * 大响应（如配置比对 get_adwaynum_file）经代理时，曾出现「后端已处理完、浏览器 Network 仍 pending」。
 * 若必须走 Vite 代理，在 .env.development 设置 VITE_USE_VITE_PROXY=1；非 8000 端口用 VITE_DEV_API_ORIGIN。
 */
function resolveRequestUrl(url) {
  if (!url || typeof url !== 'string' || !url.startsWith('/api')) return url
  try {
    if (!import.meta.env?.DEV) return url
    if (String(import.meta.env.VITE_USE_VITE_PROXY || '') === '1') return url

    // 自动获取当前页面 host 的 IP，替代写死的 127.0.0.1
    const host = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
      ? '127.0.0.1'
      : window.location.hostname  // 局域网 IP，如 192.168.1.105

    const origin = String(import.meta.env.VITE_DEV_API_ORIGIN || `http://${host}:8000`).replace(
      /\/$/,
      ''
    )
    return `${origin}${url}`
  } catch {
    return url
  }
}

export function setOnUnauthorized(fn) {
  onUnauthorized = fn
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function getExpiresAt() {
  const s = localStorage.getItem(EXPIRES_AT_KEY)
  return s ? new Date(s) : null
}

export function setToken(data) {
  if (data.token) localStorage.setItem(TOKEN_KEY, data.token)
  if (data.expires_at) localStorage.setItem(EXPIRES_AT_KEY, data.expires_at)
  if (data.username) localStorage.setItem(USERNAME_KEY, data.username)
  if (data.user_cn_name != null && data.user_cn_name !== '') {
    localStorage.setItem(USER_CN_NAME_KEY, data.user_cn_name)
  }
  if (data.is_super_admin != null) {
    localStorage.setItem(IS_SUPER_ADMIN_KEY, data.is_super_admin ? '1' : '0')
  }
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(EXPIRES_AT_KEY)
  localStorage.removeItem(USERNAME_KEY)
  localStorage.removeItem(USER_CN_NAME_KEY)
  localStorage.removeItem(IS_SUPER_ADMIN_KEY)
}

export function getUsername() {
  return localStorage.getItem(USERNAME_KEY) || ''
}

/** 库中 user_cn_name，用于欢迎语等；若无则回退登录名 */
export function getUserCnName() {
  return localStorage.getItem(USER_CN_NAME_KEY) || getUsername() || ''
}

/** 是否为超级管理员角色（role_code=super_admin），用于前端隐藏删除等操作 */
export function isSuperAdmin() {
  return localStorage.getItem(IS_SUPER_ADMIN_KEY) === '1'
}

/** token_check 返回后同步本地展示名 */
export function syncUserProfileFromTokenData(data) {
  if (!data) return
  if (data.username) localStorage.setItem(USERNAME_KEY, data.username)
  if (data.user_cn_name != null && data.user_cn_name !== '') {
    localStorage.setItem(USER_CN_NAME_KEY, data.user_cn_name)
  }
  if (data.is_super_admin != null) {
    localStorage.setItem(IS_SUPER_ADMIN_KEY, data.is_super_admin ? '1' : '0')
  }
}

/** token 是否已过期（按本地过期时间判断） */
export function isTokenExpired() {
  const expiresAt = getExpiresAt()
  if (!expiresAt) return true
  return new Date() >= new Date(expiresAt)
}

/**
 * 带 token 且统一处理 401 的请求方法。
 * 自动附加 Authorization: Bearer <token>，若响应 401 则清除 token、执行 onUnauthorized 并抛错。
 * 后续新增接口只需调用此方法即可实现带 token 与过期处理。
 *
 * @param {string} url - 请求地址
 * @param {RequestInit} [options={}] - fetch 的 options
 * @returns {Promise<Response>} - fetch 的 Response，需自行 .json() 等
 */
export async function requestWithToken(url, options = {}) {
  const token = getToken()
  const isFormData =
    typeof FormData !== 'undefined' && options.body instanceof FormData
  const headers = { ...options.headers }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const method = String(options.method || 'GET').toUpperCase()
  // FormData 必须由浏览器自动带 multipart boundary，不能写死 application/json
  // GET/HEAD 不要默认加 application/json（与 Postman 等工具一致），避免个别代理/服务端对无 body 的 JSON Content-Type 处理异常
  if (
    !isFormData &&
    method !== 'GET' &&
    method !== 'HEAD' &&
    headers['Content-Type'] === undefined
  ) {
    headers['Content-Type'] = 'application/json'
  }

  const resolvedUrl = resolveRequestUrl(url)
  const fetchInit = { ...options, headers }
  if (fetchInit.cache === undefined && method === 'GET') {
    fetchInit.cache = 'no-store'
  }

  let res
  try {
    res = await fetch(resolvedUrl, fetchInit)
  } catch (e) {
    // GET/HEAD 幂等：网络错误（如后端 runserver 热重载瞬间）自动重试一次
    if (method === 'GET' || method === 'HEAD') {
      await new Promise((r) => setTimeout(r, 800))
      try {
        res = await fetch(resolvedUrl, fetchInit)
      } catch (e2) {
        console.error('[request] fetch 失败:', resolvedUrl, e2)
        throw new Error('网络请求失败，请检查服务是否正常')
      }
    } else {
      console.error('[request] fetch 失败:', resolvedUrl, e)
      throw new Error('网络请求失败，请检查服务是否正常')
    }
  }

  if (res.status === 401) {
    clearToken()
    const data = await res.json().catch(() => ({}))
    const msg = data.message || '登录已过期，请重新登录'
    onUnauthorized(msg)
    throw new Error(msg)
  }

  return res
}

/**
 * 获取页面配置（公开接口，无需登录），缓存到 localStorage。
 * 失败时静默回退，后续 getPageTitle() 使用默认值。
 */
export async function fetchPageConfig() {
  try {
    const url = resolveRequestUrl('/api/common/page_config/')
    const res = await fetch(url, { cache: 'no-store' })
    if (!res.ok) return
    const json = await res.json()
    if (json.code === 0 && json.data) {
      if (json.data.page_tile_name) {
        localStorage.setItem(PAGE_TITLE_KEY, json.data.page_tile_name)
      }
      if (json.data.sso_enabled != null) {
        localStorage.setItem(
          SSO_ENABLED_KEY,
          json.data.sso_enabled ? '1' : '0'
        )
      }
    }
  } catch {
    // 静默失败，使用默认标题
  }
}

/**
 * 获取页面标题，优先从 localStorage 读取缓存值，无缓存时返回默认值。
 * @returns {string} 页面标题
 */
export function getPageTitle() {
  return localStorage.getItem(PAGE_TITLE_KEY) || '测试平台'
}

/** 统一 SSO 登录开关是否开启（默认 false，无配置时不显示入口） */
export function isSsoEnabled() {
  return localStorage.getItem(SSO_ENABLED_KEY) === '1'
}
