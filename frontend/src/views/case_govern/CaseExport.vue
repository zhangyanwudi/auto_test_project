<template>
  <div class="case-export-page">
    <div class="export-header">
      <div class="export-title">
        {{ caseName || '用例' }}
        <span class="export-meta">更新时间：{{ updateTime || '—' }}</span>
      </div>
      <div class="export-actions">
        <el-button type="primary" size="small" :loading="exporting" @click="exportXmind">
          下载 XMind（推荐）
        </el-button>
        <el-button size="small" :loading="exporting" @click="exportSvg">下载 SVG</el-button>
        <el-button size="small" :loading="exporting" @click="exportPng">下载 PNG</el-button>
        <el-button size="small" :loading="exporting" @click="exportPdf">下载 PDF</el-button>
      </div>
    </div>

    <MindMapEditor
      v-if="caseId"
      :case-id="caseId"
      :case-name="caseName"
      readonly
      expand-on-load
      @back="() => {}"
      @saved="() => {}"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import html2canvas from 'html2canvas'
import { jsPDF } from 'jspdf'
import { fetchCaseList, exportXmindFile } from '../../api/case_govern/caseGovern.js'
import MindMapEditor from './MindMapEditor.vue'

const route = useRoute()
const caseId = ref(null)
const caseName = ref('')
const updateTime = ref('')
const exporting = ref(false)

const TYPE_LABELS = { module: '模块', case: '用例', step: '步骤', expect: '预期', precondition: '前置条件', result: '结果' }
const TYPE_COLORS = { module: '#409eff', case: '#67c23a', step: '#909399', expect: '#e6a23c', precondition: '#b882ff', result: '#13c2c2' }
const EXEC_COLORS = { '通过': '#67c23a', '不通过': '#f56c6c', '未执行': '#909399' }

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

function escapeXml(s) {
  return String(s).replace(/[<>&"']/g, (c) => ({
    '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&apos;',
  }[c]))
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function downloadText(text, filename, mime) {
  downloadBlob(new Blob([text], { type: mime }), filename)
}

/* ---- SVG 导出：矢量文本，体积小，可缩放、可搜索 ---- */

function collectSvgData(content) {
  const cr = content.getBoundingClientRect()
  const nodes = []
  content.querySelectorAll('.tcard[data-node-id]').forEach((card) => {
    const r = card.getBoundingClientRect()
    const type = (card.className.match(/tcard--(\w+)/) || [])[1] || 'case'
    const titleEl = card.querySelector('.tcard-title')
    const title = titleEl ? titleEl.innerText : ''
    const execEl = card.querySelector('.tcard-exec')
    const exec = execEl ? execEl.innerText.trim() : ''
    nodes.push({
      x: r.left - cr.left,
      y: r.top - cr.top,
      w: r.width,
      h: r.height,
      type,
      title: title || '（图片节点）',
      exec,
    })
  })
  const links = []
  content.querySelectorAll('.mind-links path').forEach((p) => {
    const d = p.getAttribute('d')
    if (d) links.push(d)
  })
  return { width: cr.width, height: cr.height, nodes, links }
}

function buildSvg(data) {
  const titleH = 44
  const w = data.width
  const h = data.height + titleH
  let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">`
  svg += `<rect width="100%" height="100%" fill="#ffffff"/>`
  // 标题区
  svg += `<text x="16" y="24" font-family="sans-serif" font-size="16" font-weight="600" fill="#303133">${escapeXml(caseName.value || '用例')}</text>`
  svg += `<text x="16" y="40" font-family="sans-serif" font-size="12" fill="#909399">更新时间：${escapeXml(updateTime.value || '—')}</text>`
  // 内容区（整体下移标题高度）
  svg += `<g transform="translate(0,${titleH})">`
  svg += `<g fill="none" stroke="#d5d9e2" stroke-width="1.5">`
  data.links.forEach((d) => { svg += `<path d="${d}"/>` })
  svg += `</g>`
  data.nodes.forEach((n) => {
    const color = TYPE_COLORS[n.type] || '#909399'
    const label = TYPE_LABELS[n.type] || '用例'
    svg += `<g>`
    svg += `<rect x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" rx="8" fill="#ffffff" stroke="#dcdfe6" stroke-width="1.5"/>`
    // 标题（支持多行）
    const lines = n.title.split('\n')
    svg += `<text x="${n.x + 12}" y="${n.y + 20}" font-family="sans-serif" font-size="13" fill="#303133">`
    lines.forEach((line, i) => {
      svg += `<tspan x="${n.x + 12}" dy="${i === 0 ? 0 : 16}">${escapeXml(line)}</tspan>`
    })
    svg += `</text>`
    // 类型标签 + 执行结果
    svg += `<text x="${n.x + 12}" y="${n.y + n.h - 10}" font-family="sans-serif" font-size="10" fill="${color}">${label}</text>`
    if (n.exec) {
      svg += `<text x="${n.x + n.w - 12}" y="${n.y + n.h - 10}" font-family="sans-serif" font-size="10" fill="${EXEC_COLORS[n.exec] || '#909399'}" text-anchor="end">${escapeXml(n.exec)}</text>`
    }
    svg += `</g>`
  })
  svg += `</g>`
  svg += `</svg>`
  return svg
}

