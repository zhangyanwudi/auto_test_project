import { requestWithToken } from '../../common/request.js'

const BASE = '/api/case_govern'

/** 列出启用的模块（供下拉选择） */
export async function fetchModuleList() {
  const res = await requestWithToken(`${BASE}/modules/`)
  return res.json()
}

/** 用例列表（含节点数） */
export async function fetchCaseList() {
  const res = await requestWithToken(`${BASE}/cases/`)
  return res.json()
}

export async function createCase(body) {
  const res = await requestWithToken(`${BASE}/cases/create/`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  return res.json()
}

export async function updateCase(id, body) {
  const res = await requestWithToken(`${BASE}/cases/${id}/`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
  return res.json()
}

export async function deleteCase(id) {
  const res = await requestWithToken(`${BASE}/cases/${id}/delete/`, {
    method: 'POST',
  })
  return res.json()
}

/** 获取用例的思维导图树 */
export async function fetchMindTree(id) {
  const res = await requestWithToken(`${BASE}/cases/${id}/mind/`)
  return res.json()
}

/** 保存思维导图（整棵树全量替换） */
export async function saveMindTree(id, tree) {
  const res = await requestWithToken(`${BASE}/cases/${id}/mind/save/`, {
    method: 'POST',
    body: JSON.stringify({ tree }),
  })
  return res.json()
}

/** 导入 MindMaster（.emmx）思维导图，创建用例及节点 */
export async function importCaseFromEmmx(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await requestWithToken(`${BASE}/cases/import_emmx/`, {
    method: 'POST',
    body: form,
  })
  return res.json()
}
