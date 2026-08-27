<template>
  <div class="dashboard">
    <!-- KPI 统计卡片行 -->
    <el-row :gutter="20" class="kpi-row">
      <el-col :xs="24" :sm="12" :md="4" v-for="card in statCards" :key="card.key">
        <el-card shadow="hover" class="kpi-card" v-loading="loading" element-loading-text="加载中">
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

    <!-- 图表行：饼图 + 柱状图 -->
    <el-row :gutter="20" class="chart-row">
      <el-col :xs="24" :lg="12">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <span class="chart-title">比对类型分布</span>
          </template>
          <div ref="pieChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="12">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <span class="chart-title">各项目比对次数</span>
          </template>
          <div ref="barChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 按小时趋势图 -->
    <el-card shadow="hover" class="chart-card">
      <template #header>
        <span class="chart-title">今日比对趋势（按小时）</span>
      </template>
      <div ref="lineChartRef" class="chart-container chart-line"></div>
    </el-card>

    <!-- 最近比对记录表格 -->
    <el-card shadow="hover" class="recent-card">
      <template #header>
        <div class="recent-head">
          <span class="recent-title">今日比对记录</span>
          <el-tag size="small" type="info" effect="plain">最近 10 条</el-tag>
        </div>
      </template>
      <el-table
        :data="recentList"
        v-loading="loading"
        stripe
        size="default"
        empty-text="今日暂无比对记录"
      >
        <el-table-column prop="create_time" label="时间" width="180" sortable />
        <el-table-column prop="user_name" label="用户" width="120" />
        <el-table-column prop="project_names" label="项目" min-width="160" show-overflow-tooltip />
        <el-table-column prop="compare_type" label="比对类型" width="100">
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
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import {
  DataAnalysis,
  Document,
  Operation,
  User,
  FolderOpened,
} from '@element-plus/icons-vue'
import { get_daily_statistic } from '../../api/home/index.js'

const loading = ref(false)

const stats = ref({
  total_count: 0,
  single_count: 0,
  batch_count: 0,
  unique_users: 0,
  unique_projects: 0,
  project_stats: [],
  hourly_stats: [],
  recent_list: [],
})

const recentList = computed(() => stats.value.recent_list || [])

const statCards = computed(() => [
  { key: 'total', label: '总比对次数', value: stats.value.total_count, icon: DataAnalysis, bg: '#ecf5ff', color: '#409eff' },
  { key: 'single', label: '单次对比', value: stats.value.single_count, icon: Document, bg: '#f0f9eb', color: '#67c23a' },
  { key: 'batch', label: '批量比对', value: stats.value.batch_count, icon: Operation, bg: '#fdf6ec', color: '#e6a23c' },
  { key: 'users', label: '操作用户', value: stats.value.unique_users, icon: User, bg: '#fef0f0', color: '#f56c6c' },
  { key: 'projects', label: '涉及项目', value: stats.value.unique_projects, icon: FolderOpened, bg: '#f4f4f5', color: '#909399' },
])

// ---- 图表实例 ----
const pieChartRef = ref(null)
const barChartRef = ref(null)
const lineChartRef = ref(null)
let pieChart = null
let barChart = null
let lineChart = null

function disposeCharts() {
  pieChart?.dispose()
  barChart?.dispose()
  lineChart?.dispose()
  pieChart = null
  barChart = null
  lineChart = null
}

function initCharts() {
  disposeCharts()
  if (pieChartRef.value) pieChart = echarts.init(pieChartRef.value)
  if (barChartRef.value) barChart = echarts.init(barChartRef.value)
  if (lineChartRef.value) lineChart = echarts.init(lineChartRef.value)
}

// ---- 饼图：单次 vs 批量 ----
function renderPieChart() {
  if (!pieChart) return
  const { single_count, batch_count } = stats.value
  pieChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} 次 ({d}%)' },
    legend: { bottom: 0, textStyle: { color: '#606266', fontSize: 12 } },
    series: [{
      type: 'pie',
      radius: ['55%', '78%'],
      center: ['50%', '48%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      emphasis: {
        label: { show: true, fontSize: 16, fontWeight: 'bold' },
        scaleSize: 8,
      },
      data: [
        { value: single_count, name: '单次对比', itemStyle: { color: '#409eff' } },
        { value: batch_count, name: '批量比对', itemStyle: { color: '#e6a23c' } },
      ],
    }],
  }, true)
}

// ---- 柱状图：各项目比对次数 ----
function renderBarChart() {
  if (!barChart) return
  const list = stats.value.project_stats || []
  barChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 8, right: 16, top: 8, bottom: 0, containLabel: true },
    xAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: '#909399', fontSize: 11 },
      splitLine: { lineStyle: { color: '#f0f0f0' } },
    },
    yAxis: {
      type: 'category',
      data: list.map(x => x.name),
      axisLabel: { color: '#606266', fontSize: 11, width: 80, overflow: 'truncate' },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [{
      type: 'bar',
      data: list.map(x => x.count),
      barWidth: 16,
      itemStyle: {
        borderRadius: [0, 4, 4, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: '#409eff' },
          { offset: 1, color: '#79bbff' },
        ]),
      },
      label: { show: true, position: 'right', color: '#606266', fontSize: 11 },
    }],
  }, true)
}

// ---- 折线图：按小时趋势 ----
function renderLineChart() {
  if (!lineChart) return
  const list = stats.value.hourly_stats || []
  lineChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 8, right: 24, top: 16, bottom: 0, containLabel: true },
    xAxis: {
      type: 'category',
      data: list.map(x => x.hour),
      boundaryGap: false,
      axisLabel: { color: '#909399', fontSize: 11 },
      axisLine: { lineStyle: { color: '#e0e0e0' } },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: '#909399', fontSize: 11 },
      splitLine: { lineStyle: { color: '#f0f0f0' } },
    },
    series: [{
      type: 'line',
      data: list.map(x => x.count),
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
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

function renderAllCharts() {
  nextTick(() => {
    renderPieChart()
    renderBarChart()
    renderLineChart()
  })
}

// ---- 窗口大小变化时 resize 图表 ----
function onResize() {
  pieChart?.resize()
  barChart?.resize()
  lineChart?.resize()
}

async function fetchStats() {
  loading.value = true
  try {
    const res = await get_daily_statistic()
    if (res.code === 0 && res.data) {
      stats.value = res.data
      await nextTick()
      initCharts()
      renderAllCharts()
    }
  } catch {
    // 静默
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchStats()
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  disposeCharts()
})
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ---- KPI cards ---- */
.kpi-row {
  margin: 0 !important;
}
.kpi-card {
  border-radius: 10px;
}
.kpi-card :deep(.el-card__body) {
  padding: 20px 18px;
}
.kpi-inner {
  display: flex;
  align-items: center;
  gap: 14px;
}
.kpi-icon {
  width: 48px;
  height: 48px;
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
  font-size: 13px;
  color: #909399;
  margin-bottom: 4px;
}
.kpi-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}

/* ---- Charts ---- */
.chart-row {
  margin: 0 !important;
}
.chart-card {
  border-radius: 10px;
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
.chart-line {
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
</style>
