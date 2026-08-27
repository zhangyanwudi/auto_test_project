<template>
  <el-container class="admin-layout">
    <el-aside width="220px" class="admin-aside">
      <div class="logo">
        <span class="logo-text">{{ pageTitle }}</span>
      </div>
      <el-menu
        v-loading="menuLoading"
        :default-active="activeMenu"
        class="admin-menu"
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409eff"
        @select="handleMenuSelect"
      >
        <template v-if="menuTree.length">
          <template v-for="item in menuTree" :key="item.id">
            <el-sub-menu v-if="item.children && item.children.length" :index="canonicalMenuCode(item.menu_code)">
              <template #title>
                <el-icon><component :is="iconComponent(item.icon)" /></el-icon>
                <span>{{ item.menu_name }}</span>
              </template>
              <el-menu-item
                v-for="ch in item.children"
                :key="ch.id"
                :index="canonicalMenuCode(ch.menu_code)"
              >
                <el-icon><component :is="iconComponent(ch.icon)" /></el-icon>
                <span>{{ ch.menu_name }}</span>
              </el-menu-item>
            </el-sub-menu>
            <el-menu-item v-else :index="canonicalMenuCode(item.menu_code)">
              <el-icon><component :is="iconComponent(item.icon)" /></el-icon>
              <span>{{ item.menu_name }}</span>
            </el-menu-item>
          </template>
        </template>
        <el-empty v-else-if="!menuLoading" description="暂无可用菜单" :image-size="60" />
      </el-menu>
    </el-aside>

    <el-container direction="vertical">
      <el-header class="admin-header">
        <div class="header-left">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item>
              <span role="button" tabindex="0" @click="setActiveMenu('home')" class="breadcrumb-link">首页</span>
            </el-breadcrumb-item>
            <el-breadcrumb-item v-if="breadcrumb">{{ breadcrumb }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <el-dropdown trigger="click" @command="handleCommand">
            <span class="user-dropdown">
              <el-icon><Avatar /></el-icon>
              <span class="user-name">{{ username }}</span>
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">
                  <el-icon><User /></el-icon>
                  个人中心
                </el-dropdown-item>
                <el-dropdown-item command="logout" divided>
                  <el-icon><SwitchButton /></el-icon>
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="admin-main">
        <div v-if="activeMenu === 'home'" class="page-content">
          <!-- 欢迎语 -->
          <el-card shadow="hover" class="welcome-card">
            <template #header>
              <span>欢迎使用</span>
            </template>
            <p class="welcome-text">您好，{{ username }}！欢迎进入{{ pageTitle }}。</p>
          </el-card>

          <!-- KPI 统计卡片 -->
          <el-row :gutter="20" class="kpi-row">
            <el-col :xs="24" :sm="12" :md="4" v-for="card in homeStatCards" :key="card.key">
              <el-card shadow="hover" class="kpi-card" v-loading="homeLoading">
                <div class="kpi-inner">
                  <div class="kpi-icon" :style="{ background: card.bg }">
                    <el-icon :size="22"><component :is="card.icon" /></el-icon>
                  </div>
                  <div class="kpi-body">
                    <div class="kpi-label">{{ card.label }}</div>
                    <div class="kpi-value" :style="{ color: card.color }">{{ card.value }}</div>
                  </div>
                </div>
              </el-card>
            </el-col>
          </el-row>

          <!-- 图表区域 -->
          <el-row :gutter="20" class="chart-row">
            <el-col :xs="24" :lg="12">
              <el-card shadow="hover" class="chart-card">
                <template #header>
                  <span class="chart-title">比对类型分布</span>
                </template>
                <div ref="homePieChartRef" class="chart-container"></div>
              </el-card>
            </el-col>
            <el-col :xs="24" :lg="12">
              <el-card shadow="hover" class="chart-card">
                <template #header>
                  <span class="chart-title">各项目比对次数</span>
                </template>
                <div ref="homeBarChartRef" class="chart-container"></div>
              </el-card>
            </el-col>
          </el-row>

          <!-- 趋势图 -->
          <el-card shadow="hover" class="chart-card">
            <template #header>
              <span class="chart-title">今日比对趋势（按小时）</span>
            </template>
            <div ref="homeLineChartRef" class="chart-container chart-line"></div>
          </el-card>

          <!-- 最近记录 -->
          <el-card shadow="hover" class="recent-card">
            <template #header>
              <div class="recent-head">
                <span class="recent-title">今日比对记录</span>
                <el-tag size="small" type="info" effect="plain">最近 10 条</el-tag>
              </div>
            </template>
            <el-table :data="homeRecentList" v-loading="homeLoading" stripe size="default" empty-text="今日暂无比对记录">
              <el-table-column prop="create_time" label="时间" width="180" sortable />
              <el-table-column prop="user_name" label="用户" width="120" />
              <el-table-column prop="project_names" label="项目" min-width="160" show-overflow-tooltip />
              <el-table-column prop="compare_type" label="类型" width="90">
                <template #default="{ row }">
                  <el-tag :type="row.compare_type === 'batch' ? 'warning' : 'primary'" size="small" effect="light">
                    {{ row.compare_type === 'batch' ? '批量' : '单次' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="left_Adwaynum" label="左侧方案" min-width="140" show-overflow-tooltip />
              <el-table-column prop="right_Adwaynum" label="右侧方案" min-width="140" show-overflow-tooltip />
            </el-table>
          </el-card>
        </div>
        <div v-else-if="activeView" class="page-content">
          <component :is="activeView" ref="activeViewRef" />
        </div>
        <div v-else class="page-content">
          <el-card shadow="hover">
            <template #header>
              <span>{{ breadcrumb || '页面' }}</span>
            </template>
            <p class="placeholder-text">该功能模块开发中，敬请期待。</p>
          </el-card>
        </div>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, markRaw, reactive, nextTick } from 'vue'
import { useRouter, useRoute, onBeforeRouteLeave } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import {
  User,
  Avatar,
  ArrowDown,
  SwitchButton,
  DataAnalysis,
  Document,
  Operation,
  FolderOpened,
} from '@element-plus/icons-vue'
import { getUserCnName, clearToken, requestWithToken, syncUserProfileFromTokenData, getPageTitle } from '../common/request.js'
import { fetchSidebarMenuList } from '../api/system/menu.js'
import { get_daily_statistic } from '../api/home/index.js'
import MenuManagement from './system/MenuManagement.vue'
import UserManagement from './system/UserManagement.vue'
import RoleManagement from './system/RoleManagement.vue'
import Dashboard from './system/Dashboard.vue'
import IconManagement from './system/IconManagement.vue'
import ConfigCompare from './tools/ConfigCompare.vue'
import ImgRecognize from './tools/img_recognize.vue'
import ScheduledTaskManagement from './task/ScheduledTaskManagement.vue'
import AiHelperPage from './ai_helper/AiHelperPage.vue'
import GpLogcat from './gp_logcat/GpLogcat.vue'
import MockApiManagement from './mock_api/MockApiManagement.vue'
import CaseGovernManagement from './case_govern/CaseGovernManagement.vue'

const router = useRouter()
const route = useRoute()
const activeMenu = ref('home')
/** 当前渲染的功能页面组件实例，用于路由离开守卫判断是否有未保存修改 */
const activeViewRef = ref(null)
/** 页面标题：读取 page_config.json 中的 page_tile_name */
const pageTitle = ref(getPageTitle())
/** 顶栏与欢迎语展示名：优先库中 user_cn_name */
const username = ref('')
const menuLoading = ref(false)
const menuTree = ref([])
/** 侧栏接口返回的扁平菜单（可见即已授权，用于解码与父级挂载解析） */
const sidebarMenuFlat = ref([])
const menuTitleMap = ref({ home: '' })
/** 首页统计数据 */
const homeLoading = ref(false)
const homeStats = reactive({
  total_count: 0,
  single_count: 0,
  batch_count: 0,
  unique_users: 0,
  unique_projects: 0,
  project_stats: [],
  hourly_stats: [],
  recent_list: [],
})

/** KPI 卡片配置 */
const homeStatCards = computed(() => [
  { key: 'total', label: '总比对次数', value: homeStats.total_count, icon: DataAnalysis, bg: '#ecf5ff', color: '#409eff' },
  { key: 'single', label: '单次对比', value: homeStats.single_count, icon: Document, bg: '#f0f9eb', color: '#67c23a' },
  { key: 'batch', label: '批量比对', value: homeStats.batch_count, icon: Operation, bg: '#fdf6ec', color: '#e6a23c' },
  { key: 'users', label: '操作用户', value: homeStats.unique_users, icon: User, bg: '#fef0f0', color: '#f56c6c' },
  { key: 'projects', label: '涉及项目', value: homeStats.unique_projects, icon: FolderOpened, bg: '#f4f4f5', color: '#909399' },
])

const homeRecentList = computed(() => homeStats.recent_list || [])

/** 图表 refs */
const homePieChartRef = ref(null)
const homeBarChartRef = ref(null)
const homeLineChartRef = ref(null)
let homePieChart = null
let homeBarChart = null
let homeLineChart = null

function disposeHomeCharts() {
  homePieChart?.dispose()
  homeBarChart?.dispose()
  homeLineChart?.dispose()
  homePieChart = null
  homeBarChart = null
  homeLineChart = null
}

function initHomeCharts() {
  disposeHomeCharts()
  if (homePieChartRef.value) homePieChart = echarts.init(homePieChartRef.value)
  if (homeBarChartRef.value) homeBarChart = echarts.init(homeBarChartRef.value)
  if (homeLineChartRef.value) homeLineChart = echarts.init(homeLineChartRef.value)
}

/** 饼图 — 单次 vs 批量 */
function renderHomePie() {
  if (!homePieChart) return
  const { single_count, batch_count } = homeStats
  const data = [
    { value: single_count, name: '单次对比', itemStyle: { color: '#409eff' } },
    { value: batch_count, name: '批量比对', itemStyle: { color: '#e6a23c' } },
  ]
  homePieChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} 次 ({d}%)' },
    legend: { bottom: 0, textStyle: { color: '#606266' } },
    series: [{
      type: 'pie',
      radius: ['55%', '78%'],
      center: ['50%', '46%'],
      itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 16, fontWeight: 'bold' } },
      data,
    }],
  }, true)
}

