<template>
  <el-dialog
    v-model="dialogVisible"
    title="AI 助手"
    :width="840"
    :close-on-click-modal="false"
    :modal="false"
    draggable
    destroy-on-close
    class="ai-chat-dialog"
    @open="onDialogOpen"
  >
    <ChatBody
      :conversation-code="conversationCode"
      v-model:messages="messages"
      :sending="sending"
      :model-provider="modelProvider"
      :model-providers="modelProviders"
      @update:model-provider="modelProvider = $event"
      @send="onSend"
    />
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import {
  createConversation,
  sendMessage,
  fetchModels,
  fetchConversationMessages,
} from '../api/ai_helper/index.js'
import ChatBody from './ChatBody.vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:visible'])

const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val),
})

const conversationCode = ref('')
const messages = ref([])
const sending = ref(false)
const modelProvider = ref('gateway')
const modelProviders = ref([])

async function onDialogOpen() {
  if (!conversationCode.value) {
    try {
      const res = await createConversation()
      if (res.code === 0 && res.data) {
        conversationCode.value = res.data.conversation_code
      }
    } catch {
      // 创建失败不阻塞
    }
  }
  // 获取可用模型列表
  if (modelProviders.value.length === 0) {
    try {
      const res = await fetchModels()
      if (res.code === 0 && res.data) {
        modelProviders.value = res.data.providers || []
      }
    } catch {
      // 获取失败不阻塞
    }
    // 兜底：如果获取失败或返回为空，仅提供网关默认选项
    // （本地模型必须由后端真实查询到才展示，不能在此处臆造）
    if (modelProviders.value.length === 0) {
      modelProviders.value = [
        { key: 'gateway', label: '智能体网关' },
      ]
    }
  }
}

async function onSend({ message, fileIds, onReply, onError }) {
  sending.value = true

  // 巡检命令（@巡检基建平台 / @case-explore）：发送期间轮询对话消息，实时展示每步进度，
  // 避免探索耗时较长时页面长时间无反馈，也不知道卡在哪一步。
  const isExplore = /^@(巡检基建平台|case-explore)/.test((message || '').trim())
  let pollTimer = null
  let shownCount = 0

  // 首次发送时若无 conversation_code，先创建一个（确保轮询有目标）
  if (isExplore && !conversationCode.value) {
    try {
      const c = await createConversation()
      if (c.code === 0 && c.data) {
        conversationCode.value = c.data.conversation_code
      }
    } catch {
      // 创建失败不阻塞，轮询会跳过
    }
  }

  // 巡检期间轮询：把新出现的 assistant 进度消息实时追加到 messages
  const startPolling = (convCode) => {
    if (!convCode) return
    const poll = async () => {
      try {
        const r = await fetchConversationMessages(convCode)
        if (r.code === 0 && Array.isArray(r.data)) {
          const assistantMsgs = r.data.filter(m => m.role === 'assistant')
          if (assistantMsgs.length > shownCount) {
            const fresh = assistantMsgs.slice(shownCount)
            fresh.forEach(m => {
              // 标记为进度消息，最终报告到达时清掉，避免与完整报告重复
              messages.value.push({ role: 'assistant', content: m.content, _isProgress: true })
            })
            shownCount = assistantMsgs.length
          }
        }
      } catch {
        // 轮询失败忽略，等下次
      }
    }
    poll()
    pollTimer = setInterval(poll, 800)
  }

  if (isExplore && conversationCode.value) {
    startPolling(conversationCode.value)
  }

  try {
    const res = await sendMessage(conversationCode.value, message, fileIds, modelProvider.value)
    if (res.code === 0 && res.data) {
      if (!conversationCode.value && res.data.conversation_code) {
        conversationCode.value = res.data.conversation_code
      }
      if (isExplore) {
        // 探索结束：清掉轮询期间的进度消息，只保留最终完整报告
        messages.value = messages.value.filter(m => !m._isProgress)
      }
      onReply(res.data.reply)
    } else {
      onError(res.message || '请求失败')
    }
  } catch {
    onError('发送消息失败')
  } finally {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    sending.value = false
  }
}
</script>

<!--
  非 scoped：el-dialog 通过 Teleport 渲染到 body，scoped 样式选不中它，
  必须用全局选择器。此处只放 dialog 框架级样式，不影响其他页面的 el-dialog。
-->
<style>
.ai-chat-dialog {
  max-height: 85vh;
}

.ai-chat-dialog .el-dialog__header {
  cursor: move;
  user-select: none;
}

.ai-chat-dialog .el-dialog__body {
  padding: 0 !important;
  display: flex;
  flex-direction: column;
  height: 600px;
  max-height: calc(85vh - 54px);
  position: relative;
  overflow: hidden;
}
</style>
