/**
 * 用户管理 API（z_user）
 */
import { requestWithToken } from '../../common/request.js'

const BASE = '/api/user_management'

export async function fetchUserList() {
  const res = await requestWithToken(`${BASE}/users/`)
  return res.json()
}

export async function createUser(body) {
  const res = await requestWithToken(`${BASE}/users/create/`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  return res.json()
}

export async function updateUser(id, body) {
  const res = await requestWithToken(`${BASE}/users/${id}/`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
  return res.json()
}

export async function deleteUser(id) {
  const res = await requestWithToken(`${BASE}/users/${id}/delete/`, {
    method: 'POST',
  })
  return res.json()
}

export async function changeUserPassword(id, newPassword) {
  const res = await requestWithToken(`${BASE}/users/${id}/password/`, {
    method: 'POST',
    body: JSON.stringify({ new_password: newPassword }),
  })
  return res.json()
}