/** 柱状图 — 各项目比对次数 */
function renderHomeBar() {
  if (!homeBarChart) return
  const list = homeStats.project_stats || []
  homeBarChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 8, right: 16, top: 8, bottom: 0, containLabel: true },
    xAxis: {
      type: 'value', minInterval: 1,
      axisLabel: { color: '#909399', fontSize: 11 },
      splitLine: { lineStyle: { color: '#f0f0f0' } },
    },
    yAxis: {
      type: 'category', data: list.map(x => x.name),
      axisLabel: { color: '#606266', fontSize: 11, width: 80, overflow: 'truncate' },
      axisLine: { show: false }, axisTick: { show: false },
    },
    series: [{
      type: 'bar', data: list.map(x => x.count), barWidth: 16,
      itemStyle: {
        borderRadius: [0, 4, 4, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: '#409eff' }, { offset: 1, color: '#79bbff' },
        ]),
      },
      label: { show: true, position: 'right', color: '#606266', fontSize: 11 },
    }],
  }, true)
}

/** 折线图 — 按小时趋势 */
function renderHomeLine() {
  if (!homeLineChart) return
  const list = homeStats.hourly_stats || []
  homeLineChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 8, right: 24, top: 16, bottom: 0, containLabel: true },
    xAxis: {
      type: 'category', data: list.map(x => x.hour), boundaryGap: false,
      axisLabel: { color: '#909399', fontSize: 11 },
      axisLine: { lineStyle: { color: '#e0e0e0' } },
    },
    yAxis: {
      type: 'value', minInterval: 1,
      axisLabel: { color: '#909399', fontSize: 11 },
      splitLine: { lineStyle: { color: '#f0f0f0' } },
    },
    series: [{
      type: 'line', data: list.map(x => x.count), smooth: true,
      symbol: 'circle', symbolSize: 6,
      lineStyle: { color: '#409eff', width: 2 },
      itemStyle: { color: '#409eff' },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(64,158,255,0.25)' },
          { offset: 1, color: 'rgba(64,158,255,0.02)' },
        ]),
      },
    }],
  }, true)
}

