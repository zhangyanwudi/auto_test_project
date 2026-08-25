<template>
  <div class="tnode">
    <div
      ref="cardRef"
      class="tcard"
      :data-node-id="node.id"
      :class="[`tcard--${node.node_type || 'case'}`, { 'is-selected': selected, 'is-drop-target': isDropTarget, 'is-dragging': isDragSource }]"
      :draggable="draggable"
      @click.stop="onSelect"
      @dblclick.stop="onEdit"
      @dragstart="onDragStart"
      @dragover="onDragOver"
      @drop="onDrop"
      @dragend="onDragEnd"
    >
      <span
        v-if="hasChildren"
        class="tcard-toggle"
        :title="node.collapsed ? `展开 ${childCount} 个子节点` : '收起子节点'"
        @click.stop="onToggleCollapse"
      >
        <template v-if="node.collapsed">+{{ childCount }}</template>
        <template v-else>−</template>
      </span>
      <span class="tcard-tag">{{ typeLabel }}</span>
      <span v-if="isSmokeCase" class="tcard-smoke" title="冒烟用例，优先执行">冒烟</span>
      <input
        v-if="isEditing"
        ref="titleInput"
        class="tcard-title-input"
        :value="node.title"
        placeholder="未命名"
        @click.stop
        @input="onTitleInput"
        @keydown.tab.prevent="onTab"
        @keydown.enter.prevent="onEnter"
        @keydown.esc="onEsc"
        @blur="onBlur"
      />
      <span v-else-if="node.title || !node.image" class="tcard-title">{{ wrappedTitle }}</span>
      <span
        v-if="node.node_type === 'case' && execResult !== 'none'"
        class="tcard-exec"
        :class="[`tcard-exec--${execResult}`, { 'is-readonly': readonly }]"
        :title="execTitle"
        @click.stop="onToggleExec"
      >
        <el-icon><component :is="execIcon" /></el-icon>
        <span>{{ execLabel }}</span>
      </span>
      <el-image
        v-if="node.image"
        :src="node.image"
        :preview-src-list="[node.image]"
        preview-teleported
        fit="cover"
        class="tcard-img"
        @click.stop
        @dblclick.stop
      />
      <span v-if="!readonly" class="tcard-actions">
        <el-icon v-if="!isRoot" class="tact tact--danger" title="删除节点" @click.stop="onRemove"><Delete /></el-icon>
      </span>
    </div>

    <div v-if="hasChildren && !node.collapsed" class="tkids">
      <MindNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :selected-id="selectedId"
        :editing-id="editingId"
        :is-root="false"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, onUpdated, onUnmounted, ref, watch, nextTick } from 'vue'
import { Delete, CircleCheck, CircleCheckFilled, CircleCloseFilled } from '@element-plus/icons-vue'

const props = defineProps({
  node: { type: Object, required: true },
  selectedId: { type: [String, Number], default: null },
  editingId: { type: [String, Number], default: null },
  isRoot: { type: Boolean, default: false },
})

const ops = inject('mindOps')
const readonly = inject('mindReadonly', false)
const drag = inject('mindDrag', null)
const cardRef = ref(null)
const titleInput = ref(null)

const TYPE_META = {
  module: { label: '模块', color: '#409eff' },
  case: { label: '用例', color: '#67c23a' },
  step: { label: '步骤', color: '#909399' },
  expect: { label: '预期', color: '#e6a23c' },
  precondition: { label: '前置条件', color: '#b882ff' },
}

const typeLabel = computed(() => (TYPE_META[props.node.node_type] || TYPE_META.case).label)
const isSmokeCase = computed(() => props.node.node_type === 'case' && !!props.node.is_smoke)
const execResult = computed(() => {
  const v = props.node.exec_result
  return v === 'pass' ? 'pass' : v === 'fail' ? 'fail' : 'none'
})
const execIcon = computed(() => {
  if (execResult.value === 'pass') return CircleCheckFilled
  if (execResult.value === 'fail') return CircleCloseFilled
  return CircleCheck
})
const execLabel = computed(() => {
  if (execResult.value === 'pass') return '通过'
  if (execResult.value === 'fail') return '不通过'
  return '未执行'
})
const execTitle = computed(() => {
  if (readonly) {
    if (execResult.value === 'pass') return '已通过'
    if (execResult.value === 'fail') return '不通过'
    return '未执行'
  }
  if (execResult.value === 'pass') return '已通过，点击标记为不通过'
  if (execResult.value === 'fail') return '不通过，点击重置为未执行'
  return '未执行，点击标记为通过'
})
const hasChildren = computed(() => Array.isArray(props.node.children) && props.node.children.length > 0)
const childCount = computed(() => (Array.isArray(props.node.children) ? props.node.children.length : 0))
// 节点标题每行最多显示的字符数，达到该字数才换行
const TITLE_LINE_CHARS = 80
const wrappedTitle = computed(() => {
  const title = props.node.title || ''
  if (!title) return '未命名'
  const chars = Array.from(title)
  const lines = []
  for (let i = 0; i < chars.length; i += TITLE_LINE_CHARS) {
    lines.push(chars.slice(i, i + TITLE_LINE_CHARS).join(''))
  }
  return lines.join('\n')
})
const selected = computed(() => props.selectedId != null && props.node.id === props.selectedId)
const isEditing = computed(() => props.editingId != null && props.node.id === props.editingId)
const isDropTarget = computed(() => !!drag && drag.dropTargetId.value === props.node.id)
const isDragSource = computed(() => !!drag && drag.dragSourceId.value === props.node.id)
const draggable = computed(() => !readonly && !props.isRoot)

