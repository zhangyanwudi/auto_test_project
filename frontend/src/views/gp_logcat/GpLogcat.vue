<template>
  <div class="gp-logcat-page">
    <!-- ===== 顶部控制栏 ===== -->
    <el-card shadow="never" class="control-card">
      <div class="control-row">
        <div class="control-left">
          <!-- 连接 / adb 状态 -->
          <span class="status-dot" :class="statusDotClass" :title="statusTooltip"></span>
          <el-tag :type="statusTagType" size="small" effect="dark">
            {{ statusLabel }}
          </el-tag>

          <el-divider direction="vertical" />

          <!-- 日志计数 -->
          <span class="log-count">
            <el-icon><Document /></el-icon>
            <strong>{{ filteredLines.length }}</strong> / {{ allLines.length }} 条
          </span>

          <el-divider direction="vertical" />

          <!-- 模式切换 -->
          <el-radio-group v-model="runMode" size="small" :disabled="adbRunning || isReceivingLogs">
            <el-radio-button value="server">服务器</el-radio-button>
            <el-radio-button value="local">本地</el-radio-button>
          </el-radio-group>

          <el-divider direction="vertical" />

          <!-- 启停按钮 -->
          <el-button
            v-if="!adbRunning && !isReceivingLogs"
            type="success"
            size="small"
            :icon="VideoPlay"
            :loading="starting"
            :disabled="runMode === 'local' && !agentReady"
            @click="handleStart"
          >
            启动日志
          </el-button>
          <el-button
            v-else-if="adbRunning || isReceivingLogs"
            type="danger"
            size="small"
            :icon="VideoPause"
            :loading="stopping"
            @click="handleStop"
          >
            停止
          </el-button>

          <!-- 本地模式：一键启动代理 -->
          <el-popover
            v-if="runMode === 'local' && !agentReady && !isReceivingLogs"
            v-model:visible="localGuideVisible"
            placement="bottom"
            :width="560"
            trigger="manual"
          >
            <template #reference>
              <el-button size="small" type="primary" :icon="DocumentCopy" @click="localGuideVisible = !localGuideVisible">
                一键启动代理
              </el-button>
            </template>
            <div style="font-size:13px;line-height:1.8">
              <p><strong>本地模式会自动检测 Python、下载并启动代理：</strong></p>
              <p>① Android 设备通过 USB 连接<strong>你本地电脑</strong></p>
              <p>② 复制下面命令，粘贴到<strong>本地终端</strong>运行（保持终端不关）：</p>
              <pre
                style="background:#1e1e1e;color:#d4d4d4;padding:10px;border-radius:4px;overflow-x:auto;font-size:12px;cursor:pointer;user-select:all;white-space:pre-wrap;word-break:break-all"
                @click="copyAgentCommand"
                title="点击复制"
              ><code>{{ agentCommand }}</code></pre>
              <p style="color:#909399;margin:6px 0 0">脚本会：检查 python3 → 首次下载代理 → 自动启动</p>
              <p style="color:#e6a23c;margin:4px 0 0">⚠ 终端保持运行；代理就绪后本页会自动提示</p>
              <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
                <el-button type="primary" size="small" :icon="DocumentCopy" @click="copyAgentCommand">复制一键命令</el-button>
                <el-button size="small" @click="downloadLauncher('command')">下载 macOS 启动脚本</el-button>
                <el-button size="small" @click="downloadLauncher('bat')">下载 Windows 启动脚本</el-button>
              </div>
            </div>
          </el-popover>

          <el-divider direction="vertical" />

          <!-- 自动滚动 -->
          <el-switch
            v-model="autoScroll"
            size="small"
            active-text="自动滚动"
            @change="onAutoScrollChange"
          />
        </div>

        <div class="control-right">
          <el-button-group>
            <el-button size="small" @click="pauseResume">
              <el-icon><component :is="paused ? VideoPlay : VideoPause" /></el-icon>
              {{ paused ? '继续' : '暂停' }}
            </el-button>
            <el-button size="small" type="danger" plain @click="handleClear">
              <el-icon><Delete /></el-icon>
              清空
            </el-button>
          </el-button-group>
        </div>
      </div>

      <!-- 环境提示 -->
      <div v-if="runMode === 'local' && !agentReady" class="env-warning">
        <el-icon><WarningFilled /></el-icon>
        <span>本地模式需先启动代理。点击「一键启动代理」复制命令到本地终端运行（自动检测 Python 并下载脚本）。</span>
      </div>
      <div v-if="runMode === 'local' && agentReady" class="agent-hint">
        <el-icon><CircleCheck /></el-icon>
        <span>本地代理已就绪，点击「启动日志」开始抓取。</span>
      </div>

      <!-- 过滤参数 -->
      <div v-if="!adbRunning && !isReceivingLogs" class="filter-config-row">
        <span class="filter-label">TAG 过滤：</span>
        <el-input
          v-model="adbFilter"
          size="small"
          placeholder="如：klog（匹配该 TAG 的日志）；空格分隔多个"
          style="flex: 1"
          clearable
        />
      </div>
    </el-card>

    <!-- ===== 过滤区域 ===== -->
    <el-card shadow="never" class="filter-card" v-if="filteredLines.length > 0 || allLines.length > 0">
      <el-row :gutter="16" align="middle">
        <el-col :xs="24" :md="10">
          <el-input
            v-model="keyword"
            placeholder="输入关键字过滤日志..."
            clearable
            :prefix-icon="Search"
            size="default"
          />
        </el-col>
        <el-col :xs="24" :md="10">
          <el-checkbox-group v-model="levelFilter" size="small">
            <el-checkbox label="V" border class="level-check level-v">V</el-checkbox>
            <el-checkbox label="D" border class="level-check level-d">D</el-checkbox>
            <el-checkbox label="I" border class="level-check level-i">I</el-checkbox>
            <el-checkbox label="W" border class="level-check level-w">W</el-checkbox>
            <el-checkbox label="E" border class="level-check level-e">E</el-checkbox>
            <el-checkbox label="F" border class="level-check level-f">F</el-checkbox>
          </el-checkbox-group>
        </el-col>
        <el-col :xs="24" :md="4" class="filter-right">
          <el-select v-model="displayLimit" size="default" style="width: 140px">
            <el-option label="最近 200 行" :value="200" />
            <el-option label="最近 500 行" :value="500" />
            <el-option label="最近 1000 行" :value="1000" />
            <el-option label="最近 2000 行" :value="2000" />
          </el-select>
        </el-col>
      </el-row>
    </el-card>

    <!-- ===== 日志显示区域 ===== -->
    <el-card shadow="never" class="log-card" body-style="padding: 0">
      <div ref="logContainer" class="log-container" @scroll="onLogScroll">
        <!-- 空状态 -->
        <div v-if="filteredLines.length === 0" class="log-empty">
          <!-- 受过滤影响但确有日志 -->
          <template v-if="allLines.length > 0">
            <el-empty description="无匹配日志，请调整过滤条件" :image-size="80" />
          </template>
          <!-- 完全没有日志 -->
          <template v-else>
            <div class="empty-panel">
              <div class="empty-icon">
                <el-icon :size="40"><Monitor /></el-icon>
              </div>
              <template v-if="runMode === 'server'">
                <div class="empty-title">点击「启动日志」开始抓取</div>
                <div class="empty-desc">请确保 Android 设备已通过 USB 连接到此服务器</div>
              </template>
              <template v-else-if="agentReady">
                <div class="empty-title">本地代理已就绪</div>
                <div class="empty-desc">点击「启动日志」开始抓取</div>
              </template>
              <template v-else>
                <div class="empty-title">请先启动本地代理</div>
                <div class="empty-desc">点击上方「一键启动代理」，复制命令到本地终端运行</div>
              </template>
            </div>
          </template>
        </div>

        <!-- 日志行 -->
        <div v-else class="log-lines">
          <div
            v-for="(item, idx) in filteredLines"
            :key="idx"
            class="log-line"
            :class="logLevelClass(item)"
          >
            <span class="line-num">{{ item.originIndex + 1 }}</span>
            <span class="line-text" v-html="highlightKeyword(item.text)"></span>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Document,
  DocumentCopy,
  VideoPlay,
  VideoPause,
  Delete,
  Search,
  Monitor,
  WarningFilled,
  CircleCheck,
} from '@element-plus/icons-vue'
import {
  getStreamUrl,
  clearLogs,
  getStatus,
  startLogcat,
  stopLogcat,
  getAgentOneClickCommand,
  getAgentBootstrapUrl,
} from '../../api/gp_logcat/index.js'

