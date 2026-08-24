<template>
  <div class="img-recognize">
    <el-card shadow="never" class="main-card">
      <template #header>
        <div class="card-title">
          <span class="title-text">图片文字识别</span>
          <el-tag size="small" type="info" effect="plain"
            >服务端腾讯云 OCR，上传原图识别</el-tag>
        </div>
      </template>

      <div
        ref="pasteZoneRef"
        class="paste-zone"
        tabindex="0"
        @paste="onPaste"
        @dragover.prevent
        @drop.prevent="onDrop"
        @click="focusPasteZone"
      >
        <input
          ref="fileInputRef"
          type="file"
          accept="image/*"
          class="file-input"
          @change="onFileChange"
        />
        <template v-if="!displayImageUrl">
          <el-icon class="zone-icon"><Picture /></el-icon>
          <p class="zone-hint">点击此处聚焦后，使用 <kbd>Ctrl</kbd>+<kbd>V</kbd> 粘贴图片</p>
          <p class="zone-sub">或拖拽图片到此处，也可点击下方按钮选择文件</p>
          <el-button type="primary" plain @click.stop="triggerFile">选择图片</el-button>
        </template>
        <div v-else class="preview-wrap">
          <img :src="displayImageUrl" alt="预览缩略图" class="preview-img" />
          <p class="preview-hint">以下为页面缩略图；识别始终使用原图分辨率。</p>
          <div class="preview-actions">
            <el-button size="small" @click.stop="triggerFile">更换图片</el-button>
            <el-button size="small" type="danger" plain @click.stop="clearImage">清除</el-button>
            <el-button
              type="primary"
              size="small"
              :loading="ocrLoading"
              :disabled="!hasOcrImage"
              @click.stop="runOcr"
            >
              开始识别
            </el-button>
          </div>
        </div>
      </div>

      <div v-if="ocrLoading && ocrStatusText" class="ocr-progress-line">
        <el-progress
          :percentage="ocrProgressIndeterminate ? 0 : ocrProgress"
          :indeterminate="ocrProgressIndeterminate"
          :stroke-width="6"
        />
        <span class="ocr-status">{{ ocrStatusText }}</span>
      </div>

      <el-divider content-position="left">识别结果</el-divider>

      <div class="result-toolbar">
        <el-button
          type="primary"
          :disabled="!resultText.trim()"
          @click="copyResult"
        >
          复制文字
        </el-button>
        <el-button v-if="resultText" plain @click="resultText = ''">清空结果</el-button>
      </div>
      <el-input
        v-model="resultText"
        type="textarea"
        :rows="12"
        placeholder="识别出的文字将显示在这里…"
        class="result-textarea"
        readonly
      />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Picture } from '@element-plus/icons-vue'
import { ocrImageByServer } from '../../api/tools/imageOcr.js'

/** 页面预览缩略图最大边（仅展示；识别使用原图 blob） */
const PREVIEW_THUMB_MAX_EDGE = 560

const pasteZoneRef = ref(null)
const fileInputRef = ref(null)
const displayImageUrl = ref('')
/** 是否有可上传识别的原图（供模板绑定） */
const hasOcrImage = ref(false)
/** 原图 Object URL */
let ocrObjectUrl = ''
let thumbObjectUrl = ''
let previewLoadSeq = 0

const resultText = ref('')
const ocrLoading = ref(false)
const ocrProgress = ref(0)
const ocrProgressIndeterminate = ref(false)
const ocrStatusText = ref('')

/**
 * 从原图 URL 生成缩略图 Object URL（仅用于页面展示）
 * @param {string} fullImageUrl 原图 blob URL
 * @param {number} maxEdge
 * @returns {Promise<string | null>}
 */
function createThumbnailObjectUrl(fullImageUrl, maxEdge) {
  return new Promise((resolve) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      try {
        const w0 = img.naturalWidth
        const h0 = img.naturalHeight
        if (!w0 || !h0) {
          resolve(null)
          return
        }
        const scale = Math.min(1, maxEdge / Math.max(w0, h0))
        const tw = Math.max(1, Math.round(w0 * scale))
        const th = Math.max(1, Math.round(h0 * scale))
        const c = document.createElement('canvas')
        c.width = tw
        c.height = th
        const ctx = c.getContext('2d')
        if (!ctx) {
          resolve(null)
          return
        }
        ctx.imageSmoothingEnabled = true
        ctx.imageSmoothingQuality = 'high'
        ctx.drawImage(img, 0, 0, tw, th)
        c.toBlob(
          (blob) => {
            if (!blob) {
              resolve(null)
              return
            }
            resolve(URL.createObjectURL(blob))
          },
          'image/jpeg',
          0.88
        )
      } catch {
        resolve(null)
      }
    }
    img.onerror = () => resolve(null)
    img.src = fullImageUrl
  })
}

function focusPasteZone() {
  pasteZoneRef.value?.focus?.()
}

function triggerFile() {
  fileInputRef.value?.click?.()
}

function revokeAllPreviewObjectUrls() {
  hasOcrImage.value = false
  if (ocrObjectUrl) {
    URL.revokeObjectURL(ocrObjectUrl)
    ocrObjectUrl = ''
  }
  if (thumbObjectUrl) {
    URL.revokeObjectURL(thumbObjectUrl)
    thumbObjectUrl = ''
  }
}