watch(isEditing, (val) => {
  if (val) nextTick(() => titleInput.value?.focus())
})

onMounted(() => {
  ops?.registerNode(props.node.id, cardRef.value)
  ops?.notify()
  if (isEditing.value) nextTick(() => titleInput.value?.focus())
})
onUpdated(() => {
  ops?.registerNode(props.node.id, cardRef.value)
  ops?.notify()
})
onUnmounted(() => {
  ops?.unregisterNode(props.node.id)
  ops?.notify()
})

function onSelect() {
  ops?.select(props.node.id)
}
function onEdit() {
  if (readonly) return
  ops?.edit(props.node.id)
}
function onRemove() {
  ops?.removeNode(props.node.id)
}
function onDragStart(e) {
  if (readonly || props.isRoot) return
  ops?.setDragSource(props.node.id)
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(props.node.id))
  }
}
function onDragOver(e) {
  if (readonly) return
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
  ops?.setDropTarget(props.node.id)
}
function onDrop(e) {
  if (readonly) return
  e.preventDefault()
  const sourceId = drag ? drag.dragSourceId.value : null
  ops?.moveNode(sourceId, props.node.id)
  ops?.clearDropTarget()
  ops?.clearDragSource()
}
function onDragEnd() {
  ops?.clearDropTarget()
  ops?.clearDragSource()
}
function onToggleCollapse() {
  ops?.toggleCollapse(props.node.id)
}
function onToggleExec() {
  if (readonly) return
  ops?.toggleExecResult(props.node.id)
}
function onTitleInput(e) {
  ops?.setTitle(props.node.id, e.target.value)
}
function onTab() {
  ops?.addChild(props.node.id)
}
function onEnter() {
  if (props.isRoot) {
    ops?.addChild(props.node.id)
  } else {
    ops?.addSibling(props.node.id)
  }
}
function onEsc() {
  ops?.cancelEdit(props.node.id)
}
function onBlur() {
  ops?.finishEdit(props.node.id)
}
</script>

<style scoped>
.tnode {
  display: flex;
  align-items: center;
  position: relative;
  padding: 4px 0;
  width: max-content;
}

.tcard {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  background: #fff;
  border: 1.5px solid #dcdfe6;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  cursor: pointer;
  position: relative;
  white-space: nowrap;
  flex-shrink: 0;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.tcard:hover {
  border-color: #409eff;
}

.tcard.is-selected {
  border-color: #409eff;
  box-shadow: 0 0 0 3px rgba(64, 158, 255, 0.15);
}

.tcard.is-drop-target {
  border-color: #67c23a;
  box-shadow: 0 0 0 3px rgba(103, 194, 58, 0.2);
}

.tcard.is-dragging {
  opacity: 0.45;
}

.tcard-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: #f0f2f5;
  color: #606266;
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
  flex-shrink: 0;
  user-select: none;
}

.tcard-toggle:hover {
  background: #409eff;
  color: #fff;
}

.tcard-tag {
  font-size: 11px;
  color: #fff;
  padding: 1px 6px;
  border-radius: 4px;
  background: #909399;
  line-height: 1.5;
  flex-shrink: 0;
}

.tcard--module .tcard-tag { background: #409eff; }
.tcard--case .tcard-tag { background: #67c23a; }
.tcard--step .tcard-tag { background: #909399; }
.tcard--expect .tcard-tag { background: #e6a23c; }
.tcard--precondition .tcard-tag { background: #b882ff; }

.tcard-smoke {
  font-size: 11px;
  color: #fff;
  padding: 1px 6px;
  border-radius: 4px;
  background: #f56c6c;
  line-height: 1.5;
  flex-shrink: 0;
}

.tcard-exec {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  line-height: 1.5;
  padding: 1px 7px;
  border-radius: 10px;
  cursor: pointer;
  color: #fff;
  background: #c0c4cc;
  flex-shrink: 0;
  user-select: none;
}

.tcard-exec .el-icon {
  font-size: 12px;
}

.tcard-exec--pass { background: #67c23a; }
.tcard-exec--fail { background: #f56c6c; }

.tcard-exec.is-readonly {
  cursor: default;
}

.tcard-title {
  font-size: 13px;
  color: #303133;
  white-space: pre-wrap;
  line-height: 1.5;
  flex-shrink: 0;
}

.tcard-title-input {
  font-size: 13px;
  color: #303133;
  width: 160px;
  padding: 2px 6px;
  border: 1px solid #409eff;
  border-radius: 4px;
  outline: none;
  background: #fff;
  line-height: 1.4;
}

.tcard-img {
  width: 240px;
  height: 160px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
  flex-shrink: 0;
  cursor: zoom-in;
  overflow: hidden;
}

.tcard-img :deep(.el-image__inner) {
  width: 100%;
  height: 100%;
  object-fit: cover;
  -webkit-user-drag: none;
}

.tcard-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-left: 4px;
  opacity: 0;
  transition: opacity 0.15s;
}

.tcard:hover .tcard-actions,
.tcard.is-selected .tcard-actions {
  opacity: 1;
}

.tact {
  font-size: 15px;
  color: #909399;
  cursor: pointer;
  padding: 2px;
}

.tact:hover {
  color: #409eff;
}

.tact--danger:hover {
  color: #f56c6c;
}

/* 子节点列：仅留出曲线空间，连线由 MindMapEditor 的 SVG 绘制 */
.tkids {
  display: flex;
  flex-direction: column;
  padding-left: 44px;
}
</style>
