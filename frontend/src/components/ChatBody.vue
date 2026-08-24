<template>
  <div
    class="chat-body"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <!-- 拖拽遮罩层 -->
    <transition name="drag-fade">
      <div v-if="isDragging" class="drag-overlay">
        <div class="drag-overlay-box">
          <el-icon :size="40" class="drag-icon"><UploadFilled /></el-icon>
          <p class="drag-text">释放文件以上传</p>
          <p class="drag-hint">支持 .json / .xlsx / .xls / 图片 文件，最大 5MB</p>
        </div>
      </div>
    </transition>

    <!-- 消息列表 -->
    <div class="chat-messages" ref="messagesContainer">
      <div v-if="!sending && messages.length === 0" class="chat-welcome">
        <div class="welcome-icon">
          <el-icon :size="40"><ChatDotRound /></el-icon>
        </div>
        <p>你好！我是 AI 助手，有什么可以帮助你的？</p>
        <p class="welcome-hint">
          支持上传 JSON / Excel / 图片文件进行分析和比对<br>
          拖拽文件到对话框或粘贴文件即可上传
        </p>
      </div>
      <div
        v-for="(msg, idx) in messages"
        :key="idx"
        class="message-row"
        :class="msg.role === 'user' ? 'msg-user' : 'msg-assistant'"
      >
        <div class="message-bubble" :class="msg.role">
          <div v-if="msg.files && msg.files.length > 0" class="msg-files">
            <span
              v-for="f in msg.files"
              :key="f.file_id"
              class="msg-file-badge"
            >
              📎 {{ f.filename }}
            </span>
          </div>
          <div class="msg-content" v-html="renderContent(msg.content)"></div>
        </div>
      </div>
      <div v-if="sending" class="message-row msg-assistant">
        <div class="message-bubble assistant">
          <div class="msg-loading">
            <span class="dot"></span><span class="dot"></span><span class="dot"></span>
          </div>
        </div>
      </div>
    </div>

    <!-- 已上传待发送文件列表 -->
    <div v-if="uploadedFiles.length > 0" class="uploaded-files-bar">
      <div
        v-for="uf in uploadedFiles"
        :key="uf.file_id"
        class="file-card"
        :class="{ 'file-card-expanded': expandedFiles.has(uf.file_id) }"
      >
        <div class="file-card-header" @click="toggleFilePreview(uf.file_id)">
          <span class="file-card-icon">📄</span>
          <span class="file-card-name">{{ uf.filename }}</span>
          <span class="file-card-size">{{ uf.sizeText }}</span>
          <span v-if="uf.preview" class="file-card-expand-icon">
            <el-icon><ArrowDown v-if="!expandedFiles.has(uf.file_id)" /><ArrowUp v-else /></el-icon>
          </span>
          <el-button
            class="file-card-remove"
            :icon="Close"
            circle
            size="small"
            text
            @click.stop="handleRemoveFile(uf)"
          />
        </div>
        <div v-if="uf.preview && expandedFiles.has(uf.file_id)" class="file-card-preview">
          <pre>{{ uf.preview }}</pre>
        </div>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="chat-input-area">
      <el-select
        :model-value="modelProvider"
        class="model-select"
        size="small"
        @update:model-value="onModelChange"
      >
        <el-option
          v-for="p in modelProviders"
          :key="p.key"
          :label="p.label"
          :value="p.key"
        />
      </el-select>
      <el-input
        v-model="inputText"
        type="textarea"
        :rows="2"
        placeholder="输入消息，Enter 发送，Shift+Enter 换行；支持拖拽或粘贴文件上传"
        :disabled="sending"
        @keydown.enter.exact="handleSend"
        @paste="onPaste"
        resize="none"
      />
      <el-button
        type="primary"
        :icon="Promotion"
        :disabled="!canSend || sending"
        :loading="sending"
        @click="handleSend"
      >
        发送
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Promotion, UploadFilled, ArrowDown, ArrowUp, Close } from '@element-plus/icons-vue'
import { uploadFile } from '../api/ai_helper/index.js'

