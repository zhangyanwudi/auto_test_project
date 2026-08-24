/**
 * 配置比对（Django：apis/operate_tool/git_config_views + read_git_config）
 */
import { requestWithToken } from '../../common/request.js'

const BASE = '/api/operate_tool/git_config_diff'

export async function get_git_info(project_name) {
  const q = new URLSearchParams({ select_project: project_name || '' })
  const res = await requestWithToken(`${BASE}/get_git_info/?${q.toString()}`)
  return res.json()
}

/**
 * @param {string} project_name
 * @param {string} business_v
 * @param {string} timeslot
 * @param {RequestInit} [init] 可选，如 { signal } 用于切换项目时取消未完成的请求
 */
export async function get_adwaynum_file(project_name, business_v, timeslot, init = {}) {
  const q = new URLSearchParams({
    project_name: project_name || '',
    business_v: business_v ?? '',
    timeslot: timeslot || '',
  })
  const res = await requestWithToken(`${BASE}/get_adwaynum_file/?${q.toString()}`, init)
  return res.json()
}

export async function get_adwaynum_json_2(project_name, business_v, adwaynum, timeslot) {
  const q = new URLSearchParams({
    project_name: project_name || '',
    business_v: business_v ?? '',
    adwaynum: adwaynum || '',
    timeslot: timeslot || '',
  })
  const res = await requestWithToken(`${BASE}/get_adwaynum_json_2/?${q.toString()}`)
  return res.json()
}

/** 手动触发方案列表磁盘缓存重建（同步，完成后返回） */
export async function rebuild_adwaynum_cache(project_names) {
  const names = Array.isArray(project_names)
    ? project_names.filter(Boolean)
    : [project_names].filter(Boolean)
  const res = await requestWithToken(`${BASE}/rebuild_adwaynum_cache/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_names: names }),
  })
  return res.json()
}

/** 统计上报（原逻辑为拼接 query 风格字符串） */
export async function report_statistic_info(statisticStr) {
  const res = await requestWithToken(`${BASE}/report_statistic_info/`, {
    method: 'POST',
    body: typeof statisticStr === 'string' ? statisticStr : String(statisticStr),
    headers: { 'Content-Type': 'text/plain;charset=UTF-8' },
  })
  return res.json()
}

