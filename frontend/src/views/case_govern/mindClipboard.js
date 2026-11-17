import { ref } from 'vue'

// 思维导图节点剪贴板：模块级单例，所有 MindMapEditor 实例共享，
// 从而支持在 A 用例复制、在 B 用例粘贴（编辑器实例销毁后数据仍保留）。
// 仅存在于当前浏览器标签页内存中，刷新页面后清空。
export const copiedNode = ref(null)
