<template>
  <div class="mind-editor">
    <div class="mind-toolbar">
      <el-button size="small" @click="onBack">返回列表</el-button>
      <span class="mind-title">{{ caseName || '用例设计' }}</span>
      <div class="mind-toolbar-right">
        <span class="mind-legend">
          <span v-for="t in NODE_TYPES" :key="t.value" class="legend-item">
            <i class="legend-dot" :style="{ background: t.color }"></i>{{ t.label }}
          </span>
        </span>
        <el-button size="small" @click="expandAll">展开全部</el-button>
        <el-button size="small" @click="collapseAll">收起全部</el-button>
        <el-button
          size="small"
          :disabled="!canUndoDelete"
          title="撤销最近一次删除（Ctrl+Z / ⌘Z）"
          @click="undoDelete"
        >撤销删除</el-button>
        <el-button size="small" type="primary" :loading="saving" @click="onSave()">保存</el-button>
      </div>
    </div>

    <div class="mind-body">
      <div v-loading="loading" class="mind-canvas" @scroll.passive="notify" @click.self="clearSelection">
        <div class="mind-content" ref="contentRef">
          <svg class="mind-links" aria-hidden="true">
            <path
              v-for="(link, i) in links"
              :key="i"
              :d="link.d"
              fill="none"
              stroke="#d5d9e2"
              stroke-width="1.5"
            />
          </svg>
          <div class="mind-tree">
            <el-empty
              v-if="!loading && !tree.title && tree.children.length === 0"
              description="点击根节点，在右侧编辑节点内容后即可开始"
              :image-size="80"
            />
            <MindNode :node="tree" :selected-id="selectedId" :editing-id="editingId" :is-root="true" />
          </div>
        </div>
      </div>

      <div class="mind-panel">
        <template v-if="selectedNode">
          <div class="panel-head">节点编辑</div>
          <div class="panel-body">
            <p class="panel-label">节点内容</p>
            <el-input
              v-model="selectedNode.title"
              type="textarea"
              :rows="2"
              placeholder="输入节点文本"
              @input="onNodeEdit"
            />
            <p class="panel-label">节点类型</p>
            <el-select v-model="selectedNode.node_type" style="width: 100%" @change="onNodeEdit">
              <el-option
                v-for="t in NODE_TYPES"
                :key="t.value"
                :label="t.label"
                :value="t.value"
              />
            </el-select>
            <template v-if="selectedNode.node_type === 'case'">
              <p class="panel-label">冒烟测试</p>
              <div class="panel-smoke">
                <el-switch v-model="selectedNode.is_smoke" @change="onNodeEdit" />
                <span class="panel-smoke-hint">标记为冒烟用例，优先执行</span>
              </div>
              <p class="panel-label">执行结果</p>
              <el-radio-group v-model="selectedNode.exec_result" @change="onNodeEdit">
                <el-radio :label="''">未执行</el-radio>
                <el-radio label="pass">通过</el-radio>
                <el-radio label="fail">不通过</el-radio>
              </el-radio-group>
            </template>
            <p class="panel-label">节点图片（选中后 Ctrl+V 粘贴）</p>
            <div class="panel-image">
              <img v-if="selectedNode.image" :src="selectedNode.image" class="panel-img" alt="" />
              <p v-else class="panel-img-hint">粘贴后在此显示预览</p>
              <el-button
                v-if="selectedNode.image"
                size="small"
                type="danger"
                plain
                @click="removeSelectedImage"
              >
                删除图片
              </el-button>
            </div>
            <div class="panel-actions">
              <el-button size="small" type="primary" plain @click="addChild(selectedNode.id)">
                <el-icon><Plus /></el-icon>新增子节点
              </el-button>
              <el-button
                v-if="selectedNode.id !== tree.id"
                size="small"
                plain
                @click="addSibling(selectedNode.id)"
              >
                <el-icon><Bottom /></el-icon>新增兄弟节点
              </el-button>
              <el-button
                v-if="selectedNode.id !== tree.id"
                size="small"
                type="danger"
                plain
                @click="removeNode(selectedNode.id)"
              >
                <el-icon><Delete /></el-icon>删除节点
              </el-button>
            </div>
          </div>
        </template>
        <div v-else class="panel-empty">
          <el-empty description="点击左侧节点进行编辑" :image-size="70" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, provide, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Bottom, Delete } from '@element-plus/icons-vue'
