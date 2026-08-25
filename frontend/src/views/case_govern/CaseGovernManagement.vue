<template>
  <div class="case-govern-page">
    <el-card shadow="never">
      <template #header>
        <header class="card-head">
          <span class="card-title">用例管理</span>
        </header>
      </template>
      <p class="page-hint">
        管理测试用例记录；点击「设计用例」通过思维导图创建用例步骤与预期。
      </p>

      <el-empty v-if="showEmptyHint" description="暂无用例" :image-size="72">
        <el-button type="primary" @click="openCreateDialog">新建用例</el-button>
        <el-button :loading="importing" @click="triggerImport">导入用例</el-button>
        <p class="empty-sub">列表将展示已创建的用例；也可导入 .emmx / .xmind 思维导图。</p>
      </el-empty>

      <template v-else>
        <div class="list-toolbar">
          <el-input
            v-model="keyword"
            clearable
            placeholder="搜索用例名称、模块、创建人…"
            class="search-input"
            :prefix-icon="Search"
          />
          <el-button type="primary" @click="openCreateDialog">新建用例</el-button>
          <el-button :loading="importing" @click="triggerImport">导入</el-button>
        </div>
        <el-table
          v-loading="loading"
          :data="filteredList"
          border
          stripe
          style="width: 100%"
        >
          <template #empty>
            <el-empty description="无匹配用例" :image-size="56" />
          </template>
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="case_name" label="用例名称" min-width="150" show-overflow-tooltip />
          <el-table-column prop="module" label="模块" min-width="120" show-overflow-tooltip />
          <el-table-column label="优先级" width="90">
            <template #default="{ row }">
              <el-tag :type="priorityTagType(row.priority)" size="small">
                {{ row.priority_label || priorityLabel(row.priority) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="node_count" label="节点数" width="80" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.status === 1 ? 'success' : 'info'">
                {{ row.status === 1 ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="creator" label="创建人" min-width="100" show-overflow-tooltip />
          <el-table-column prop="create_time" label="创建时间" min-width="170" show-overflow-tooltip />
          <el-table-column prop="update_time" label="更新时间" min-width="170" show-overflow-tooltip />
          <el-table-column label="操作" width="370" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" size="small" @click="openMindEditor(row)">{{ isOwner(row) ? '设计用例' : '查看用例' }}</el-button>
              <el-button size="small" @click="openEditDialog(row)">编辑</el-button>
              <el-button size="small" type="warning" plain @click="onExport(row)">导出</el-button>
              <el-button size="small" type="success" plain @click="onShare(row)">分享</el-button>
              <el-button type="danger" size="small" @click="onDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-card>

    <input
      ref="importInput"
      type="file"
      accept=".emmx,.xmind"
      style="display: none"
      @change="onImportFileChange"
    />

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑用例' : '新建用例'"
      width="560px"
      destroy-on-close
      @closed="onDialogClosed"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="用例名称" prop="case_name">
          <el-input v-model="form.case_name" placeholder="同一模块下用例名称唯一" />
        </el-form-item>
        <el-form-item label="所属模块" prop="module">
          <el-select
            v-model="form.module"
            filterable
            clearable
            allow-create
            default-first-option
            placeholder="选择或输入模块名"
            style="width: 100%"
          >
            <el-option v-for="m in moduleOptions" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级" prop="priority">
          <el-radio-group v-model="form.priority">
            <el-radio :label="1">高</el-radio>
            <el-radio :label="2">中</el-radio>
            <el-radio :label="3">低</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="!editingId" label="状态" prop="status">
          <el-radio-group v-model="form.status">
            <el-radio :label="1">启用</el-radio>
            <el-radio :label="0">停用</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="用例图片">
          <div class="case-image" tabindex="0" @paste="onCasePaste">
            <img v-if="form.image" :src="form.image" class="case-img" alt="" />
            <p v-else class="case-img-hint">点击此处聚焦后 Ctrl+V 粘贴图片</p>
            <el-button
              v-if="form.image"
              size="small"
              type="danger"
              plain
              @click="form.image = ''"
            >
              删除图片
            </el-button>
          </div>
        </el-form-item>
        <el-form-item label="说明" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="选填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="mindVisible"
      :title="mindCase && mindCase.readonly ? '查看用例' : '用例设计'"
      fullscreen
      destroy-on-close
      class="mind-dialog"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :before-close="handleMindClose"
      @closed="onMindClosed"
    >
      <MindMapEditor
        v-if="mindVisible && mindCase"
        :case-id="mindCase.id"
        :case-name="mindCase.case_name"
        :readonly="mindCase.readonly"
        @saved="onMindSaved"
        @back="handleMindBack"
        @dirty-change="onMindDirty"
      />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import {
  fetchCaseList,
  fetchModuleList,
  createCase,
  updateCase,
  deleteCase,
  importCaseFromFile,
} from '../../api/case_govern/caseGovern.js'
import { getUserCnName, getUsername } from '../../common/request.js'
import MindMapEditor from './MindMapEditor.vue'

const loading = ref(false)
const list = ref([])
const keyword = ref('')
const dialogVisible = ref(false)
const saving = ref(false)
const editingId = ref(null)
const formRef = ref(null)
const mindVisible = ref(false)
const mindCase = ref(null)
const mindDirty = ref(false)
const moduleOptions = ref([])
const importInput = ref(null)
const importing = ref(false)

const PRIORITY_LABELS = { 1: '高', 2: '中', 3: '低' }

const showEmptyHint = computed(() => !loading.value && list.value.length === 0)

/** 是否用例创建人（与后端 creator 取当前用户中文名/登录名一致）；无创建人记录时视为可编辑 */
function isOwner(row) {
  const creator = (row && row.creator || '').trim()
  if (!creator) return true
  return creator === getUserCnName() || creator === getUsername()
}

function priorityLabel(v) {
  return PRIORITY_LABELS[v] || String(v ?? '')
}

function priorityTagType(v) {
  if (v === 1) return 'danger'
  if (v === 2) return 'warning'
  return 'info'
}

function rowMatchesKeyword(row) {
  const kw = (keyword.value || '').trim().toLowerCase()
  if (!kw) return true
  const parts = [
    row.id,
    row.case_name,
    row.module,
    row.creator,
    row.description,
    row.priority_label || priorityLabel(row.priority),
    row.node_count,
  ]
    .filter((x) => x != null)
    .map((x) => String(x).toLowerCase())
  return parts.some((s) => s.includes(kw))
}

const filteredList = computed(() => list.value.filter((row) => rowMatchesKeyword(row)))

const form = reactive({
  case_name: '',
  module: '',
  priority: 2,
  status: 1,
  description: '',
  image: '',
})

const rules = {
  case_name: [{ required: true, message: '请输入用例名称', trigger: 'blur' }],
}

function resetForm() {
  editingId.value = null
  form.case_name = ''
  form.module = ''
  form.priority = 2
  form.status = 1
  form.description = ''
  form.image = ''
}

function onDialogClosed() {
  formRef.value?.resetFields()
  resetForm()
}

function openCreateDialog() {
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function openEditDialog(row) {
  resetForm()
  editingId.value = row.id
  form.case_name = row.case_name
  form.module = row.module || ''
  form.priority = row.priority || 2
  form.description = row.description || ''
  form.image = row.image || ''
  dialogVisible.value = true
}

function openMindEditor(row) {
  mindCase.value = { id: row.id, case_name: row.case_name, readonly: !isOwner(row) }
  mindDirty.value = false
  mindVisible.value = true
}

function onMindDirty(val) {
  mindDirty.value = val
}

function onMindSaved() {
  mindDirty.value = false
  loadList()
}

async function confirmCloseMind() {
  if (!mindDirty.value) return true
  try {
    await ElMessageBox.confirm(
      '思维导图有未保存的修改，关闭后将丢失，确定关闭吗？',
      '提示',
      {
        type: 'warning',
        confirmButtonText: '放弃修改',
        cancelButtonText: '继续编辑',
      },
    )
    return true
  } catch {
    return false
  }
}

async function handleMindBack() {
  if (await confirmCloseMind()) {
    mindVisible.value = false
  }
}

async function handleMindClose(done) {
  if (await confirmCloseMind()) {
    done()
  }
}

function onMindClosed() {
  mindCase.value = null
  mindDirty.value = false
}

async function loadList() {
  loading.value = true
  try {
    const res = await fetchCaseList()
    list.value = res.code === 0 && Array.isArray(res.data) ? res.data : []
  } catch {
    list.value = []
  } finally {
    loading.value = false
  }
}

async function loadModules() {
  try {
    const res = await fetchModuleList()
    if (res.code === 0 && Array.isArray(res.data)) {
      moduleOptions.value = res.data.map((x) => String(x))
    } else {
      moduleOptions.value = []
    }
  } catch {
    moduleOptions.value = []
  }
}

function onCasePaste(e) {
  const items = e.clipboardData?.items
  if (!items) return
  for (const item of items) {
    if (item.type && item.type.startsWith('image/')) {
      const file = item.getAsFile()
      if (!file) continue
      const reader = new FileReader()
      reader.onload = () => {
        form.image = reader.result
      }
      reader.readAsDataURL(file)
      e.preventDefault()
      break
    }
  }
}

async function submitForm() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const payload = {
      case_name: form.case_name.trim(),
      module: form.module.trim(),
      priority: form.priority,
      description: form.description.trim(),
      image: form.image || '',
    }
    let res
    if (editingId.value) {
      res = await updateCase(editingId.value, payload)
    } else {
      res = await createCase({ ...payload, status: form.status })
    }
    if (res.code === 0) {
      ElMessage.success(res.message || '保存成功')
      dialogVisible.value = false
      await loadList()
      await loadModules()
      if (!editingId.value) {
        // 新建成功后直接进入思维导图设计
        const created = res.data || {}
        mindCase.value = { id: created.id, case_name: created.case_name || payload.case_name }
        mindDirty.value = false
        mindVisible.value = true
      }
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text)
  }
  return new Promise((resolve, reject) => {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.top = '0'
    ta.style.left = '0'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.focus()
    ta.select()
    try {
      document.execCommand('copy') ? resolve() : reject(new Error('copy failed'))
    } catch (e) {
      reject(e)
    } finally {
      document.body.removeChild(ta)
    }
  })
}

async function onShare(row) {
  const url = `${window.location.origin}/case_share/${row.id}`
  try {
    await copyText(url)
    ElMessage.success('分享链接已复制到剪贴板')
  } catch {
    ElMessage.error(`复制失败，请手动复制：${url}`)
  }
}

function onExport(row) {
  const url = `${window.location.origin}/case_export/${row.id}`
  window.open(url, '_blank')
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除用例「${row.case_name}」？删除后思维导图节点一并删除，不可恢复。`,
      '删除',
      { type: 'warning', confirmButtonText: '删除', confirmButtonClass: 'el-button--danger' },
    )
  } catch {
    return
  }
  try {
    const res = await deleteCase(row.id)
    if (res.code === 0) {
      ElMessage.success(res.message || '已删除')
      await loadList()
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
  }
}

function triggerImport() {
  importInput.value?.click()
}

async function onImportFileChange(e) {
  const file = e.target.files && e.target.files[0]
  e.target.value = '' // 清空，允许再次选择同一文件
  if (!file) return
  importing.value = true
  try {
    const res = await importCaseFromFile(file)
    if (res.code === 0) {
      ElMessage.success(res.message || '导入成功')
      await loadList()
      await loadModules()
      // 导入成功后直接进入思维导图设计，便于查看导入结果
      const created = res.data || {}
      if (created.id) {
        mindCase.value = { id: created.id, case_name: created.case_name || '' }
        mindDirty.value = false
        mindVisible.value = true
      }
    } else {
      ElMessage.error(res.message || '导入失败')
    }
  } catch (err) {
    ElMessage.error(err.message || '导入失败')
  } finally {
    importing.value = false
  }
}

onMounted(() => {
  loadList()
  loadModules()
})

// 供 Home 的路由离开守卫调用：判断当前是否有未保存的思维导图修改
defineExpose({
  hasUnsavedChanges: () => mindDirty.value,
})
</script>

<style scoped>
.case-govern-page {
  width: 100%;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-weight: 600;
  font-size: 15px;
}

.page-hint {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin: 0 0 12px;
  line-height: 1.5;
}

.list-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.search-input {
  flex: 1;
  min-width: 200px;
  max-width: 420px;
}

.empty-sub {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.case-image {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
  min-height: 40px;
  padding: 8px;
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
  cursor: text;
  outline: none;
}

.case-image:focus {
  border-color: var(--el-color-primary);
}

.case-img {
  max-width: 100%;
  max-height: 160px;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
}

.case-img-hint {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

:deep(.mind-dialog) {
  display: flex;
  flex-direction: column;
}

:deep(.mind-dialog .el-dialog__body) {
  flex: 1;
  padding: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
</style>
