/**
 * 登录相关 API：仅封装登录请求，token 存取与带 token 请求见 common/request.js
 */
import { setToken } from '../common/request.js'

const LOGIN_URL = '/api/login/login/'
const SSO_LOGIN_URL = '/api/login/youxi123/login_url/'
const VERIFY_TICKET_URL = '/api/login/youxi123/verify_ticket/'

/**
 * 登录请求：校验用户名密码，成功则写入 token 并返回接口数据。
 * @param {{ username: string, password: string }} params
 * @returns {Promise<{ code: number, message?: string, data?: { token, expires_at, username } }>}
 */
export async function login(params) {
  const res = await fetch(LOGIN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username: (params.username || '').trim(),
      password: params.password || '',
    }),
  })
  const data = await res.json()

  if (data.code === 0 && data.data) {
    setToken({
      token: data.data.token,
      expires_at: data.data.expires_at,
      username: data.data.username,
      user_cn_name: data.data.user_cn_name,
      is_super_admin: data.data.is_super_admin,
    })
  }

  return data
}

/**
 * 获取 youxi123 统一 SSO 登录地址（开关开启且已配置时返回）。
 * @returns {Promise<{ code: number, message?: string, data?: { login_url: string } }>}
 */
export async function getSsoLoginUrl() {
  const res = await fetch(SSO_LOGIN_URL, { cache: 'no-store' })
  return res.json()
}

/**
 * 用 SSO 回调返回的 ticket 换取登录 token（成功则写入 token）。
 * @param {string} ticket
 * @returns {Promise<{ code: number, message?: string, data?: { token, expires_at, username } }>}
 */
export async function verifySsoTicket(ticket) {
  const res = await fetch(VERIFY_TICKET_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticket }),
  })
  const data = await res.json()

  if (data.code === 0 && data.data) {
    setToken({
      token: data.data.token,
      expires_at: data.data.expires_at,
      username: data.data.username,
      user_cn_name: data.data.user_cn_name,
      is_super_admin: data.data.is_super_admin,
    })
  }

  return data
}
