<template>
  <div class="ai-helper-container">
    <!-- 左侧对话列表 -->
    <div class="sidebar">
      <div class="sidebar-header">
        <el-button type="primary" :icon="Plus" @click="handleNewConversation" :loading="creatingConversation">
          新对话
        </el-button>
      </div>
      <div class="conversation-list" v-loading="listLoading">
        <div
          v-for="conv in conversations"
          :key="conv.conversation_code"
          class="conversation-item"
          :class="{ active: currentCode === conv.conversation_code }"
          @click="selectConversation(conv.conversation_code)"
        >
          <div class="conv-info">
            <div class="conv-title">{{ conv.title || '新对话' }}</div>
            <div class="conv-time">{{ formatTime(conv.update_time) }}</div>
          </div>
          <el-button
            class="conv-delete"
            :icon="Delete"
            text
            size="small"
            @click.stop="handleDeleteConversation(conv.conversation_code)"
          />
        </div>
        <el-empty v-if="!listLoading && conversations.length === 0" description="暂无对话" :image-size="60" />
      </div>
      <div class="sidebar-footer">
        <el-button
          type="danger"
          :icon="Delete"
          plain
          :disabled="conversations.length === 0"
          :loading="clearingAll"
          @click="handleClearAllConversations"
        >
          清空全部对话
        </el-button>
      </div>
    </div>

    <!-- 右侧聊天区域 -->
    <div class="chat-area">
      <!-- 无对话时的欢迎页 -->
      <div v-if="!currentCode" class="welcome">
        <div class="welcome-icon">
          <el-icon :size="64"><ChatDotRound /></el-icon>
        </div>
        <h2>AI 助手</h2>
        <p>点击左侧「新对话」开始与 AI 交流</p>
        <p class="welcome-hint">
          支持上传 JSON / Excel / 图片文件进行分析和比对<br>
          拖拽文件到对话框或粘贴文件即可上传
        </p>
      </div>

      <!-- 对话界面 -->
      <template v-else>
        <div class="chat-header">
          <span class="chat-title">{{ currentTitle }}</span>
          <el-button
            type="danger"
            :icon="Delete"
            text
            size="small"
            :disabled="messages.length === 0"
            :loading="clearingMessages"
            @click="handleClearConversationMessages"
          >
            清空消息
          </el-button>
        </div>
        <ChatBody
          :conversation-code="currentCode"
          v-model:messages="messages"
          :sending="sending"
          :model-provider="modelProvider"
          :model-providers="modelProviders"
          @update:model-provider="modelProvider = $event"
          @send="onSend"
        />
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, ChatDotRound } from '@element-plus/icons-vue'
import {
  fetchConversations,
  createConversation,
  deleteConversation,
  fetchConversationMessages,
  sendMessage,
  clearAllConversations,
  clearConversationMessages,
  fetchModels,
} from '../../api/ai_helper/index.js'
import ChatBody from '../../components/ChatBody.vue'

const conversations = ref([])
const currentCode = ref('')
const messages = ref([])
const sending = ref(false)
const listLoading = ref(false)
const creatingConversation = ref(false)
const clearingAll = ref(false)
const clearingMessages = ref(false)
const modelProvider = ref('gateway')
const modelProviders = ref([])