function renderHomeAllCharts() {
  nextTick(() => {
    renderHomePie()
    renderHomeBar()
    renderHomeLine()
  })
}

async function fetchHomeStats() {
  homeLoading.value = true
  try {
    const res = await get_daily_statistic()
    if (res.code === 0 && res.data) {
      Object.assign(homeStats, res.data)
      await nextTick()
      initHomeCharts()
      renderHomeAllCharts()
    }
  } catch {
    // 静默失败
  } finally {
    homeLoading.value = false
  }
}

function onHomeResize() {
  homePieChart?.resize()
  homeBarChart?.resize()
  homeLineChart?.resize()
}

/** menu_code -> 侧栏选中时渲染的页面组件（与菜单管理里「前端路径」字段无运行时关联，前端路径仅库内备注） */
const viewMap = {
  dashboard: markRaw(Dashboard),
  users: markRaw(UserManagement),
  roles: markRaw(RoleManagement),
  menu_management: markRaw(MenuManagement),
  icon_management: markRaw(IconManagement),
  config_compare: markRaw(ConfigCompare),
  img_recognize: markRaw(ImgRecognize),
  /** 父级「定时任务」分组：与子项同页（el-menu-item 点才走 scheduled_task） */
  timer_task: markRaw(ScheduledTaskManagement),
  ai_helper: markRaw(AiHelperPage),
  gp_logcat: markRaw(GpLogcat),
  mock_api: markRaw(MockApiManagement),
  case_govern: markRaw(CaseGovernManagement),
}