const props = defineProps({
  conversationCode: {
    type: String,
    default: '',
  },
  messages: {
    type: Array,
    default: () => [],
  },
  sending: {
    type: Boolean,
    default: false,
  },
  modelProvider: {
    type: String,
    default: 'gateway',
  },
  modelProviders: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['update:messages', 'send', 'update:modelProvider'])

// 本地消息列表（与父组件双向绑定）
const messages = computed({
  get: () => props.messages,
  set: (val) => emit('update:messages', val),
})

const MAX_UPLOAD_COUNT = 5
const MAX_FILE_SIZE = 5 * 1024 * 1024 // 5MB
const ALLOWED_EXTENSIONS = ['.json', '.xlsx', '.xls', '.png', '.jpg', '.jpeg', '.gif', '.webp']

const inputText = ref('')
const messagesContainer = ref(null)

// 已上传文件列表（已提交到后端，有 file_id）
const uploadedFiles = ref([])
// 展开预览的文件 ID 集合
const expandedFiles = ref(new Set())
// 正在上传的文件名集合
const uploadingSet = ref(new Set())

// 拖拽状态
const isDragging = ref(false)

// 监听外部 messages 变化时滚动
watch(() => props.messages.length, () => {
  scrollToBottom()
})

function scrollToBottom() {
  nextTick(() => {
    const el = messagesContainer.value
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  })
}

/**
 * 格式化文件大小
 */
function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

/**
 * 简易 Markdown 渲染
 */
function renderContent(text) {
  if (!text) return ''
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // 代码块 ```lang\ncode\n```
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_m, lang, code) => {
    const escaped = code
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
    return `<pre><code>${escaped}</code></pre>`
  })

  // 行内代码
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  // 粗体
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  // 链接
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
  // 换行
  html = html.replace(/\n/g, '<br>')

  return html
}

/**
 * 解析 AI 回复中的 [TOOL_CALL:...]...[/TOOL_CALL]
 */
function parseToolCall(reply) {
  const regex = /\[TOOL_CALL:(\w+)\]([\s\S]*?)\[\/TOOL_CALL\]/g
  let match
  let displayContent = reply
  let toolCall = null

  while ((match = regex.exec(reply)) !== null) {
    const toolName = match[1]
    const paramsStr = match[2].trim()
    try {
      const params = JSON.parse(paramsStr)
      toolCall = { name: toolName, params }
      displayContent = displayContent.replace(match[0], '')
    } catch {
      // JSON 解析失败，保留原文
    }
  }

  return {
    displayContent: displayContent.trim(),
    toolCall,
  }
}

function executeToolCall(toolCall) {
  if (toolCall.name === 'config_compare') {
    const payload = {
      tool: 'config_compare',
      params: toolCall.params,
    }
    sessionStorage.setItem('__ai_tool_call', JSON.stringify(payload))
    window.dispatchEvent(new CustomEvent('ai-tool-navigate', {
      detail: { menu: 'config_compare' },
    }))
    window.dispatchEvent(new CustomEvent('ai-tool-call-live', {
      detail: toolCall.params,
    }))
    messages.value.push({
      role: 'assistant',
      content: `✅ 已自动填入比对参数：**${toolCall.params.left_scheme}** vs **${toolCall.params.right_scheme}** …`,
    })
    scrollToBottom()
  }
}

// ─── 文件校验 & 上传核心逻辑 ──────────────────────────────

/** 校验单个文件：返回 null 表示通过，返回字符串表示错误消息 */
function validateFile(file) {
  const name = file.name.toLowerCase()
  const ext = ALLOWED_EXTENSIONS.find(e => name.endsWith(e))
  if (!ext) {
    return `不支持的文件类型，仅允许: ${ALLOWED_EXTENSIONS.join(', ')}`
  }
  if (file.size > MAX_FILE_SIZE) {
    return `文件大小不能超过 ${formatFileSize(MAX_FILE_SIZE)}`
  }
  return null
}

/** 生成文件内容预览 */
function buildContentPreview(content) {
  if (!content) return ''
  const lines = content.split('\n')
  if (lines.length <= 8) return content
  const preview = lines.slice(0, 8).join('\n')
  const moreHint = lines.length > 8 ? `\n... (预览共 ${lines.length} 行，已截断)` : ''
  return preview + moreHint
}

/** 上传单个文件并加入 uploadedFiles */
async function uploadSingleFile(rawFile) {
  const errMsg = validateFile(rawFile)
  if (errMsg) {
    ElMessage.warning(errMsg)
    return
  }

  if (uploadedFiles.value.length >= MAX_UPLOAD_COUNT) {
    ElMessage.warning(`最多上传 ${MAX_UPLOAD_COUNT} 个文件`)
    return
  }

  const fileName = rawFile.name
  uploadingSet.value.add(fileName)

  try {
    const res = await uploadFile(rawFile)
    if (res.code === 0 && res.data) {
      const fileEntry = {
        file_id: res.data.file_id,
        filename: res.data.filename,
        size: res.data.size,
        sizeText: formatFileSize(res.data.size),
        preview: buildContentPreview(res.data.content_preview || ''),
      }
      uploadedFiles.value.push(fileEntry)
      ElMessage.success(`已上传: ${res.data.filename}`)
    } else {
      ElMessage.error(res.message || '上传失败')
    }
  } catch {
    ElMessage.error('上传文件失败，请检查网络连接')
  } finally {
    uploadingSet.value.delete(fileName)
  }
}

// ─── 拖拽上传 ──────────────────────────────────────────