// -------------------------------------------------------------------
// 状态
// -------------------------------------------------------------------

/** 运行模式 */
const runMode = ref('server')  // 'server' | 'local'

/** adb 环境 */
const adbAvailable = ref(false)
const adbCheckMsg = ref('正在检查 adb 环境...')
const adbRunning = ref(false)
const adbFilter = ref('')

/** 本地代理引导弹层 */
const localGuideVisible = ref(false)

/** 本地代理启动命令（一键：检测 Python → 下载 → 启动） */
const agentCommand = computed(() => getAgentOneClickCommand())

/** 启停 loading */
const starting = ref(false)
const stopping = ref(false)

/** 日志 */
const allLines = ref([])
let lineCounter = 0
let _renderBuffer = []
let _flushTimer = null
const FLUSH_INTERVAL = 80
const FLUSH_BATCH_MAX = 200
const MAX_BUFFER_LINES = 3000  // 缓冲区上限，超出丢弃旧数据

/** 连接 */
const connectionState = ref('disconnected')

/** UI */
const paused = ref(false)
const autoScroll = ref(true)
const keyword = ref('')
const levelFilter = ref(['V', 'D', 'I', 'W', 'E', 'F'])
const displayLimit = ref(1000)

let eventSource = null
let pausedBuffer = []
const logContainer = ref(null)