/** 规范化侧栏传来的 index（去空格），避免 `(code in menuTitleMap)` 误判 */
function canonicalMenuCode(raw) {
  if (raw === null || raw === undefined) return ''
  const s = String(raw).trim()
  return s
}

/** 当前侧栏页签同步到地址栏 query（?menu=xxx），刷新/恢复标签页后能回到原页面；
 *  用 history.replaceState 只改地址栏，不触发路由守卫（避免误触 onBeforeRouteLeave 的未保存确认） */
function syncMenuToUrl(menu) {
  const url = new URL(window.location.href)
  if (!menu || menu === 'home') {
    url.searchParams.delete('menu')
  } else {
    url.searchParams.set('menu', menu)
  }
  window.history.replaceState(window.history.state, '', url.toString())
}

/** 设置当前侧栏页签，并同步到 URL */
function setActiveMenu(menu) {
  const c = canonicalMenuCode(menu) || 'home'
  activeMenu.value = c
  syncMenuToUrl(c)
}

/** 从 URL query 恢复上次停留的侧栏页签（无则首页） */
function menuFromUrl() {
  return canonicalMenuCode(route.query.menu) || 'home'
}

/** 是否与侧栏已下发菜单一致：只要当前 menu_code 在接口返回中存在即视为可看该页（接口已按角色过滤） */
function isSidebarAuthorizedFor(code) {
  const c = canonicalMenuCode(code)
  if (!sidebarMenuFlat.value.length) return true
  return sidebarMenuFlat.value.some((x) => canonicalMenuCode(x.menu_code) === c)
}

function findMenuRowByCode(menuCodeRaw) {
  const c = canonicalMenuCode(menuCodeRaw)
  return sidebarMenuFlat.value.find((x) => canonicalMenuCode(x.menu_code) === c) ?? null
}

/**
 * menu_code → 页面组件。
 * - 先在 viewMap 精确匹配；
 * - 再在侧栏数据中按 path（或父级 page_scheduled）解析定时任务页，避免库内改码后无法打开。
 */
function resolveViewComponent(menuCodeRaw) {
  const code = canonicalMenuCode(menuCodeRaw)
  const direct = viewMap[code]
  if (direct) return direct

  const row = findMenuRowByCode(code)
  if (!row) return null

  return null
}

