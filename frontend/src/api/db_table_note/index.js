import { requestWithToken } from '../../common/request.js'

const BASE = '/api/db_table_note'

/** 连接配置列表（脱敏，不含密码） */
export async function fetchConnectionList() {
  const res = await requestWithToken(`${BASE}/connections/`)
  return res.json()
}

/** 新增/编辑连接配置（编辑时 password 留空表示保持原密码） */
export async function saveConnection(body) {
  const res = await requestWithToken(`${BASE}/connections/save/`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  return res.json()
}

/** 删除连接配置 */
export async function deleteConnection(id) {
  const res = await requestWithToken(`${BASE}/connections/delete/`, {
    method: 'POST',
    body: JSON.stringify({ id }),
  })
  return res.json()
}

/** 获取连接下所有表（表名 + 注释） */
export async function fetchTableList(connectionId, keyword = '') {
  const res = await requestWithToken(
    `${BASE}/tables/?connection_id=${encodeURIComponent(connectionId)}&keyword=${encodeURIComponent(keyword)}`
  )
  return res.json()
}

/** 获取某表的备注与执行 SQL */
export async function fetchTableNote(connectionId, tableName) {
  const res = await requestWithToken(
    `${BASE}/note/?connection_id=${encodeURIComponent(connectionId)}&table_name=${encodeURIComponent(tableName)}`
  )
  return res.json()
}

/** 按需加载某表字段注释（含手动备注拼接结果） */
export async function fetchTableFields(connectionId, tableName) {
  const res = await requestWithToken(
    `${BASE}/fields/?connection_id=${encodeURIComponent(connectionId)}&table_name=${encodeURIComponent(tableName)}`
  )
  return res.json()
}

/** 保存某表的备注、执行 SQL 与字段手动备注 */
export async function saveTableNote(body) {
  const res = await requestWithToken(`${BASE}/note/save/`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  return res.json()
}

/** 执行 SQL（查询返回结果集；UPDATE/DELETE 无 WHERE 时需 force=true） */
export async function executeSql(connectionId, sql, force = false) {
  const res = await requestWithToken(`${BASE}/sql/execute/`, {
    method: 'POST',
    body: JSON.stringify({ connection_id: connectionId, sql, force }),
  })
  return res.json()
}
