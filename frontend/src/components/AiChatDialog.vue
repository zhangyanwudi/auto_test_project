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
  try {
    const res = await sendMessage(conversationCode.value, message, fileIds, modelProvider.value)
    if (res.code === 0 && res.data) {
      if (!conversationCode.value && res.data.conversation_code) {
        conversationCode.value = res.data.conversation_code
      }
      onReply(res.data.reply)
    } else {
      onError(res.message || '请求失败')
    }
  } catch {
    onError('发送消息失败')
  } finally {
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