// -------------------------------------------------------------------
// 计算属性
// -------------------------------------------------------------------

const statusDotClass = computed(() => ({
  connected: adbRunning.value || isReceivingLogs.value,
  connecting: connectionState.value === 'connecting' || (runMode.value === 'local' && !agentReady.value),
  disconnected: !adbRunning.value && !isReceivingLogs.value && connectionState.value !== 'connecting',
}))

const statusTagType = computed(() => {
  if (adbRunning.value || isReceivingLogs.value) return 'success'
  if (runMode.value === 'local' && agentReady.value) return 'success'
  if (connectionState.value === 'connecting') return 'warning'
  if (runMode.value === 'local' && !agentReady.value) return 'warning'
  return 'info'
})

const statusLabel = computed(() => {
  if (adbRunning.value) return '抓取中'
  if (isReceivingLogs.value) return '接收中'
  if (connectionState.value === 'connecting') return '连接中...'
  if (runMode.value === 'local') return agentReady.value ? '代理就绪' : '等待代理'
  return adbAvailable.value ? '待启动' : '待连接'
})

const statusTooltip = computed(() => {
  if (adbRunning.value) return 'adb logcat 正在运行'
  if (isReceivingLogs.value) return '正在接收代理推送的日志'
  if (connectionState.value === 'connecting') return '正在建立 SSE 连接...'
  if (runMode.value === 'local') {
    return agentReady.value
      ? '本地代理在线，可点击启动日志'
      : '请在本地终端运行一键启动命令'
  }
  return adbAvailable.value ? '点击启动按钮开始抓取日志' : '复制代理命令在本地终端运行'
})