import { fetchMindTree, saveMindTree } from '../../api/case_govern/caseGovern.js'
import MindNode from './MindNode.vue'

const NODE_TYPES = [
  { value: 'module', label: '模块', color: '#409eff' },
  { value: 'case', label: '用例', color: '#67c23a' },
  { value: 'step', label: '步骤', color: '#909399' },
  { value: 'expect', label: '预期', color: '#e6a23c' },
  { value: 'precondition', label: '前置条件', color: '#b882ff' },
]

const props = defineProps({
  caseId: { type: [Number, String], required: true },
  caseName: { type: String, default: '' },
})
const emit = defineEmits(['saved', 'back', 'dirty-change', 'loaded'])

let uidCounter = 0
function uid() {
  uidCounter += 1
  return `n_${uidCounter}`
}

function newNode(title = '', nodeType = 'case') {
  return { id: uid(), title, node_type: nodeType, is_smoke: false, exec_result: '', image: '', children: [] }
}

const tree = reactive(newNode('', 'module'))
const selectedId = ref(null)
const editingId = ref(null)
const editSnapshot = ref('')
const loading = ref(false)
const saving = ref(false)
const dirty = ref(false)
// 保存前已删除的节点记录（用于「撤销删除」恢复），保存成功后清空
const deletedStack = ref([])
const canUndoDelete = computed(() => deletedStack.value.length > 0)
const links = ref([])
const contentRef = ref(null)
const nodeEls = {}

const selectedNode = computed(() => findNode(tree, selectedId.value))

function findNode(node, id) {
  if (!node || id == null) return null
  if (node.id === id) return node
  for (const ch of node.children || []) {
    const found = findNode(ch, id)
    if (found) return found
  }
  return null
}

function findParent(root, id) {
  if (!root) return null
  for (const ch of root.children || []) {
    if (ch.id === id) return root
    const found = findParent(ch, id)
    if (found) return found
  }
  return null
}

function select(id) {
  selectedId.value = id
  editingId.value = null
}

function edit(id) {
  selectedId.value = id
  editingId.value = id
  const node = findNode(tree, id)
  editSnapshot.value = node ? node.title || '' : ''
}

function cancelEdit(id) {
  if (id != null && editingId.value !== id) return
  const node = findNode(tree, id)
  if (node) {
    node.title = editSnapshot.value
  }
  editingId.value = null
  notify()
}

function finishEdit(id) {
  // 仅当失焦的节点仍是当前编辑节点时才结束编辑，避免 Tab 建子节点等切换场景误触发
  if (id != null && editingId.value !== id) return
  editingId.value = null
  selectedId.value = null
  if (dirty.value) {
    onSave(true)
  }
}

function clearSelection() {
  selectedId.value = null
  editingId.value = null
}

function markDirty() {
  if (!dirty.value) {
    dirty.value = true
    emit('dirty-change', true)
  }
}

function onNodeEdit() {
  markDirty()
  notify()
}

function setTitle(id, value) {
  const node = findNode(tree, id)
  if (!node) return
  node.title = value
  markDirty()
  notify()
}

function addChild(id) {
  const parent = findNode(tree, id)
  if (!parent) return
  parent.children = parent.children || []
  const child = newNode('', 'case')
  parent.children.push(child)
  selectedId.value = child.id
  editingId.value = child.id
  markDirty()
  notify()
}

function addSibling(id) {
  if (id === tree.id) return
  const parent = findParent(tree, id)
  if (!parent) return
  const idx = parent.children.findIndex((c) => c.id === id)
  const sibling = newNode('', 'case')
  parent.children.splice(idx + 1, 0, sibling)
  selectedId.value = sibling.id
  editingId.value = sibling.id
  markDirty()
  notify()
}