const currentTitle = computed(() => {
  const conv = conversations.value.find((c) => c.conversation_code === currentCode.value)
  return conv ? (conv.title || '新对话') : ''
})

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = now - d
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}小时前`
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hour = String(d.getHours()).padStart(2, '0')
  const minute = String(d.getMinutes()).padStart(2, '0')
  if (d.getFullYear() === now.getFullYear()) {
    return `${month}-${day} ${hour}:${minute}`
  }
  return `${d.getFullYear()}-${month}-${day}`
}

async function loadConversations() {
  listLoading.value = true
  try {
    const res = await fetchConversations()
    if (res.code === 0) {
      conversations.value = res.data || []
    }
  } catch {
    // 401 等由全局拦截处理
  } finally {
    listLoading.value = false
  }
}

async function loadMessages(conversationCode) {
  try {
    const res = await fetchConversationMessages(conversationCode)
    if (res.code === 0) {
      messages.value = res.data || []
    }
  } catch {
    // ignore
  }
}

function selectConversation(code) {
  if (currentCode.value === code) return
  currentCode.value = code
  messages.value = []
  loadMessages(code)
}

async function handleNewConversation() {
  creatingConversation.value = true
  try {
    const res = await createConversation()
    if (res.code === 0 && res.data) {
      conversations.value.unshift(res.data)
      selectConversation(res.data.conversation_code)
    } else {
      ElMessage.error(res.message || '创建失败')
    }
  } catch {
    ElMessage.error('创建对话失败')
  } finally {
    creatingConversation.value = false
  }
}

async function handleDeleteConversation(code) {
  try {
    await ElMessageBox.confirm('确定要删除该对话吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    const res = await deleteConversation(code)
    if (res.code === 0) {
      conversations.value = conversations.value.filter((c) => c.conversation_code !== code)
      if (currentCode.value === code) {
        currentCode.value = ''
        messages.value = []
      }
      ElMessage.success('已删除')
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  } catch {
    ElMessage.error('删除失败')
  }
}

async function handleClearAllConversations() {
  try {
    await ElMessageBox.confirm(
      '确定要清空全部对话记录吗？此操作不可恢复。',
      '清空全部对话',
      {
        confirmButtonText: '确定清空',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }
  clearingAll.value = true
  try {
    const res = await clearAllConversations()
    if (res.code === 0) {
      conversations.value = []
      currentCode.value = ''
      messages.value = []
      ElMessage.success(res.message || '已清空全部对话')
    } else {
      ElMessage.error(res.message || '清空失败')
    }
  } catch {
    ElMessage.error('清空全部对话失败')
  } finally {
    clearingAll.value = false
  }
}

async function handleClearConversationMessages() {
  try {
    await ElMessageBox.confirm(
      '确定要清空当前对话的所有消息吗？此操作不可恢复。',
      '清空消息',
      {
        confirmButtonText: '确定清空',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }
  clearingMessages.value = true
  try {
    const res = await clearConversationMessages(currentCode.value)
    if (res.code === 0) {
      messages.value = []
      ElMessage.success(res.message || '消息已清空')
    } else {
      ElMessage.error(res.message || '清空失败')
    }
  } catch {
    ElMessage.error('清空消息失败')
  } finally {
    clearingMessages.value = false
  }
}

async function onSend({ message, fileIds, onReply, onError }) {
  sending.value = true
  try {
    const res = await sendMessage(currentCode.value, message, fileIds, modelProvider.value)
    if (res.code === 0 && res.data) {
      if (!currentCode.value && res.data.conversation_code) {
        currentCode.value = res.data.conversation_code
        await loadConversations()
      }
      onReply(res.data.reply)

      // 更新标题
      const conv = conversations.value.find((c) => c.conversation_code === currentCode.value)
      if (conv && res.data.title) {
        conv.title = res.data.title
      }
    } else {
      onError(res.message || '请求失败')
    }
  } catch {
    onError('发送消息失败')
  } finally {
    sending.value = false
  }
}

// 初始化
loadConversations()
// 预加载可用模型列表（网关 / 本地）
fetchModels().then(res => {
  if (res.code === 0 && res.data && res.data.providers && res.data.providers.length > 0) {
    modelProviders.value = res.data.providers
  }
}).catch(() => {}).finally(() => {
  // 兜底：确保始终有默认选项
  // （本地模型必须由后端真实查询到才展示，不能在此处臆造）
  if (modelProviders.value.length === 0) {
    modelProviders.value = [
      { key: 'gateway', label: '智能体网关' },
    ]
  }
})
</script>

<style scoped>
.ai-helper-container {
  display: flex;
  height: calc(100vh - 140px);
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

/* ---- 左侧栏 ---- */
.sidebar {
  width: 280px;
  min-width: 280px;
  border-right: 1px solid #ebeef5;
  display: flex;
  flex-direction: column;
  background: #fafbfc;
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid #ebeef5;
}

.sidebar-header .el-button {
  width: 100%;
}

.conversation-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.conversation-item {
  display: flex;
  align-items: center;
  padding: 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: background 0.15s;
}

.conversation-item:hover {
  background: #ecf5ff;
}

.conversation-item.active {
  background: #d9ecff;
}

.conv-info {
  flex: 1;
  min-width: 0;
}

.conv-title {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-time {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.conv-delete {
  opacity: 0;
  transition: opacity 0.15s;
  color: #909399;
}

.conversation-item:hover .conv-delete {
  opacity: 1;
}

.conv-delete:hover {
  color: #f56c6c;
}

/* ---- 右侧聊天区域 ---- */
.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.welcome {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #909399;
}

.welcome-icon {
  color: #c0c4cc;
  margin-bottom: 16px;
}

.welcome h2 {
  margin: 0 0 8px;
  font-size: 22px;
  font-weight: 600;
  color: #606266;
}

.welcome p {
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

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #ebeef5;
  background: #fff;
  flex-shrink: 0;
}

.chat-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

/* Sidebar footer -- visually separated from the conversation list */
.sidebar-footer {
  padding: 12px 16px;
  border-top: 1px solid #ebeef5;
  flex-shrink: 0;
}

.sidebar-footer .el-button {
  width: 100%;
}
</style>