const activeView = computed(() => {
  const code = canonicalMenuCode(activeMenu.value)
  if (code === 'home' || !code) return null
  if (!isSidebarAuthorizedFor(code)) return null
  return resolveViewComponent(code)
})

const breadcrumb = computed(() => {
  const c = canonicalMenuCode(activeMenu.value)
  const m = menuTitleMap.value
  const row = findMenuRowByCode(c)
  if (m[c]) return m[c]
  if (row?.menu_name) return row.menu_name
  if (c === 'scheduled_task' && (m.scheduled_task || m.page_scheduled)) {
    return m.scheduled_task || m.page_scheduled
  }
  if (c === 'page_scheduled' && (m.page_scheduled || m.scheduled_task)) {
    return m.page_scheduled || m.scheduled_task
  }
  return ''
})

function iconComponent(name) {
  if (!name) return ElementPlusIconsVue.Menu
  return ElementPlusIconsVue[name] || ElementPlusIconsVue.Menu
}

/** 侧栏：排序字段从小到大，相同再按 id */
function compareMenuOrder(a, b) {
  const so = (a.sort_order ?? 0) - (b.sort_order ?? 0)
  if (so !== 0) return so
  return (a.id ?? 0) - (b.id ?? 0)
}

function buildMenuTree(flat) {
  const byId = {}
  flat.forEach((m) => {
    byId[m.id] = { ...m, children: [] }
  })
  const roots = []
  flat.forEach((m) => {
    const node = byId[m.id]
    if (m.parent_id && byId[m.parent_id]) {
      byId[m.parent_id].children.push(node)
    } else if (!m.parent_id) {
      roots.push(node)
    }
  })
  roots.sort(compareMenuOrder)
  roots.forEach((r) => {
    r.children.sort(compareMenuOrder)
  })
  return roots
}

function syncTitleMap(flat) {
  const m = { home: '' }
  flat.forEach((x) => {
    const ck = canonicalMenuCode(x.menu_code)
    if (!ck) return
    m[ck] = x.menu_name
  })
  menuTitleMap.value = m
}

function ensureActiveMenuValid(flat) {
  const codes = new Set(flat.map((x) => canonicalMenuCode(x.menu_code)).filter(Boolean))
  const cur = canonicalMenuCode(activeMenu.value)
  if (cur !== 'home' && !codes.has(cur)) {
    setActiveMenu('home')
  }
}

async function loadSidebarMenus() {
  menuLoading.value = true
  try {
    const res = await fetchSidebarMenuList()
    if (res.code === 0 && Array.isArray(res.data)) {
      sidebarMenuFlat.value = res.data
      syncTitleMap(res.data)
      menuTree.value = buildMenuTree(res.data)
      ensureActiveMenuValid(res.data)
    } else {
      sidebarMenuFlat.value = []
      menuTree.value = []
    }
  } catch {
    sidebarMenuFlat.value = []
    menuTree.value = []
  } finally {
    menuLoading.value = false
  }
}

function handleMenuSelect(index, _indexPath) {
  setActiveMenu(index)
}

function handleCommand(command) {
  if (command === 'logout') {
    clearToken()
    router.push('/')
  } else if (command === 'profile') {
    // 可跳转个人中心
  }
}

function onMenuUpdated() {
  loadSidebarMenus()
}

async function refreshUserDisplayName() {
  try {
    const res = await requestWithToken('/api/common/token_check/')
    const j = await res.json()
    if (j.code === 0 && j.data) {
      syncUserProfileFromTokenData(j.data)
    }
  } catch {
    // 401 等由全局处理
  }
  username.value = getUserCnName() || '管理员'
}

function onAiToolNavigate(e) {
  const menu = e.detail?.menu
  if (menu && viewMap[menu]) {
    setActiveMenu(menu)
  }
}