function setPreviewFromFile(file) {
  if (!file || !file.type.startsWith('image/')) {
    ElMessage.warning('请选择图片文件')
    return
  }
  revokeAllPreviewObjectUrls()
  previewLoadSeq += 1
  const seq = previewLoadSeq

  ocrObjectUrl = URL.createObjectURL(file)
  hasOcrImage.value = true
  displayImageUrl.value = ocrObjectUrl
  resultText.value = ''

  createThumbnailObjectUrl(ocrObjectUrl, PREVIEW_THUMB_MAX_EDGE).then((thumbUrl) => {
    if (seq !== previewLoadSeq) {
      if (thumbUrl) URL.revokeObjectURL(thumbUrl)
      return
    }
    if (!thumbUrl) return
    if (thumbObjectUrl) URL.revokeObjectURL(thumbObjectUrl)
    thumbObjectUrl = thumbUrl
    displayImageUrl.value = thumbUrl
  })
}

function onPaste(e) {
  const items = e.clipboardData?.items
  if (!items?.length) return
  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    if (item.kind === 'file' && item.type.startsWith('image/')) {
      const file = item.getAsFile()
      if (file) {
        e.preventDefault()
        setPreviewFromFile(file)
        return
      }
    }
  }
}

function onDrop(e) {
  const file = e.dataTransfer?.files?.[0]
  if (file) setPreviewFromFile(file)
}

function onFileChange(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (file) setPreviewFromFile(file)
}

function clearImage() {
  revokeAllPreviewObjectUrls()
  previewLoadSeq += 1
  displayImageUrl.value = ''
  resultText.value = ''
}

/** 与后端 _normalize_ocr_text 一致：逐行去尾空白、去掉末尾空行 */
function normalizeServerOcrText(text) {
  if (text == null || text === '') return ''
  const normalized = String(text).replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const lines = normalized.split('\n').map((ln) => ln.trimEnd())
  while (lines.length && lines[lines.length - 1] === '') lines.pop()
  return lines.join('\n')
}

async function runOcr() {
  if (!ocrObjectUrl) {
    ElMessage.warning('请先粘贴或选择一张图片')
    return
  }
  ocrLoading.value = true
  ocrProgress.value = 0
  ocrProgressIndeterminate.value = true
  ocrStatusText.value = '上传并识别…'
  resultText.value = ''
  try {
    const blob = await fetch(ocrObjectUrl).then((r) => r.blob())
    const file = new File([blob], 'image.png', { type: blob.type || 'image/png' })
    const text = await ocrImageByServer(file)
    resultText.value = normalizeServerOcrText(text)
    if (!resultText.value) {
      ElMessage.info('未识别到文字，请检查图片清晰度或腾讯云 OCR 配置')
    } else {
      ElMessage.success('识别完成')
    }
  } catch (err) {
    console.error(err)
    ElMessage.error(err?.message || '识别失败，请重试')
  } finally {
    ocrLoading.value = false
    ocrProgress.value = 0
    ocrProgressIndeterminate.value = false
    ocrStatusText.value = ''
  }
}

async function copyResult() {
  const text = resultText.value.trim()
  if (!text) {
    ElMessage.warning('没有可复制的内容')
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    try {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.left = '-9999px'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      ElMessage.success('已复制到剪贴板')
    } catch {
      ElMessage.error('复制失败，请手动全选复制')
    }
  }
}

onUnmounted(() => {
  revokeAllPreviewObjectUrls()
})
</script>

<style scoped>
.img-recognize {
  padding: 0 4px 16px;
}

.main-card {
  border-radius: 8px;
}

.card-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.title-text {
  font-size: 16px;
  font-weight: 600;
}

.paste-zone {
  min-height: 200px;
  border: 1px dashed var(--el-border-color);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 24px;
  text-align: center;
  cursor: default;
  outline: none;
  transition: border-color 0.2s, background 0.2s;
}

.paste-zone:focus {
  border-color: var(--el-color-primary);
  background: var(--el-fill-color-light);
}

.zone-icon {
  font-size: 48px;
  color: var(--el-text-color-secondary);
}

.zone-hint {
  margin: 0;
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.zone-hint kbd {
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid var(--el-border-color);
  font-size: 12px;
  background: var(--el-fill-color);
}

.zone-sub {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.file-input {
  display: none;
}

.preview-wrap {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.preview-img {
  max-width: 100%;
  max-height: 360px;
  object-fit: contain;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
}

.preview-hint {
  margin: -4px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}

.preview-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

.ocr-progress-line {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: stretch;
  margin-top: 16px;
  width: 100%;
}

.ocr-progress-line :deep(.el-progress) {
  width: 100%;
}

.ocr-status {
  display: block;
  margin-top: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
  width: 100%;
  box-sizing: border-box;
}

.result-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.result-textarea :deep(textarea) {
  font-family: ui-monospace, monospace;
  font-size: 13px;
  white-space: pre;
  overflow-x: auto;
  line-height: 1.35;
}
</style>
