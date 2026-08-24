/**
 * Mock API 管理 API
 */
import { requestWithToken } from '../../common/request.js'

const BASE = '/api/mock_api'

/* ---- 规则 CRUD ---- */

/** 获取规则列表（支持 ?status=1 过滤启用） */
export async function getRules(status = '') {
  const query = status ? `?status=${status}` : ''
  const res = await requestWithToken(`${BASE}/rules/${query}`)
  return res.json()
}

/** 新增规则 */
export async function createRule(data) {
  const res = await requestWithToken(`${BASE}/rules/create/`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  return res.json()
}

/** 编辑规则 */
export async function updateRule(id, data) {
  const res = await requestWithToken(`${BASE}/rules/${id}/`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  return res.json()
}

/** 启用/停用规则 */
export async function toggleRuleStatus(id, status) {
  const res = await requestWithToken(`${BASE}/rules/${id}/status/`, {
    method: 'POST',
    body: JSON.stringify({ status }),
  })
  return res.json()
}

/** 删除规则 */
export async function deleteRule(id) {
  const res = await requestWithToken(`${BASE}/rules/${id}/delete/`, {
    method: 'POST',
  })
  return res.json()
}

/* ---- 代理控制 ---- */

/** 启动 Mock 代理 */
export async function startProxy(port = 8080, host = '0.0.0.0') {
  const res = await requestWithToken(`${BASE}/proxy/start/`, {
    method: 'POST',
    body: JSON.stringify({ port, host }),
  })
  return res.json()
}

/** 停止 Mock 代理（传入端口号用于兜底杀进程） */
export async function stopProxy(port = 8080) {
  const res = await requestWithToken(`${BASE}/proxy/stop/`, {
    method: 'POST',
    body: JSON.stringify({ port }),
  })
  return res.json()
}

/** 查询代理状态 */
export async function getProxyStatus() {
  const res = await requestWithToken(`${BASE}/proxy/status/`)
  return res.json()
}

/** 热加载规则 */
export async function reloadProxy() {
  const res = await requestWithToken(`${BASE}/proxy/reload/`, {
    method: 'POST',
  })
  return res.json()
}

/* ---- 数据库连接配置 ---- */

/** 获取数据库连接配置列表 */
export async function getDbConfigs() {
  const res = await requestWithToken(`${BASE}/db_configs/`)
  return res.json()
}

/** 新增数据库连接配置 */
export async function createDbConfig(data) {
  const res = await requestWithToken(`${BASE}/db_configs/create/`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  return res.json()
}

/** 编辑数据库连接配置 */
export async function updateDbConfig(id, data) {
  const res = await requestWithToken(`${BASE}/db_configs/${id}/`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  return res.json()
}

/** 删除数据库连接配置 */
export async function deleteDbConfig(id) {
  const res = await requestWithToken(`${BASE}/db_configs/${id}/delete/`, {
    method: 'POST',
  })
  return res.json()
}

/* ---- 规则测试 ---- */

/** 测试 URL 匹配规则 */
export async function testMatch(data) {
  const res = await requestWithToken(`${BASE}/rules/test_match/`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  return res.json()
}
