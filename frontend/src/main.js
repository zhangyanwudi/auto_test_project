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

// 应用启动时获取页面配置，设置浏览器标题
fetchPageConfig().then(() => {
  document.title = getPageTitle()
})

app.mount('#app')

setOnUnauthorized((msg) => {
  ElMessage.error(msg || '登录已过期，请重新登录')
  router.push('/')
})