/** 代理模式下是否正在接收日志（最近 5 秒内有新日志） */
const isReceivingLogs = ref(false)
let _lastReceiveCheck = 0
let _receiveCheckTimer = null
let _agentPollTimer = null

/** 代理模式下本地代理是否已就绪（通过心跳检测到） */
const agentReady = ref(false)

const filteredLines = computed(() => {
  let lines = allLines.value

  if (keyword.value.trim()) {
    const kw = keyword.value.trim().toLowerCase()
    lines = lines.filter(item => item.text.toLowerCase().includes(kw))
  }

  if (levelFilter.value.length < 6) {
    lines = lines.filter(item => {
      const m = item.text.match(/^\s*([VDIWEF])\//)
      return m ? levelFilter.value.includes(m[1]) : true
    })
  }

  if (lines.length > displayLimit.value) {
    lines = lines.slice(lines.length - displayLimit.value)
  }

  return lines
})

// -------------------------------------------------------------------
// 模式切换：选择本地时自动引导一键启动
// -------------------------------------------------------------------

watch(runMode, async (mode) => {
  if (mode === 'local') {
    await refreshAgentStatus()
    if (!agentReady.value) {
      localGuideVisible.value = true
      // 自动复制一键命令，减少手动操作
      nextTick(() => copyAgentCommand({ silent: false }))
    }
  } else {
    localGuideVisible.value = false
  }
})

watch(agentReady, (ready) => {
  if (ready && runMode.value === 'local') {
    localGuideVisible.value = false
    ElMessage.success('本地代理已连接')
  }
})

// -------------------------------------------------------------------
// 日志级别
// -------------------------------------------------------------------

function logLevelClass(item) {
  const m = item.text.match(/^\s*([VDIWEF])\//)
  if (!m) return ''
  const map = { V: 'log-v', D: 'log-d', I: 'log-i', W: 'log-w', E: 'log-e', F: 'log-f' }
  return map[m[1]] || ''
}

function highlightKeyword(text) {
  if (!keyword.value.trim()) return escapeHtml(text)
  const kw = keyword.value.trim()
  const escaped = escapeHtml(text)
  const re = new RegExp(`(${escapeRegex(kw)})`, 'gi')
  return escaped.replace(re, '<mark class="log-highlight">$1</mark>')
}

function escapeHtml(str) {
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
  return str.replace(/[&<>"']/g, c => map[c])
}

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// -------------------------------------------------------------------
// 启停操作
// -------------------------------------------------------------------

async function handleStart() {
  if (adbRunning.value || isReceivingLogs.value) return
  starting.value = true
  try {
    const res = await startLogcat(adbFilter.value.trim(), runMode.value)
    if (res.code === 0) {
      const mode = res.data?.mode || ''
      if (mode === 'local') {
        ElMessage.success('已向本地代理发送启动指令')
      } else {
        adbRunning.value = true
        ElMessage.success(res.message || 'adb logcat 已启动')
      }
    } else {
      ElMessage.error(res.message || '启动失败')
    }
  } catch {
    ElMessage.error('启动请求失败，请检查服务器连接')
  } finally {
    starting.value = false
  }
}

async function handleStop() {
  if (!adbRunning.value && !isReceivingLogs.value && runMode.value !== 'local') return
  stopping.value = true
  try {
    // 先刷新前端缓冲区中还在排队的日志
    if (_flushTimer) { clearTimeout(_flushTimer); _flushTimer = null }
    if (_renderBuffer.length) flushRenderBuffer()

    const res = await stopLogcat()
    if (res.code === 0) {
      adbRunning.value = false
      isReceivingLogs.value = false
      ElMessage.success(res.message || '已停止')
    } else {
      ElMessage.error(res.message || '停止失败')
    }
  } catch {
    ElMessage.error('停止请求失败')
  } finally {
    stopping.value = false
  }
}

/** 复制代理命令到剪贴板 */
function copyAgentCommand(opts = {}) {
  const silent = opts && opts.silent === true
  const text = agentCommand.value
  if (!text) return

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => {
      if (!silent) {
        ElMessage.success({ message: '一键启动命令已复制，粘贴到本地终端运行即可', duration: 4000 })
      }
    }).catch(() => fallbackCopy(text, silent))
    return
  }
  fallbackCopy(text, silent)
}

function fallbackCopy(text, silent = false) {
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.left = '-9999px'
  ta.style.top = '-9999px'
  document.body.appendChild(ta)
  ta.focus()
  ta.select()
  try {
    document.execCommand('copy')
    if (!silent) {
      ElMessage.success({ message: '一键启动命令已复制，粘贴到本地终端运行即可', duration: 4000 })
    }
  } catch {
    ElMessage.warning('复制失败，请手动选中命令复制')
  } finally {
    document.body.removeChild(ta)
  }
}

/** 下载可双击运行的启动脚本（macOS .command / Windows .bat） */
function downloadLauncher(format = 'command') {
  const url = getAgentBootstrapUrl(format)
  const a = document.createElement('a')
  a.href = url
  a.download = format === 'bat'
    ? 'start_gp_logcat_agent.bat'
    : 'start_gp_logcat_agent.command'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  ElMessage.success(
    format === 'bat'
      ? '已开始下载，双击 .bat 即可启动（需已安装 Python）'
      : '已开始下载，首次请在终端执行 chmod +x 后再双击运行',
  )
}

// -------------------------------------------------------------------
// SSE
// -------------------------------------------------------------------

function connectSSE() {
  disconnectSSE()
  const url = getStreamUrl()
  if (!url) return
  connectionState.value = 'connecting'
  eventSource = new EventSource(url)
  eventSource.onopen = () => { connectionState.value = 'connected' }
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.line) addLogLine(data.line)
    } catch { /* ignore */ }
  }
  eventSource.onerror = () => { connectionState.value = 'disconnected' }
}

