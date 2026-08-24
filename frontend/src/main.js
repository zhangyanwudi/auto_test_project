import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import { ElMessage } from 'element-plus'
import 'element-plus/dist/index.css'
import './styles/admin-common.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import App from './App.vue'
import router from './router'
import { setOnUnauthorized, fetchPageConfig, getPageTitle } from './common/request.js'

const app = createApp(App)
app.use(router)
app.use(ElementPlus, { locale: zhCn })

// 应用启动时先获取页面配置（含 sso_enabled），再挂载，
// 避免登录页在 fetchPageConfig 完成前读取 localStorage 导致统一登录入口不显示
async function bootstrap() {
  await fetchPageConfig()
  document.title = getPageTitle()
  app.mount('#app')
}

bootstrap()

setOnUnauthorized((msg) => {
  ElMessage.error(msg || '登录已过期，请重新登录')
  router.push('/')
})
