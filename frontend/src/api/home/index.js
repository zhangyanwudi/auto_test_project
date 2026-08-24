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