function disconnectSSE() {
  if (eventSource) { eventSource.close(); eventSource = null }
  connectionState.value = 'disconnected'
}

// -------------------------------------------------------------------
// 日志批量渲染
// -------------------------------------------------------------------

function addLogLine(line) {
  _lastReceiveCheck = performance.now()
  if (!isReceivingLogs.value) isReceivingLogs.value = true
  if (!agentReady.value) agentReady.value = true
  if (paused.value) { pausedBuffer.push(line); return }
  _renderBuffer.push(line)
  if (_renderBuffer.length >= FLUSH_BATCH_MAX) { flushRenderBuffer(); return }
  scheduleFlush()
}

function flushRenderBuffer() {
  if (_flushTimer) { clearTimeout(_flushTimer); _flushTimer = null }
  const batch = _renderBuffer
  if (!batch.length) return
  _renderBuffer = []
  const items = batch.map(text => ({ text, originIndex: lineCounter++ }))
  allLines.value.push(...items)
  // 裁剪超出上限的旧数据
  if (allLines.value.length > MAX_BUFFER_LINES) {
    allLines.value = allLines.value.slice(-MAX_BUFFER_LINES)
  }
  if (autoScroll.value) scrollToBottom()
}

function scheduleFlush() {
  if (_flushTimer) return
  _flushTimer = setTimeout(() => { _flushTimer = null; flushRenderBuffer() }, FLUSH_INTERVAL)
}

