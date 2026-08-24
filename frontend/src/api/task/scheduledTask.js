import { requestWithToken } from '../../common/request.js'

const BASE = '/api/scheduled_task'

/** 列出 backend/task_file 目录下文件名（全量，由前端缓存与筛选） */
export async function fetchTaskFileNames() {
  const res = await requestWithToken(`${BASE}/task_files/`)
  return res.json()
}

export async function fetchScheduledTaskList() {
  const res = await requestWithToken(`${BASE}/tasks/`)
  return res.json()
}

export async function createScheduledTask(body) {
  const res = await requestWithToken(`${BASE}/tasks/create/`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  return res.json()
}

export async function updateScheduledTask(id, body) {
  const res = await requestWithToken(`${BASE}/tasks/${id}/`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
  return res.json()
}

export async function setScheduledTaskStatus(id, status) {
  const res = await requestWithToken(`${BASE}/tasks/${id}/status/`, {
    method: 'POST',
    body: JSON.stringify({ status }),
  })
  return res.json()
}

export async function runScheduledTaskNow(id) {
  const res = await requestWithToken(`${BASE}/tasks/${id}/run/`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
  const text = await res.text()
  let data
  try {
    data = text ? JSON.parse(text) : {}
  } catch {
    throw new Error(`服务器返回非 JSON（HTTP ${res.status}），请检查接口是否已部署 /api/scheduled_task/tasks/{id}/run/`)
  }
  return data
}

export async function deleteScheduledTask(id) {
  const res = await requestWithToken(`${BASE}/tasks/${id}/delete/`, {
    method: 'POST',
  })
  return res.json()
}