onMounted(() => {
  activeMenu.value = menuFromUrl()
  pageTitle.value = getPageTitle()
  document.title = pageTitle.value
  username.value = getUserCnName() || '管理员'
  refreshUserDisplayName()
  loadSidebarMenus()
  fetchHomeStats()
  window.addEventListener('admin-menu-updated', onMenuUpdated)
  window.addEventListener('ai-tool-navigate', onAiToolNavigate)
  window.addEventListener('resize', onHomeResize)
})

onUnmounted(() => {
  window.removeEventListener('admin-menu-updated', onMenuUpdated)
  window.removeEventListener('ai-tool-navigate', onAiToolNavigate)
  window.removeEventListener('resize', onHomeResize)
  disposeHomeCharts()
})

// 拦截浏览器后退（Mac 左右滑动）等路由离开；当前功能页（如用例管理）有未保存修改时先确认
onBeforeRouteLeave(async () => {
  const comp = activeViewRef.value
  if (comp && typeof comp.hasUnsavedChanges === 'function' && comp.hasUnsavedChanges()) {
    try {
      await ElMessageBox.confirm('当前页面有未保存的修改，离开后将丢失，确定离开吗？', '提示', {
        type: 'warning',
        confirmButtonText: '放弃修改并离开',
        cancelButtonText: '继续编辑',
      })
      return true
    } catch {
      return false
    }
  }
  return true
})
</script>

<style scoped>
.admin-layout {
  height: 100vh;
}
/* 内部垂直容器：限制高度防止内容溢出撑开整个页面 */
.admin-layout > .el-container {
  overflow: hidden;
}
.admin-aside {
  background-color: #304156;
  overflow-x: hidden;
}
.logo {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.2);
}
.logo-text {
  color: #fff;
  font-size: 18px;
  font-weight: 600;
}
.admin-menu {
  border-right: none;
}
.admin-menu .el-menu-item:hover,
.admin-menu .el-sub-menu__title:hover {
  background-color: #263445 !important;
  color: #409eff;
}
.admin-menu .el-menu-item.is-active {
  background-color: #263445 !important;
  color: #409eff;
}
.admin-menu .el-sub-menu .el-menu {
  background-color: #1f2d3d !important;
}
.admin-menu .el-sub-menu .el-menu-item {
  background-color: #1f2d3d !important;
}
.admin-menu .el-sub-menu .el-menu-item:hover {
  background-color: #263445 !important;
}
.admin-menu:not(.el-menu--collapse) {
  width: 220px;
}
.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  padding: 0 20px;
}
.header-left {
  flex: 1;
}
.header-right {
  display: flex;
  align-items: center;
}
.user-dropdown {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: #606266;
}
.user-name {
  font-size: 14px;
}
.admin-main {
  background: #f0f2f5;
  padding: 20px;
  overflow-y: auto;
}
.page-content {
  min-height: 100%;
}
.welcome-card {
  margin-bottom: 20px;
}
.welcome-card .welcome-text {
  margin: 0;
  font-size: 15px;
  color: #606266;
}

/* ---- KPI cards ---- */
.kpi-row {
  margin: 0 0 20px !important;
}
.kpi-card {
  border-radius: 10px;
  margin-bottom: 0;
}
.kpi-card :deep(.el-card__body) {
  padding: 18px 16px;
}
.kpi-inner {
  display: flex;
  align-items: center;
  gap: 12px;
}
.kpi-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.kpi-body {
  flex: 1;
  min-width: 0;
}
.kpi-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 2px;
}
.kpi-value {
  font-size: 26px;
  font-weight: 700;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}

/* ---- Charts ---- */
.chart-row {
  margin: 0 0 20px !important;
}
.chart-card {
  border-radius: 10px;
  margin-bottom: 20px;
}
.chart-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}
.chart-container {
  width: 100%;
  height: 280px;
}
.chart-container.chart-line {
  height: 220px;
}

/* ---- Table ---- */
.recent-card {
  border-radius: 10px;
}
.recent-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.recent-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.placeholder-text {
  color: #909399;
  margin: 0;
}
.breadcrumb-link {
  cursor: pointer;
  color: var(--el-color-primary);
}
.breadcrumb-link:hover {
  opacity: 0.8;
}
</style>
