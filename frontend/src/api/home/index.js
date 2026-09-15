/**
 * 首页 / 仪表盘 API
 */
import { requestWithToken } from '../../common/request.js'

const BASE = '/api/home'

/** 查询当日配置比对统计数据 */
export async function get_daily_statistic() {
  const res = await requestWithToken(`${BASE}/daily_statistic/`)
  return res.json()
}

/** 功能使用上报（进入某功能页停留满 1 分钟调用） */
export async function reportFeatureUsage(menuCode, menuName) {
  const res = await requestWithToken(`${BASE}/feature_usage/report/`, {
    method: 'POST',
    body: JSON.stringify({ menu_code: menuCode, menu_name: menuName }),
  })
  return res.json()
}

/** 按菜单功能统计使用量（全量；可传 start/end 时间过滤） */
export async function getFeatureUsageStatistic(params = {}) {
  const qs = new URLSearchParams()
  if (params.start) qs.set('start', params.start)
  if (params.end) qs.set('end', params.end)
  const query = qs.toString() ? `?${qs.toString()}` : ''
  const res = await requestWithToken(`${BASE}/feature_usage/statistic/${query}`)
  return res.json()
}