function onDragOver(e) {
  e.preventDefault()
  if (e.dataTransfer && e.dataTransfer.types.includes('Files')) {
    isDragging.value = true
  }
}

function onDragLeave(e) {
  if (!e.currentTarget.contains(e.relatedTarget)) {
    isDragging.value = false
  }
}

async function onDrop(e) {
  e.preventDefault()
  isDragging.value = false
  const files = e.dataTransfer?.files
  if (!files || files.length === 0) return

  for (const file of files) {
    await uploadSingleFile(file)
  }
}

// ─── 剪贴板粘贴 ────────────────────────────────────────

async function onPaste(e) {
  const items = e.clipboardData?.items
  if (!items) return

  const files = []
  for (const item of items) {
    if (item.kind === 'file') {
      const file = item.getAsFile()
      if (file) files.push(file)
    }
  }

  if (files.length > 0) {
    e.preventDefault()
    for (const file of files) {
      await uploadSingleFile(file)
    }
  }
}

// ─── 文件管理 ──────────────────────────────────────────

/** 移除已上传的文件 */
function handleRemoveFile(file) {
  uploadedFiles.value = uploadedFiles.value.filter(f => f.file_id !== file.file_id)
  expandedFiles.value.delete(file.file_id)
}

/** 切换模型后端 */
function onModelChange(val) {
  emit('update:modelProvider', val)
}

/** 展开/收起文件内容预览 */
function toggleFilePreview(fileId) {
  const s = new Set(expandedFiles.value)
  if (s.has(fileId)) {
    s.delete(fileId)
  } else {
    s.add(fileId)
  }
  expandedFiles.value = s
}

// ─── 发送消息 ──────────────────────────────────────────

/** 是否能发送：有文本或有已上传文件，且无正在上传中的文件 */
const canSend = computed(() => {
  const hasText = inputText.value.trim().length > 0
  const hasFiles = uploadedFiles.value.length > 0
  const hasUploading = uploadingSet.value.size > 0
  return (hasText || hasFiles) && !hasUploading
})

/** 发送消息（支持文本 + 文件同时发送） */
async function handleSend(e) {
  if (e) {
    if (e.shiftKey) return
    e.preventDefault()
  }
  const text = inputText.value.trim()
  const hasFiles = uploadedFiles.value.length > 0
  if (!text && !hasFiles) return
  if (props.sending) return
  if (uploadingSet.value.size > 0) {
    ElMessage.warning('还有文件正在上传中，请稍候')
    return
  }

  // 构建用户消息气泡
  const userMsg = { role: 'user', content: text || '请分析上传的文件' }
  if (hasFiles) {
    userMsg.files = [...uploadedFiles.value]
  }
  messages.value.push(userMsg)

  // 收集 file_ids
  const fileIds = uploadedFiles.value.map(f => f.file_id)

  // 清空输入
  inputText.value = ''
  uploadedFiles.value = []
  expandedFiles.value = new Set()
  scrollToBottom()

  // 通知父组件发送消息
  emit('send', {
    message: text || '请分析上传的文件',
    fileIds,
    onReply: (replyText) => {
      const { displayContent, toolCall } = parseToolCall(replyText)
      messages.value.push({ role: 'assistant', content: displayContent })
      if (toolCall) {
        executeToolCall(toolCall)
      }
    },
    onError: (errorMsg) => {
      ElMessage.error(errorMsg)
    },
  })
}
</script>

<style scoped>
/* ── 容器 ── */
.chat-body {
  display: flex;
  flex-direction: column;
  height: 100%;
  position: relative;
  overflow: hidden;
}

/* ── 拖拽遮罩层 ── */
.drag-overlay {
  position: absolute;
  inset: 0;
  z-index: 100;
  background: rgba(64, 158, 255, 0.08);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}

.drag-overlay-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px 48px;
  border: 2px dashed #409eff;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.9);
  pointer-events: auto;
}

.drag-icon {
  color: #409eff;
  animation: drag-icon-bounce 0.6s ease-in-out infinite alternate;
}

@keyframes drag-icon-bounce {
  from { transform: translateY(0); }
  to { transform: translateY(-4px); }
}

.drag-text {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #409eff;
}

.drag-hint {
  margin: 0;
  font-size: 12px;
  color: #909399;
}

.drag-fade-enter-active {
  transition: opacity 0.2s ease;
}
.drag-fade-leave-active {
  transition: opacity 0.15s ease;
}
.drag-fade-enter-from,
.drag-fade-leave-to {
  opacity: 0;
}

/* ── 消息区域 ── */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 16px 20px;
  background: #f5f7fa;
  min-height: 0;
}

/* 自定义滚动条 */
.chat-messages::-webkit-scrollbar {
  width: 6px;
}

