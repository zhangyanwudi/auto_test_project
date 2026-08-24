/**
 * 菜单管理 API（自动带 token，见 common/request.js）
 */
import { requestWithToken } from '../../common/request.js'

const BASE = '/api/menu_management'

/** 侧栏：仅启用菜单，用于动态渲染导航 */
export async function fetchSidebarMenuList() {
  const res = await requestWithToken(`${BASE}/menus/?enabled_only=1`)
  return res.json()
}

export async function fetchMenuList() {
  const res = await requestWithToken(`${BASE}/menus/`)
  return res.json()
}

export async function createMenu(body) {
  const res = await requestWithToken(`${BASE}/menus/create/`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  return res.json()
}

export async function updateMenu(id, body) {
  const res = await requestWithToken(`${BASE}/menus/${id}/`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
  return res.json()
}

export async function setMenuStatus(id, status) {
  const res = await requestWithToken(`${BASE}/menus/${id}/status/`, {
    method: 'POST',
    body: JSON.stringify({ status }),
  })
  return res.json()
}

/** 删除菜单（后端要求：已停用且无子菜单） */
export async function deleteMenu(id) {
  const res = await requestWithToken(`${BASE}/menus/${id}/delete/`, {
    method: 'POST',
  })
  return res.json()
}
