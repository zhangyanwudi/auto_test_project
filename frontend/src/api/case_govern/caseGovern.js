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

/** 生成用例分享链接 token（后端签名，URL 不可预测） */
export async function fetchShareToken(id) {
  const res = await requestWithToken(`${BASE}/cases/${id}/share_token/`)
  return res.json()
}

/** 校验分享 token，返回 { case_id, case_name } */
export async function verifyShareToken(token) {
  const res = await requestWithToken(`${BASE}/cases/share_verify/?token=${encodeURIComponent(token)}`)
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

/** 更新单个节点的执行结果（非创建人查看时也可标记通过/不通过） */
export async function updateNodeExecResult(id, nodeId, execResult) {
  const res = await requestWithToken(`${BASE}/cases/${id}/mind/exec/`, {
    method: 'POST',
    body: JSON.stringify({ node_id: nodeId, exec_result: execResult }),
  })
  return res.json()
}

/** 导出用例为 .xmind 文件（返回 Blob） */
export async function exportXmindFile(id) {
  const res = await requestWithToken(`${BASE}/cases/${id}/export_xmind/`, {
    method: 'GET',
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.message || '导出失败')
  }
  return res.blob()
}

/** 导入思维导图（.emmx / .xmind），后端按扩展名自动区分解析方式 */
export async function importCaseFromFile(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await requestWithToken(`${BASE}/cases/import/`, {
    method: 'POST',
    body: form,
  })
  return res.json()
}