async function exportXmind() {
  if (exporting.value) return
  exporting.value = true
  try {
    const blob = await exportXmindFile(caseId.value)
    downloadBlob(blob, `${caseName.value || '用例'}_用例.xmind`)
    ElMessage.success('XMind 已导出')
  } catch (e) {
    ElMessage.error('导出失败：' + (e.message || e))
  } finally {
    exporting.value = false
  }
}

function exportSvg() {
  if (exporting.value) return
  exporting.value = true
  try {
    const content = document.querySelector('.case-export-page .mind-content')
    if (!content) throw new Error('未找到思维导图内容')
    const data = collectSvgData(content)
    const svg = buildSvg(data)
    downloadText(svg, `${caseName.value || '用例'}_用例.svg`, 'image/svg+xml;charset=utf-8')
    ElMessage.success('SVG 已导出')
  } catch (e) {
    ElMessage.error('导出失败：' + (e.message || e))
  } finally {
    exporting.value = false
  }
}

/* ---- PNG / PDF 导出：基于 html2canvas 截图 ---- */

async function renderMergedCanvas() {
  const content = document.querySelector('.case-export-page .mind-content')
  const header = document.querySelector('.case-export-page .export-title')
  if (!content) throw new Error('未找到思维导图内容')
  // html2canvas 对百分比尺寸的 SVG 兼容性较差，截图前固定为内容实际像素尺寸
  const svg = content.querySelector('.mind-links')
  if (svg) {
    svg.style.width = `${content.scrollWidth}px`
    svg.style.height = `${content.scrollHeight}px`
  }
  const opts = { scale: 2, backgroundColor: '#ffffff', logging: false, useCORS: true }
  const contentCanvas = await html2canvas(content, opts)
  const headerCanvas = header ? await html2canvas(header, opts) : null

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
  return merged
}

async function exportPng() {
  if (exporting.value) return
  exporting.value = true
  try {
    const canvas = await renderMergedCanvas()
    await new Promise((resolve, reject) => {
      canvas.toBlob((blob) => {
        if (!blob) { reject(new Error('PNG 生成失败')); return }
        downloadBlob(blob, `${caseName.value || '用例'}_用例.png`)
        resolve()
      }, 'image/png')
    })
    ElMessage.success('PNG 已导出')
  } catch (e) {
    ElMessage.error('导出失败：' + (e.message || e))
  } finally {
    exporting.value = false
  }
}

async function exportPdf() {
  if (exporting.value) return
  exporting.value = true
  try {
    const merged = await renderMergedCanvas()
    const imgData = merged.toDataURL('image/png')
    const pdf = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' })
    const pageW = pdf.internal.pageSize.getWidth()
    const pageH = pdf.internal.pageSize.getHeight()
    const ratio = Math.min(pageW / merged.width, pageH / merged.height)
    const w = merged.width * ratio
    const h = merged.height * ratio
    pdf.addImage(imgData, 'PNG', (pageW - w) / 2, (pageH - h) / 2, w, h)
    pdf.save(`${caseName.value || '用例'}_用例.pdf`)
    ElMessage.success('PDF 已导出')
  } catch (e) {
    ElMessage.error('导出失败：' + (e.message || e))
  } finally {
    exporting.value = false
  }
}

onMounted(async () => {
  parseId()
  await loadName()
})
</script>

<style scoped>
.case-export-page {
  padding: 12px;
  background: #f0f2f5;
  min-height: 100vh;
  box-sizing: border-box;
}

.export-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 12px 16px;
  margin-bottom: 12px;
  background: #fff;
  border-radius: 6px;
  box-sizing: border-box;
}

.export-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
  min-width: 0;
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

.export-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
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