function scrollToBottom() {
  nextTick(() => {
    const el = logContainer.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

// -------------------------------------------------------------------
// UI 操作
// -------------------------------------------------------------------

function pauseResume() {
  paused.value = !paused.value
  if (!paused.value && pausedBuffer.length) {
    const items = pausedBuffer.map(text => ({ text, originIndex: lineCounter++ }))
    allLines.value.push(...items)
    if (allLines.value.length > MAX_BUFFER_LINES) allLines.value = allLines.value.slice(-MAX_BUFFER_LINES)
    pausedBuffer = []
    scrollToBottom()
  }
}

function onAutoScrollChange(val) { if (val) scrollToBottom() }

function onLogScroll() {
  const el = logContainer.value
  if (!el) return
  const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30
  if (nearBottom && !autoScroll.value) autoScroll.value = true
  else if (!nearBottom && autoScroll.value) autoScroll.value = false
}

async function handleClear() {
  try {
    await ElMessageBox.confirm('确认清空所有日志？', '确认', {
      confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning',
    })
  } catch { return }

  allLines.value = []
  _renderBuffer = []
  pausedBuffer = []
  if (_flushTimer) { clearTimeout(_flushTimer); _flushTimer = null }
  lineCounter = 0
  try { await clearLogs() } catch { /* silent */ }
  ElMessage.success('日志已清空')
}

/** 轮询 status，根据心跳刷新代理在线状态 */
async function refreshAgentStatus() {
  try {
    const res = await getStatus()
    if (res.code === 0 && res.data) {
      adbAvailable.value = !!res.data.adb_available
      adbCheckMsg.value = res.data.adb_check_msg || ''
      adbRunning.value = !!res.data.adb_running
      if (res.data.adb_filter) adbFilter.value = res.data.adb_filter
      // 本地代理在线（心跳）
      if (typeof res.data.agent_online === 'boolean') {
        agentReady.value = res.data.agent_online
      }
    }
  } catch { /* silent */ }
}

// -------------------------------------------------------------------
// 生命周期
// -------------------------------------------------------------------

onMounted(async () => {
  await refreshAgentStatus()

  // 建立 SSE 连接
  connectSSE()

  // 定期检测代理模式下的日志接收状态（5 秒无新日志视为断开）
  _receiveCheckTimer = setInterval(() => {
    if (!adbRunning.value && isReceivingLogs.value) {
      if (performance.now() - _lastReceiveCheck > 5000) {
        isReceivingLogs.value = false
      }
    }
  }, 2000)

  // 本地模式下轮询代理心跳（约 2 秒）
  _agentPollTimer = setInterval(() => {
    if (runMode.value === 'local') {
      refreshAgentStatus()
    }
  }, 2000)
})

onUnmounted(() => {
  // 组件卸载时：清理定时器、刷新缓冲、停止 adb、关闭 SSE
  if (_receiveCheckTimer) { clearInterval(_receiveCheckTimer); _receiveCheckTimer = null }
  if (_agentPollTimer) { clearInterval(_agentPollTimer); _agentPollTimer = null }
  if (_flushTimer) { clearTimeout(_flushTimer); _flushTimer = null }
  if (_renderBuffer.length) flushRenderBuffer()
  if (adbRunning.value) stopLogcat().catch(() => {})
  disconnectSSE()
})
</script>

<style scoped>
/* ===== 页面整体 ===== */
.gp-logcat-page {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: calc(100vh - 56px - 20px - 20px);
}

/* ===== 控制栏 ===== */
.control-card :deep(.el-card__body) { padding: 10px 16px; }

.control-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.control-left,
.control-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 10px; height: 10px;
  border-radius: 50%; flex-shrink: 0;
}
.status-dot.connected  { background: #67c23a; box-shadow: 0 0 6px rgba(103,194,58,0.6); }
.status-dot.connecting { background: #e6a23c; animation: pulse 1s infinite; }
.status-dot.disconnected { background: #c0c4cc; }

@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

.log-count {
  display: flex; align-items: center; gap: 4px;
  font-size: 13px; color: #606266; white-space: nowrap;
}

/* 环境警告 */
.env-warning {
  display: flex; align-items: center; gap: 6px;
  margin-top: 8px; padding: 8px 12px;
  background: #fef0f0; border-radius: 4px;
  font-size: 12px; color: #f56c6c;
}

/* 过滤参数配置行 */
.filter-config-row {
  display: flex; align-items: center; gap: 8px;
  margin-top: 8px;
}
.filter-label { font-size: 12px; color: #606266; white-space: nowrap; }

.agent-hint {
  display: flex; align-items: center; gap: 6px;
  margin-top: 8px; padding: 6px 12px;
  background: #ecf5ff; border-radius: 4px;
  font-size: 12px; color: #409eff;
}

/* ===== 过滤区 ===== */
.filter-card :deep(.el-card__body) { padding: 10px 16px; }

.level-check { margin-right: 4px !important; }
.level-check.level-v :deep(.el-checkbox__label) { color: #909399; }
.level-check.level-d :deep(.el-checkbox__label) { color: #409eff; }
.level-check.level-i :deep(.el-checkbox__label) { color: #67c23a; }
.level-check.level-w :deep(.el-checkbox__label) { color: #e6a23c; }
.level-check.level-e :deep(.el-checkbox__label) { color: #f56c6c; }
.level-check.level-f :deep(.el-checkbox__label) { color: #9b59b6; }
.filter-right { display: flex; justify-content: flex-end; }

/* ===== 日志显示区 ===== */
.log-card {
  flex: 1; min-height: 0;
  display: flex; flex-direction: column;
}
.log-card :deep(.el-card__body) {
  flex: 1; min-height: 0; display: flex;
}

.log-container {
  flex: 1; min-height: 0;
  overflow-y: auto;
  background: #1e1e1e;
  font-family: 'Menlo', 'Monaco', 'Consolas', 'Courier New', monospace;
  font-size: 13px; line-height: 1.6;
}

.log-empty {
  display: flex; align-items: center; justify-content: center;
  height: 100%; min-height: 250px;
}

.empty-panel { text-align: center; }
.empty-icon { color: #909399; margin-bottom: 12px; }
.empty-title { font-size: 15px; font-weight: 500; color: #606266; margin-bottom: 6px; }
.empty-desc { font-size: 13px; color: #909399; margin-bottom: 4px; }

/* 空状态中的命令块 */
.command-block-inline {
  margin: 12px auto 0;
  max-width: 680px;
  text-align: left;
}
.command-pre-inline {
  margin: 0;
  padding: 10px 14px;
  background: #1e1e1e;
  border-radius: 6px;
  border: 1px solid #409eff;
  overflow-x: auto;
  cursor: pointer;
  transition: background 0.15s;
}
.command-pre-inline:hover { background: #252525; }
.command-pre-inline code {
  color: #d4d4d4;
  font-family: 'Menlo', 'Monaco', 'Consolas', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: nowrap;
  user-select: all;
}

.log-lines { padding: 4px 0; }

.log-line {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 1px 12px; cursor: default;
  border-left: 3px solid transparent;
  /* 浏览器级虚拟化：仅渲染视口内可见行，大幅降低 DOM 开销 */
  content-visibility: auto;
  contain-intrinsic-size: auto 22px;
}
.log-line:hover { background: rgba(255,255,255,0.05); }

.line-num {
  color: #555; font-size: 11px;
  min-width: 40px; text-align: right;
  user-select: none; flex-shrink: 0;
}

.line-text { color: #d4d4d4; white-space: pre-wrap; word-break: break-all; }

.log-v { border-left-color: #909399; }
.log-d .line-text { color: #569cd6; } .log-d { border-left-color: #569cd6; }
.log-i .line-text { color: #6a9955; } .log-i { border-left-color: #6a9955; }
.log-w .line-text { color: #e6a23c; } .log-w { border-left-color: #e6a23c; }
.log-e .line-text { color: #f44747; } .log-e { border-left-color: #f44747; }
.log-f .line-text { color: #c586c0; } .log-f { border-left-color: #c586c0; }

:deep(.log-highlight) {
  background: #d4a72c; color: #1e1e1e;
  padding: 0 2px; border-radius: 2px;
}
</style>