async function removeNode(id) {
  if (id === tree.id) return
  const node = findNode(tree, id)
  if (!node) return
  const parent = findParent(tree, id)
  if (!parent) return
  const idx = parent.children.findIndex((c) => c.id === id)
  if (idx === -1) return
  const title = node.title || '未命名'
  const hasChildren = (node.children || []).length > 0
  const hint = hasChildren ? '（含其全部子节点）' : ''
  try {
    await ElMessageBox.confirm(
      `确定删除节点「${title}」${hint}吗？删除后可通过「撤销删除」恢复。`,
      '删除节点',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return // 用户取消
  }
  // 记录删除位置与完整子树，保存前可撤销恢复
  deletedStack.value.push({
    node: JSON.parse(JSON.stringify(node)),
    parentId: parent.id,
    index: idx,
  })
  parent.children = parent.children.filter((c) => c.id !== id)
  selectedId.value = parent.id
  if (editingId.value === id) {
    editingId.value = null
  }
  markDirty()
  notify()
  ElMessage.success(`已删除节点「${title}」，可点击「撤销删除」恢复`)
}

function undoDelete() {
  const record = deletedStack.value.pop()
  if (!record) return
  const parent = findParent(tree, record.parentId)
  if (!parent) return
  const idx = Math.min(record.index, parent.children.length)
  parent.children.splice(idx, 0, record.node)
  selectedId.value = record.node.id
  editingId.value = null
  markDirty()
  notify()
  ElMessage.success('已撤销删除')
}

function toggleCollapse(id) {
  const node = findNode(tree, id)
  if (!node) return
  node.collapsed = !node.collapsed
  notify()
}

function toggleExecResult(id) {
  const node = findNode(tree, id)
  if (!node) return
  // 循环切换：未执行 -> 通过 -> 不通过 -> 未执行
  node.exec_result =
    node.exec_result === 'pass' ? 'fail' : node.exec_result === 'fail' ? '' : 'pass'
  markDirty()
  notify()
}

function removeSelectedImage() {
  if (selectedNode.value) {
    selectedNode.value.image = ''
    markDirty()
    notify()
  }
}

function walkNodes(node, fn) {
  fn(node)
  for (const ch of node.children || []) {
    walkNodes(ch, fn)
  }
}

function setAllCollapsed(collapsed) {
  walkNodes(tree, (n) => {
    if (n.children && n.children.length) {
      n.collapsed = collapsed
    }
  })
  notify()
}

function expandAll() {
  setAllCollapsed(false)
}

function collapseAll() {
  setAllCollapsed(true)
}

/* ---- SVG 贝塞尔连线 ---- */

function registerNode(id, el) {
  if (el) nodeEls[id] = el
}

function unregisterNode(id) {
  delete nodeEls[id]
}

let recomputeTimer = null
function notify() {
  if (recomputeTimer) return
  recomputeTimer = setTimeout(() => {
    recomputeTimer = null
    recomputeLinks()
  }, 30)
}

function collectEdges(node, out) {
  if (node.collapsed) return
  for (const ch of node.children || []) {
    out.push([node.id, ch.id])
    collectEdges(ch, out)
  }
}

function buildCurve(x1, y1, x2, y2) {
  const dx = Math.max(36, (x2 - x1) * 0.5)
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`
}

function recomputeLinks() {
  nextTick(() => {
    const contentEl = contentRef.value
    if (!contentEl) return
    const rect = contentEl.getBoundingClientRect()
    const edges = []
    collectEdges(tree, edges)
    const data = []
    for (const [pid, cid] of edges) {
      const pe = nodeEls[pid]
      const ce = nodeEls[cid]
      if (!pe || !ce) continue
      const pr = pe.getBoundingClientRect()
      const cr = ce.getBoundingClientRect()
      data.push({
        d: buildCurve(
          pr.right - rect.left,
          pr.top + pr.height / 2 - rect.top,
          cr.left - rect.left,
          cr.top + cr.height / 2 - rect.top,
        ),
      })
    }
    links.value = data
  })
}

provide('mindOps', { select, edit, finishEdit, cancelEdit, addChild, addSibling, removeNode, toggleCollapse, toggleExecResult, setTitle, registerNode, unregisterNode, notify })

function serializeNode(node) {
  return {
    title: node.title || '',
    node_type: node.node_type || 'case',
    is_smoke: !!node.is_smoke,
    exec_result: node.exec_result || '',
    image: node.image || '',
    children: (node.children || []).map(serializeNode),
  }
}

async function load() {
  loading.value = true
  try {
    const res = await fetchMindTree(props.caseId)
    if (res.code === 0 && res.data) {
      const d = res.data
      tree.id = d.id != null ? d.id : tree.id
      tree.title = d.title || ''
      tree.node_type = d.node_type || 'module'
      tree.is_smoke = !!d.is_smoke
      tree.exec_result = d.exec_result || ''
      tree.image = d.image || ''
      tree.children = d.children || []
      selectedId.value = tree.id
      notify()
    }
  } catch {
    // 静默失败
  } finally {
    loading.value = false
  }
  emit('loaded')
}

async function onSave(silent = false) {
  saving.value = true
  try {
    const res = await saveMindTree(props.caseId, serializeNode(tree))
    if (res.code === 0) {
      if (silent !== true) {
        ElMessage.success(res.message || '用例已保存')
      }
      dirty.value = false
      deletedStack.value = []
      emit('dirty-change', false)
      emit('saved')
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function onBack() {
  emit('back')
}

function onGlobalKeydown(e) {
  const t = e.target
  const tag = (t && t.tagName) || ''
  if (['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON', 'A'].includes(tag) || (t && t.isContentEditable)) {
    return
  }
  // F2：进入编辑（标准重命名键）
  if (e.key === 'F2') {
    if (selectedId.value != null) {
      e.preventDefault()
      edit(selectedId.value)
    }
    return
  }
  // Ctrl+Z / Cmd+Z：撤销最近一次删除
  if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z')) {
    if (deletedStack.value.length) {
      e.preventDefault()
      undoDelete()
    }
    return
  }
  if (selectedId.value == null) return
  // Delete / Backspace：删除选中节点（根节点除外）
  if (e.key === 'Delete' || e.key === 'Backspace') {
    if (selectedId.value === tree.id) return
    e.preventDefault()
    removeNode(selectedId.value)
  } else if (e.key === 'Enter') {
    // Enter：新建同级节点；根节点则新建子节点
    e.preventDefault()
    if (selectedId.value === tree.id) {
      addChild(selectedId.value)
    } else {
      addSibling(selectedId.value)
    }
  } else if (e.key === 'Tab') {
    // Tab：在当前选中节点下新建子节点并进入编辑
    e.preventDefault()
    addChild(selectedId.value)
  }
}

function onPaste(e) {
  const node = selectedNode.value
  if (!node) return
  const items = e.clipboardData?.items
  if (!items) return
  for (const item of items) {
    if (item.type && item.type.startsWith('image/')) {
      const file = item.getAsFile()
      if (!file) continue
      const reader = new FileReader()
      reader.onload = () => {
        node.image = reader.result
        markDirty()
        notify()
      }
      reader.readAsDataURL(file)
      e.preventDefault()
      break
    }
  }
}

onMounted(() => {
  load()
  window.addEventListener('paste', onPaste)
  window.addEventListener('resize', notify)
  window.addEventListener('keydown', onGlobalKeydown)
})

onUnmounted(() => {
  window.removeEventListener('paste', onPaste)
  window.removeEventListener('resize', notify)
  window.removeEventListener('keydown', onGlobalKeydown)
  if (recomputeTimer) {
    clearTimeout(recomputeTimer)
    recomputeTimer = null
  }
})
</script>

<style scoped>
.mind-editor {
  display: flex;
  flex-direction: column;
  height: 72vh;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  overflow: hidden;
}

.mind-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--el-border-color);
  background: #fafafa;
}

.mind-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.mind-toolbar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}

.mind-legend {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  display: inline-block;
}

.mind-body {
  flex: 1;
  display: flex;
  min-height: 0;
}

.mind-canvas {
  flex: 1;
  overflow: auto;
  padding: 80px;
  background:
    linear-gradient(90deg, rgba(0, 0, 0, 0.02) 1px, transparent 1px),
    linear-gradient(rgba(0, 0, 0, 0.02) 1px, transparent 1px);
  background-size: 20px 20px;
}

.mind-content {
  position: relative;
  display: inline-block;
  min-width: 100%;
}

.mind-links {
  position: absolute;
  left: 0;
  top: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  overflow: visible;
}

.mind-links path {
  fill: none;
  stroke: #d5d9e2;
  stroke-width: 1.5;
}

.mind-tree {
  position: relative;
}

.mind-panel {
  width: 280px;
  flex-shrink: 0;
  border-left: 1px solid var(--el-border-color);
  background: #fff;
  display: flex;
  flex-direction: column;
}

.panel-head {
  padding: 12px 14px;
  font-weight: 600;
  font-size: 13px;
  color: #303133;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.panel-body {
  padding: 14px;
  overflow-y: auto;
}

.panel-label {
  margin: 12px 0 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.panel-label:first-child {
  margin-top: 0;
}

.panel-smoke {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-smoke-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.panel-image {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.panel-img {
  max-width: 100%;
  max-height: 160px;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
}

.panel-img-hint {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.panel-actions {
  margin-top: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.panel-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