.chat-messages::-webkit-scrollbar-track {
  background: transparent;
}

.chat-messages::-webkit-scrollbar-thumb {
  background: #c0c4cc;
  border-radius: 3px;
}

.chat-messages::-webkit-scrollbar-thumb:hover {
  background: #909399;
}

.chat-messages {
  scrollbar-width: thin;
  scrollbar-color: #c0c4cc transparent;
}

.chat-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: #909399;
}

.welcome-icon {
  color: #c0c4cc;
  margin-bottom: 12px;
}

.chat-welcome p {
  margin: 0;
  font-size: 14px;
}

.welcome-hint {
  margin-top: 10px !important;
  font-size: 12px !important;
  color: #a8abb2 !important;
  text-align: center;
  line-height: 1.7 !important;
}

/* ── 消息中的文件标签 ── */
.msg-files {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 6px;
}

.msg-file-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 11px;
  line-height: 1.6;
  background: rgba(0, 0, 0, 0.08);
  color: #606266;
}

.message-bubble.user .msg-file-badge {
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
}

/* ── 已上传文件栏 ── */
.uploaded-files-bar {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 12px;
  background: #fafafa;
  border-top: 1px solid #ebeef5;
  flex-shrink: 0;
  max-height: 180px;
  overflow-y: auto;
}

.file-card {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
  transition: border-color 0.2s;
}

.file-card:hover {
  border-color: #c0c4cc;
}

.file-card-expanded {
  border-color: #b3d8ff;
}

.file-card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  cursor: pointer;
  user-select: none;
}

.file-card-header:hover {
  background: #f5f7fa;
}

.file-card-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.file-card-name {
  flex: 1;
  font-size: 12px;
  font-weight: 500;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.file-card-parsed-tag {
  font-size: 10px;
  color: #fff;
  background: #67c23a;
  padding: 1px 6px;
  border-radius: 8px;
  flex-shrink: 0;
  line-height: 1.4;
}
.file-card-size {
  font-size: 11px;
  color: #909399;
  flex-shrink: 0;
}

.file-card-expand-icon {
  font-size: 12px;
  color: #909399;
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.file-card-remove {
  flex-shrink: 0;
  color: #c0c4cc;
  padding: 2px;
}

.file-card-remove:hover {
  color: #f56c6c;
  background: rgba(245, 108, 108, 0.1);
}

.file-card-preview {
  border-top: 1px solid #ebeef5;
  background: #fafbfc;
  padding: 0;
}

.file-card-preview pre {
  margin: 0;
  padding: 10px 14px;
  font-size: 11px;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  line-height: 1.5;
  color: #606266;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 160px;
  overflow-y: auto;
}

/* ── 输入区域 ── */
.chat-input-area {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 12px 20px;
  border-top: 1px solid #ebeef5;
  background: #fff;
  flex-shrink: 0;
}

.model-select {
  width: 160px;
  flex-shrink: 0;
  margin-bottom: 1px;
}

.chat-input-area :deep(.el-textarea__inner) {
  font-size: 14px;
  line-height: 1.55;
}

/* ── 消息气泡 ── */
.message-row {
  display: flex;
  margin-bottom: 14px;
}

.msg-user {
  justify-content: flex-end;
}

.msg-assistant {
  justify-content: flex-start;
}

.message-bubble {
  max-width: 80%;
  min-width: 0;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.65;
  overflow-wrap: break-word;
  word-break: break-word;
}

.message-bubble.user {
  background: #409eff;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.message-bubble.assistant {
  background: #fff;
  color: #303133;
  border-bottom-left-radius: 4px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.msg-content :deep(pre) {
  background: #f0f2f5;
  border-radius: 6px;
  padding: 10px;
  overflow-x: hidden;
  white-space: pre-wrap;
  overflow-wrap: break-word;
  word-break: break-all;
  margin: 6px 0;
  font-size: 13px;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
}

.msg-content :deep(code) {
  background: rgba(0, 0, 0, 0.06);
  padding: 2px 5px;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  overflow-wrap: break-word;
  word-break: break-all;
}

.msg-content :deep(pre code) {
  background: none;
  padding: 0;
}

.msg-content :deep(a) {
  color: #409eff;
}

.message-bubble.user .msg-content :deep(a) {
  color: #fff;
  text-decoration: underline;
}

/* ── 加载动画 ── */
.msg-loading {
  display: flex;
  gap: 5px;
  padding: 3px 0;
}

.msg-loading .dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #909399;
  animation: dot-bounce 1.4s infinite ease-in-out both;
}

.msg-loading .dot:nth-child(1) {
  animation-delay: -0.32s;
}

.msg-loading .dot:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes dot-bounce {
  0%, 80%, 100% {
    transform: scale(0.6);
    opacity: 0.4;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}
</style>
