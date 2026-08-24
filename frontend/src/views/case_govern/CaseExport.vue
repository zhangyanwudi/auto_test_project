<template>
  <div class="case-export-page">
    <div class="export-tip">
      <el-icon v-if="exporting" class="is-loading"><Loading /></el-icon>
      {{ exporting ? '正在导出 PDF…' : '导出完成，可关闭窗口' }}
    </div>
    <div class="export-header">
      <div class="export-title">
        {{ caseName || '用例' }}
        <span class="export-meta">更新时间：{{ updateTime || '—' }}</span>
      </div>
    </div>
    <MindMapEditor
      v-if="caseId"
      :case-id="caseId"
      :case-name="caseName"
      @back="closeWindow"
      @saved="() => {}"
      @loaded="onLoaded"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import html2canvas from 'html2canvas'
import { jsPDF } from 'jspdf'
import { fetchCaseList } from '../../api/case_govern/caseGovern.js'
import MindMapEditor from './MindMapEditor.vue'

const route = useRoute()
const caseId = ref(null)
const caseName = ref('')
const updateTime = ref('')
const exporting = ref(true)
let exported = false
let exportTimer = null

function parseId() {
  const raw = Number(route.params.id)
  caseId.value = Number.isFinite(raw) && raw > 0 ? raw : null
}

async function loadName() {
  if (!caseId.value) return
  try {
    const res = await fetchCaseList()
    if (res.code === 0 && Array.isArray(res.data)) {
      const found = res.data.find((c) => c.id === caseId.value)
      if (found) {
        caseName.value = found.case_name || ''
        updateTime.value = found.update_time || ''
      }
    }
  } catch {
    // 静默失败
  }
}

function closeWindow() {
  window.close()
}

async function exportPdf() {
  if (exported) return
  exported = true
  if (exportTimer) {
    clearTimeout(exportTimer)
    exportTimer = null
  }
  const content = document.querySelector('.case-export-page .mind-content')
  const header = document.querySelector('.case-export-page .export-header')
  if (!content) {
    exporting.value = false
    ElMessage.error('导出失败：未找到思维导图内容')
    return
  }
  // html2canvas 对百分比尺寸的 SVG 兼容性较差，截图前固定为内容实际像素尺寸
  const svg = content.querySelector('.mind-links')
  if (svg) {
    svg.style.width = `${content.scrollWidth}px`
    svg.style.height = `${content.scrollHeight}px`
  }
  try {
    const opts = { scale: 2, backgroundColor: '#ffffff', logging: false, useCORS: true }
    const contentCanvas = await html2canvas(content, opts)
    const headerCanvas = header ? await html2canvas(header, opts) : null

    // 头部信息（用例名 + 更新时间）与思维导图内容垂直拼接为一张图
    const merged = document.createElement('canvas')
    const mergedW = Math.max(contentCanvas.width, headerCanvas ? headerCanvas.width : 0)
    const mergedH = contentCanvas.height + (headerCanvas ? headerCanvas.height : 0)
    merged.width = mergedW
    merged.height = mergedH
    const ctx = merged.getContext('2d')
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, mergedW, mergedH)
    let offsetY = 0
    if (headerCanvas) {
      ctx.drawImage(headerCanvas, (mergedW - headerCanvas.width) / 2, 0)
      offsetY = headerCanvas.height
    }
    ctx.drawImage(contentCanvas, (mergedW - contentCanvas.width) / 2, offsetY)

    const imgData = merged.toDataURL('image/png')
    const pdf = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' })
    const pageW = pdf.internal.pageSize.getWidth()
    const pageH = pdf.internal.pageSize.getHeight()
    const ratio = Math.min(pageW / merged.width, pageH / merged.height)
    const w = merged.width * ratio
    const h = merged.height * ratio
    pdf.addImage(imgData, 'PNG', (pageW - w) / 2, (pageH - h) / 2, w, h)
    pdf.save(`${caseName.value || '用例'}_用例.pdf`)
    exporting.value = false
    setTimeout(() => window.close(), 800)
  } catch (e) {
    exporting.value = false
    ElMessage.error('导出失败：' + (e.message || e))
  }
}

function onLoaded() {
  // 思维导图数据已加载，再等节点渲染与 SVG 连线完成后截图导出
  if (exported) return
  if (exportTimer) clearTimeout(exportTimer)
  exportTimer = setTimeout(exportPdf, 400)
}

onMounted(async () => {
  parseId()
  await loadName()
  // 兜底：万一 loaded 事件未触发，8 秒后强制导出
  exportTimer = setTimeout(exportPdf, 8000)
})
</script>

<style scoped>
.case-export-page {
  padding: 12px;
  background: #f0f2f5;
  min-height: 100vh;
  box-sizing: border-box;
}

.export-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  font-size: 13px;
  color: #606266;
}

.export-header {
  display: inline-block;
  min-width: 200px;
  padding: 12px 16px;
  margin-bottom: 12px;
  background: #fff;
  border-radius: 6px;
}

.export-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  line-height: 1.4;
}

.export-meta {
  font-size: 13px;
  font-weight: 400;
  color: #909399;
  white-space: nowrap;
}

/* 导出页仅展示画布，隐藏工具栏与右侧编辑面板 */
.case-export-page :deep(.mind-toolbar),
.case-export-page :deep(.mind-panel) {
  display: none !important;
}

.case-export-page :deep(.mind-editor) {
  height: auto !important;
  border: none !important;
  overflow: visible !important;
}

.case-export-page :deep(.mind-body) {
  height: auto !important;
  display: block !important;
}

.case-export-page :deep(.mind-canvas) {
  overflow: visible !important;
  padding: 16px !important;
  background: none !important;
}
</style>
