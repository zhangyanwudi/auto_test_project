/**
 * AI助手相关 API
 */
import { requestWithToken } from '../../common/request.js'

const BASE = '/api/ai_helper'

/** 获取对话列表（按更新时间倒序） */
export async function fetchConversations() {
  const res = await requestWithToken(`${BASE}/conversations/`)
  return res.json()
}

/** 创建新对话，返回 { conversation_code, title, ... } */
export async function createConversation() {
  const res = await requestWithToken(`${BASE}/conversations/create/`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
  return res.json()
}

/** 删除指定对话 */
export async function deleteConversation(conversationCode) {
  const res = await requestWithToken(`${BASE}/conversations/${conversationCode}/delete/`, {
    method: 'POST',
  })
  return res.json()
}

/** 获取指定对话的消息历史 */
export async function fetchConversationMessages(conversationCode) {
  const res = await requestWithToken(`${BASE}/conversations/${conversationCode}/messages/`)
  return res.json()
}

/**
 * 发送消息并获取 AI 回复
 * @param {string} conversationCode - 对话编码，空串表示新建对话
 * @param {string} message - 用户消息内容
 * @param {string[]} fileIds - 可选，引用的已上传文件 ID 列表
 * @param {string} modelProvider - 可选，模型后端："gateway"（默认）或 "local"
 * @returns {Promise<{code: number, message?: string, data?: {conversation_code, reply, title}}>}
 */
export async function sendMessage(conversationCode, message, fileIds, modelProvider) {
  const body = { message }
  if (conversationCode) {
    body.conversation_code = conversationCode
  }
  if (fileIds && fileIds.length > 0) {
    body.file_ids = fileIds
  }
  if (modelProvider) {
    body.model_provider = modelProvider
  }
  const res = await requestWithToken(`${BASE}/chat/`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  return res.json()
}

/** 清空所有对话记录（批量软删除） */
export async function clearAllConversations() {
  const res = await requestWithToken(`${BASE}/conversations/clear-all/`, {
    method: 'POST',
  })
  return res.json()
}

/** 清空指定对话的消息记录 */
export async function clearConversationMessages(conversationCode) {
  const res = await requestWithToken(`${BASE}/conversations/${conversationCode}/clear-messages/`, {
    method: 'POST',
  })
  return res.json()
}

/**
 * 上传 JSON 配置文件
 * @param {File} file - 要上传的文件对象
 * @returns {Promise<{code: number, data?: {file_id, filename, size, content_preview}}>}
 */
export async function uploadFile(file) {
  const formData = new FormData()
  formData.append('file', file)

  const res = await requestWithToken(`${BASE}/files/upload/`, {
    method: 'POST',
    body: formData,
  })
  return res.json()
}

/** 获取可用模型后端列表（网关 / 本地 Ollama） */
export async function fetchModels() {
  const res = await requestWithToken(`${BASE}/models/`)
  return res.json()
}
