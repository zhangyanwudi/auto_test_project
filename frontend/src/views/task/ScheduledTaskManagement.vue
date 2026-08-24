<template>
  <div class="task-scheduled-page">
    <el-card shadow="never">
      <template #header>
        <header class="card-head">
          <span class="card-title">定时任务</span>
        </header>
      </template>
      <p class="page-hint">
        配置基于标准 5 段 Cron；启用后由系统调度进程按表达式触发。
        执行文件须在 stdout 最后一行返回 JSON：
        <code>{"success": true}</code> 或
        <code>{"success": false, "message": "失败原因"}</code>（失败时 message 必填）。
      </p>

      <el-empty
        v-if="showEmptyHint"
        description="暂无定时任务"
        :image-size="72"
      >
        <el-button type="primary" @click="openCreateDialog">新建任务</el-button>
        <p class="empty-sub">列表将展示已创建的任务；请先新建一条任务。</p>
      </el-empty>

      <template v-else>
        <div class="list-toolbar">
          <el-input
            v-model="taskSearchKeyword"
            clearable
            placeholder="搜索任务名称、编码、说明、Cron、执行文件…"
            class="task-search-input"
            :prefix-icon="Search"
          />
          <el-button type="primary" @click="openCreateDialog">新建任务</el-button>
        </div>
        <el-table
          v-loading="loading"
          :data="filteredList"
          border
          stripe
          class="task-table"
          style="width: 100%"
        >
        <template #empty>
          <el-empty description="无匹配任务" :image-size="56" />
        </template>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="task_name" label="任务名称" min-width="130" show-overflow-tooltip />
        <el-table-column prop="task_code" label="任务编码" min-width="120" show-overflow-tooltip />
        <el-table-column prop="cron_expression" label="Cron" min-width="120" show-overflow-tooltip />
        <el-table-column label="执行文件" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="(row.execution_type || 'file') === 'file'">
              {{ row.task_file_name || '—' }}
            </span>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="140" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'info'">
              {{ row.status === 1 ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_run_time" label="最近执行" min-width="170" show-overflow-tooltip />
        <el-table-column label="任务结果" min-width="220">
          <template #default="{ row }">
            <div class="run-result-cell">
              <el-tag v-if="row.last_run_success === true" type="success" size="small">成功</el-tag>
              <el-tag v-else-if="row.last_run_success === false" type="danger" size="small">失败</el-tag>
              <span v-else class="run-result-muted">未执行</span>
              <span
                v-if="row.last_run_message"
                class="run-result-msg"
                :title="row.last_run_message"
              >
                {{ row.last_run_message }}
              </span>
              <el-button
                v-if="row.last_run_success != null"
                link
                type="primary"
                size="small"
                class="run-result-detail-btn"
                @click="openRunResultDialog(row)"
              >
                详情
              </el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="380" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button
              size="small"
              type="success"
              plain
              :loading="runningTaskId === row.id"
              :disabled="runNowRowDisabled(row)"
              @click="runTaskNow(row)"
            >
              立即运行
            </el-button>
            <el-button
              size="small"
              :type="row.status === 1 ? 'warning' : 'success'"
              @click="toggleStatus(row)"
            >
              {{ row.status === 1 ? '停用' : '启用' }}
            </el-button>
            <el-button type="danger" size="small" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      </template>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑定时任务' : '新建定时任务'"
      width="640px"
      destroy-on-close
      @closed="onDialogClosed"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="执行类型" prop="execution_type">
          <el-radio-group v-model="form.execution_type" @change="onExecutionTypeChange">
            <el-radio label="file">文件</el-radio>
            <el-radio label="other">其他</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item
          v-if="form.execution_type === 'file'"
          label="执行文件"
          prop="task_file_name"
        >
          <el-input
            v-model="fileSearchKeyword"
            clearable
            placeholder="搜索文件名"
            class="file-search"
          />
          <div v-loading="taskFilesLoading" class="file-list-wrap">
            <el-empty
              v-if="!taskFilesLoading && displayedTaskFiles.length === 0"
              description="无匹配文件"
              :image-size="48"
            />
            <el-scrollbar v-else max-height="220px">
              <el-radio-group v-model="form.task_file_name" class="file-radio-group">
                <div v-for="name in displayedTaskFiles" :key="name" class="file-row">
                  <el-radio :label="name">{{ name }}</el-radio>
                </div>
              </el-radio-group>
            </el-scrollbar>
            <p v-if="fileListHint" class="file-list-hint">{{ fileListHint }}</p>
          </div>
        </el-form-item>
        <el-form-item label="任务名称" prop="task_name">
          <el-input v-model="form.task_name" placeholder="展示名称" />
        </el-form-item>
        <el-form-item label="任务编码" prop="task_code">
          <el-input
            v-model="form.task_code"
            placeholder="唯一英文标识，如 nightly_sync"
            :disabled="!!editingId"
          />
        </el-form-item>
        <el-form-item label="执行计划" required>
          <el-radio-group v-model="form.schedule_mode" @change="onModeChange" class="mode-row">
            <el-radio label="daily">每天</el-radio>
            <el-radio label="weekly">每周</el-radio>
            <el-radio label="monthly">每月</el-radio>
            <el-radio label="custom">自定义 Cron</el-radio>
          </el-radio-group>
          <div v-if="form.schedule_mode === 'custom'" class="sub-block">
            <el-input
              v-model="form.custom_cron"
              placeholder="5 段，以空格分隔，如：30 9 * * *"
            />
            <p class="form-hint">格式：分 时 日 月 周；* 表示任意。示例 0 2 * * * 表示每天 2:00。</p>
          </div>
          <div v-else class="sub-block time-grid">
            <el-time-picker
              v-model="form.timeValue"
              format="HH:mm"
              value-format="HH:mm"
              placeholder="选择时刻"
            />
            <el-select
              v-if="form.schedule_mode === 'weekly'"
              v-model="form.weekday"
              placeholder="星期"
              style="width: 120px; margin-left: 12px"
            >
              <el-option
                v-for="w in weekOptions"
                :key="w.value"
                :label="w.label"
                :value="w.value"
              />
            </el-select>
            <el-input-number
              v-if="form.schedule_mode === 'monthly'"
              v-model="form.monthDay"
              :min="1"
              :max="31"
              controls-position="right"
              class="mday"
            />
            <span v-if="form.schedule_mode === 'monthly'" class="mday-lbl">号</span>
          </div>
        </el-form-item>
        <el-form-item label="说明" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="选填" />
        </el-form-item>
        <el-form-item v-if="!editingId" label="状态" prop="status">
          <el-radio-group v-model="form.status">
            <el-radio :label="1">启用</el-radio>
            <el-radio :label="0">停用</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="runResultVisible"
      title="任务返回结果"
      width="720px"
      destroy-on-close
      class="run-result-dialog"
    >
      <div class="run-result-head">
        <el-tag :type="runResultView.success ? 'success' : 'danger'" size="large">
          {{ runResultView.success ? 'true · 成功' : 'false · 失败' }}
        </el-tag>
        <span v-if="runResultView.taskName" class="run-result-task-name">{{ runResultView.taskName }}</span>
      </div>
      <p class="run-result-message">
        <span class="run-result-label">返回说明：</span>{{ runResultView.message || '—' }}
      </p>
      <template v-if="runResultView.metaText">
        <p class="run-result-section-title">运行环境</p>
        <pre class="run-result-pre">{{ runResultView.metaText }}</pre>
      </template>
      <template v-if="runResultView.stdout">
        <p class="run-result-section-title">标准输出</p>
        <pre class="run-result-pre">{{ runResultView.stdout }}</pre>
      </template>
      <template v-if="runResultView.stderr">
        <p class="run-result-section-title">标准错误</p>
        <pre class="run-result-pre run-result-pre-err">{{ runResultView.stderr }}</pre>
      </template>
      <template #footer>
        <el-button type="primary" @click="runResultVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import {
  fetchScheduledTaskList,
  fetchTaskFileNames,
  createScheduledTask,
  updateScheduledTask,
  setScheduledTaskStatus,
  deleteScheduledTask,
  runScheduledTaskNow,
} from '../../api/task/scheduledTask.js'

const TASK_FILE_DISPLAY_LIMIT = 100

const weekOptions = [
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
  { value: 0, label: '周日' },
]

const loading = ref(false)
const list = ref([])
/** 列表关键词（前端过滤，不请求接口） */
const taskSearchKeyword = ref('')
const dialogVisible = ref(false)
const saving = ref(false)
const editingId = ref(null)
const formRef = ref(null)
/** 正在「立即运行」的任务 id，用于按钮 loading */
const runningTaskId = ref(null)
const runResultVisible = ref(false)
const runResultView = reactive({
  success: false,
  taskName: '',
  message: '',
  metaText: '',
  stdout: '',
  stderr: '',
})

const showEmptyHint = computed(() => !loading.value && list.value.length === 0)

function rowMatchesTaskSearch(row) {
  const kw = (taskSearchKeyword.value || '').trim().toLowerCase()
  if (!kw) return true
  const parts = [
    row.id,
    row.task_name,
    row.task_code,
    row.description,
    row.cron_expression,
    row.task_file_name,
    row.execution_type,
    row.last_run_time,
    row.last_run_message,
    row.last_run_success,
  ]
    .filter(Boolean)
    .map((x) => String(x).toLowerCase())
  return parts.some((s) => s.includes(kw))
}

const filteredList = computed(() => list.value.filter((row) => rowMatchesTaskSearch(row)))

const form = reactive({
  execution_type: 'file',
  task_file_name: '',
  task_name: '',
  task_code: '',
  description: '',
  schedule_mode: 'daily',
  timeValue: '09:00',
  weekday: 1,
  monthDay: 1,
  custom_cron: '0 0 * * *',
  status: 1,
})

/** 接口返回的 task_file 目录下全量文件名（前端缓存，搜索在本地过滤） */
const taskFilesCache = ref([])
const taskFilesLoading = ref(false)
const fileSearchKeyword = ref('')

const rules = {
  task_name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
  task_code: [{ required: true, message: '请输入任务编码', trigger: 'blur' }],
  task_file_name: [
    {
      validator(_rule, value, callback) {
        if (form.execution_type !== 'file') {
          callback()
          return
        }
        if (!value || !String(value).trim()) {
          callback(new Error('请选择执行文件'))
          return
        }
        callback()
      },
      trigger: 'change',
    },
  ],
}

const filteredTaskFiles = computed(() => {
  const kw = (fileSearchKeyword.value || '').trim().toLowerCase()
  const all = taskFilesCache.value
  if (!kw) return all
  return all.filter((n) => String(n).toLowerCase().includes(kw))
})

const displayedTaskFiles = computed(() => {
  const filtered = filteredTaskFiles.value
  let names = filtered.slice(0, TASK_FILE_DISPLAY_LIMIT)
  const sel = String(form.task_file_name || '')
  if (sel && form.execution_type === 'file' && !names.includes(sel)) {
    names = [sel, ...names].slice(0, TASK_FILE_DISPLAY_LIMIT)
  }
  return names
})

const fileListHint = computed(() => {
  const total = filteredTaskFiles.value.length
  if (total <= TASK_FILE_DISPLAY_LIMIT) return ''
  return `共 ${total} 个匹配，仅展示前 ${TASK_FILE_DISPLAY_LIMIT} 个，请缩小搜索范围`
})

const expectedCron = computed(() => {
  if (form.schedule_mode === 'custom') {
    return (form.custom_cron || '').trim()
  }
  const t = String(form.timeValue || '0:0')
  const [hStr, mStr] = t.split(':')
  const hour = parseInt(hStr, 10) || 0
  const minute = parseInt(mStr, 10) || 0
  if (form.schedule_mode === 'daily') {
    return `${minute} ${hour} * * *`
  }
  if (form.schedule_mode === 'weekly') {
    return `${minute} ${hour} * * ${form.weekday}`
  }
  if (form.schedule_mode === 'monthly') {
    const d = Math.min(31, Math.max(1, Number(form.monthDay) || 1))
    return `${minute} ${hour} ${d} * *`
  }
  return '0 0 * * *'
})

/** 是否为 Cron 段中的纯数字（用于每天/每周/每月可视化，不含步长、范围等复杂语法） */
function isPlainCronInt(part, min, max) {
  const s = String(part ?? '').trim()
  if (!/^\d+$/.test(s)) return false
  const n = parseInt(s, 10)
  return n >= min && n <= max
}

function parseCronToForm(expr) {
  const trimmed = String(expr || '').trim()
  const parts = trimmed.split(/\s+/)
  if (parts.length !== 5) {
    form.schedule_mode = 'custom'
    form.custom_cron = trimmed || '0 0 * * *'
    return
  }
  const [a, b, c, d, e] = parts

  if (c === '*' && d === '*' && e === '*' && isPlainCronInt(a, 0, 59) && isPlainCronInt(b, 0, 23)) {
    const minute = parseInt(a, 10)
    const hour = parseInt(b, 10)
    form.timeValue = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
    form.schedule_mode = 'daily'
    return
  }
  if (
    c === '*' &&
    d === '*' &&
    e !== '*' &&
    isPlainCronInt(a, 0, 59) &&
    isPlainCronInt(b, 0, 23) &&
    isPlainCronInt(e, 0, 6)
  ) {
    const minute = parseInt(a, 10)
    const hour = parseInt(b, 10)
    form.timeValue = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
    form.schedule_mode = 'weekly'
    form.weekday = parseInt(e, 10)
    return
  }
  if (
    c !== '*' &&
    d === '*' &&
    e === '*' &&
    isPlainCronInt(a, 0, 59) &&
    isPlainCronInt(b, 0, 23) &&
    isPlainCronInt(c, 1, 31)
  ) {
    const minute = parseInt(a, 10)
    const hour = parseInt(b, 10)
    const dom = parseInt(c, 10)
    form.timeValue = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
    form.schedule_mode = 'monthly'
    form.monthDay = dom
    return
  }
  form.schedule_mode = 'custom'
  form.custom_cron = trimmed || '0 0 * * *'
}

function resetForm() {
  editingId.value = null
  form.execution_type = 'file'
  form.task_file_name = ''
  form.task_name = ''
  form.task_code = ''
  form.description = ''
  form.schedule_mode = 'daily'
  form.timeValue = '09:00'
  form.weekday = 1
  form.monthDay = 1
  form.custom_cron = '0 0 * * *'
  form.status = 1
  fileSearchKeyword.value = ''
}

function onExecutionTypeChange() {
  if (form.execution_type !== 'file') {
    form.task_file_name = ''
    fileSearchKeyword.value = ''
  } else {
    loadTaskFilesIntoCache()
    formRef.value?.validateField('task_file_name')
  }
}

async function loadTaskFilesIntoCache() {
  taskFilesLoading.value = true
  try {
    const res = await fetchTaskFileNames()
    if (res.code === 0 && Array.isArray(res.data)) {
      taskFilesCache.value = res.data.map((x) => String(x))
    } else {
      taskFilesCache.value = []
    }
  } catch {
    taskFilesCache.value = []
  } finally {
    taskFilesLoading.value = false
  }
}

watch(
  () => dialogVisible.value,
  (visible) => {
    if (visible && form.execution_type === 'file') {
      loadTaskFilesIntoCache()
    }
  },
)

function onModeChange() {
  if (form.schedule_mode === 'custom' && !form.custom_cron) {
    form.custom_cron = '0 0 * * *'
  }
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
  form.execution_type = row.execution_type === 'other' ? 'other' : 'file'
  form.task_file_name = row.task_file_name || ''
  form.task_name = row.task_name
  form.task_code = row.task_code
  form.description = row.description || ''
  parseCronToForm(row.cron_expression)
  dialogVisible.value = true
}

async function loadList() {
  loading.value = true
  try {
    const res = await fetchScheduledTaskList()
    list.value = res.code === 0 && Array.isArray(res.data) ? res.data : []
  } catch {
    list.value = []
  } finally {
    loading.value = false
  }
}

async function submitForm() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  const cron = expectedCron.value
  const cronParts = String(cron).trim().split(/\s+/)
  if (cronParts.length !== 5) {
    ElMessage.error('请填写合法的 5 段 Cron（空格分隔）')
    return
  }
  saving.value = true
  try {
    const payload = {
      task_name: form.task_name.trim(),
      task_code: form.task_code.trim(),
      description: form.description.trim(),
      cron_expression: cron,
      execution_type: form.execution_type,
      task_file_name:
        form.execution_type === 'file' ? String(form.task_file_name || '').trim() : '',
    }
    let res
    if (editingId.value) {
      res = await updateScheduledTask(editingId.value, {
        task_name: payload.task_name,
        description: payload.description,
        cron_expression: payload.cron_expression,
        execution_type: payload.execution_type,
        task_file_name: payload.task_file_name,
      })
    } else {
      res = await createScheduledTask({ ...payload, status: form.status })
    }
    if (res.code === 0) {
      ElMessage.success(res.message || '保存成功')
      dialogVisible.value = false
      await loadList()
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function isRunNowDisabled(row) {
  if ((row.execution_type || 'file') !== 'file') return true
  if (!(row.task_file_name || '').trim()) return true
  return false
}

function runNowRowDisabled(row) {
  if (isRunNowDisabled(row)) return true
  if (runningTaskId.value !== null && runningTaskId.value !== row.id) return true
  return false
}

function fillRunResultView(row, runResult) {
  const rr = runResult || {
    success: row.last_run_success,
    message: row.last_run_message,
    detail: row.last_run_detail,
  }
  const d = rr.detail && typeof rr.detail === 'object' ? rr.detail : row.last_run_detail || {}
  const tr = d.task_result && typeof d.task_result === 'object' ? d.task_result : null
  runResultView.success = tr?.success === true || rr.success === true
  runResultView.taskName = row.task_name || ''
  runResultView.message = tr?.message || rr.message || row.last_run_message || ''
  const meta = [
    d.command != null && `命令：${JSON.stringify(d.command)}`,
    d.cwd && `工作目录：${d.cwd}`,
    d.script_path && `脚本：${d.script_path}`,
    d.expected_path && `期望路径：${d.expected_path}`,
    d.returncode != null && `退出码：${d.returncode}`,
  ].filter(Boolean)
  runResultView.metaText = meta.join('\n')
  runResultView.stdout = String(d.stdout || '').trim()
  runResultView.stderr = String(d.stderr || '').trim()
}

function openRunResultDialog(row, runResult) {
  fillRunResultView(row, runResult)
  runResultVisible.value = true
}

async function runTaskNow(row) {
  if (runningTaskId.value !== null) return
  runningTaskId.value = row.id
  try {
    const res = await runScheduledTaskNow(row.id)
    if (res.code !== 0) {
      ElMessage.error(res.message || '请求失败')
      return
    }
    const data = res.data || {}
    const rr = data.run_result
    await loadList()
    openRunResultDialog(
      {
        task_name: data.task_name || row.task_name,
        last_run_success: rr?.success,
        last_run_message: rr?.message,
        last_run_detail: rr?.detail,
      },
      rr,
    )
    if (rr?.success) {
      ElMessage.success(rr.message || '执行成功')
    } else {
      ElMessage.warning(rr?.message || '执行失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '请求失败')
  } finally {
    runningTaskId.value = null
  }
}

async function toggleStatus(row) {
  const next = row.status === 1 ? 0 : 1
  const tip = next === 0 ? '确定停用该任务？' : '确定启用该任务？'
  try {
    await ElMessageBox.confirm(tip, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    const res = await setScheduledTaskStatus(row.id, next)
    if (res.code === 0) {
      ElMessage.success('已更新')
      await loadList()
    } else {
      ElMessage.error(res.message || '操作失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '操作失败')
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除任务「${row.task_name}」？删除后不可恢复。`,
      '删除',
      { type: 'warning', confirmButtonText: '删除', confirmButtonClass: 'el-button--danger' },
    )
  } catch {
    return
  }
  try {
    const res = await deleteScheduledTask(row.id)
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

onMounted(() => {
  loadList()
})
</script>

<style scoped>
.task-scheduled-page {
  width: 100%;
}

.list-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.task-search-input {
  flex: 1;
  min-width: 200px;
  max-width: 420px;
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

.page-hint code {
  font-size: 12px;
  padding: 1px 4px;
  border-radius: 4px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
}

.task-table {
  margin-top: 0;
}

.empty-sub {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.form-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.mode-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
}

.sub-block {
  margin-top: 12px;
  width: 100%;
}

.time-grid {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
}

.mday {
  width: 120px;
  margin-left: 12px;
}

.mday-lbl {
  margin-left: 6px;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.file-search {
  width: 100%;
  margin-bottom: 8px;
}

.file-list-wrap {
  width: 100%;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  padding: 8px 10px;
  background: var(--el-fill-color-blank);
}

.file-radio-group {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0;
}

.file-row {
  width: 100%;
  padding: 2px 0;
}

.file-list-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.run-result-cell {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  line-height: 1.4;
}

.run-result-msg {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--el-text-color-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-result-muted {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.run-result-detail-btn {
  padding: 0 4px;
}

.run-result-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.run-result-task-name {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.run-result-message {
  margin: 0 0 16px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  word-break: break-word;
}

.run-result-label {
  color: var(--el-text-color-secondary);
  margin-right: 4px;
}

.run-result-section-title {
  margin: 0 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}

.run-result-pre {
  margin: 0 0 14px;
  padding: 10px 12px;
  max-height: 240px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
}

.run-result-pre-err {
  color: var(--el-color-danger);
}
</style>
