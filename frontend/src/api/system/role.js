import { requestWithToken } from '../../common/request.js'

const BASE = '/api/role_management'

export async function fetchRoleList() {
  const res = await requestWithToken(`${BASE}/roles/`)
  return res.json()
}

export async function fetchMenuOptions() {
  const res = await requestWithToken(`${BASE}/menus/options/`)
  return res.json()
}

export async function createRole(body) {
  const res = await requestWithToken(`${BASE}/roles/create/`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  return res.json()
}

export async function updateRole(id, body) {
  const res = await requestWithToken(`${BASE}/roles/${id}/`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
  return res.json()
}

export async function deleteRole(id) {
  const res = await requestWithToken(`${BASE}/roles/${id}/delete/`, {
    method: 'POST',
  })
  return res.json()
}
