import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import Login from '../views/Login.vue'
import Home from '../views/Home.vue'
import CaseShare from '../views/case_govern/CaseShare.vue'
import CaseExport from '../views/case_govern/CaseExport.vue'
import { getToken, isTokenExpired, clearToken } from '../common/request.js'
import { verifySsoTicket } from '../api/login.js'

const routes = [
  { path: '/', name: 'Login', component: Login },
  { path: '/login', redirect: '/' },
  { path: '/home', name: 'Home', component: Home, meta: { requiresAuth: true } },
  { path: '/case_share/:id', name: 'CaseShare', component: CaseShare, meta: { requiresAuth: true } },
  { path: '/case_export/:id', name: 'CaseExport', component: CaseExport, meta: { requiresAuth: true } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to, from, next) => {
  // SSO 回调：URL 带 ticket，先验证换取 token 再进入目标页
  if (to.query && to.query.ticket) {
    try {
      const data = await verifySsoTicket(to.query.ticket)
      if (data.code === 0) {
        const clean = { ...to.query }
        delete clean.ticket
        next({ path: to.path, query: clean, replace: true })
        return
      }
    } catch (e) {
      // 验证失败走登录页
    }
    next({ path: '/' })
    return
  }

  if (to.meta.requiresAuth) {
    const token = getToken()
    if (!token || isTokenExpired()) {
      clearToken()
      ElMessage.warning('登录已过期，请重新登录')
      next({ path: '/', query: { redirect: to.fullPath } })
      return
    }
  }
  next()
})

export default router
