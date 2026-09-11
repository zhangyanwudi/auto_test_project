<template>
  <div class="db-table-note-page">
    <el-card shadow="never">
      <div class="layout">
        <!-- 上半：左侧表列表 + 右侧 SQL 编辑 -->
        <div class="top-area">
          <!-- 左侧：连接 + 表列表（表项可内联展开字段） -->
          <div class="left-panel">
            <div class="conn-row">
              <el-select
                v-model="currentConnId"
                placeholder="选择数据库连接"
                style="flex: 1"
                @change="onConnChange"
              >
                <el-option
                  v-for="c in connections"
                  :key="c.id"
                  :label="c.name"
                  :value="c.id"
                />
              </el-select>
              <el-dropdown trigger="click" @command="onConnCommand">
                <el-button size="small" :icon="Setting">管理</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="add">新增连接</el-dropdown-item>
                    <el-dropdown-item v-if="currentConnId" command="edit">编辑当前连接</el-dropdown-item>
                    <el-dropdown-item v-if="currentConnId" command="delete" divided>删除当前连接</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>

            <el-input
              v-model="tableKeyword"
              clearable
              placeholder="搜索表名、注释…"
              class="table-search"
              :prefix-icon="Search"
              @input="onTableSearch"
            />

            <div class="table-list" v-loading="tableLoading">
              <el-empty v-if="!tableLoading && !tables.length" description="暂无表数据" :image-size="60" />
              <div
                v-for="t in tables"
                :key="t.table_name"
                class="table-item"
                :class="{ 'is-active': t.table_name === currentTable }"
              >
                <div class="table-row" @click="selectTable(t)">
                  <el-icon
                    class="expand-arrow"
                    :class="{ 'is-expanded': isFieldsExpanded(t) }"
                    @click.stop="toggleTableFields(t)"
                  >
                    <ArrowRight v-if="!isFieldsExpanded(t)" />
                    <ArrowDown v-else />
                  </el-icon>
                  <div class="table-main">
                    <div class="table-name">
                      {{ t.table_name }}
                      <el-tag v-if="t.has_note" size="small" type="success" effect="plain">已备注</el-tag>
                    </div>
                    <div class="table-comment" :title="t.comment">
                      <el-icon class="comment-icon"><ChatLineRound /></el-icon>
                      <span class="comment-text">{{ t.comment || '暂无注释' }}</span>
                      <el-icon
                        class="note-edit-icon"
                        title="编辑表备注"
                        @click.stop="openNoteDialog(t)"
                      >
                        <EditPen />
                      </el-icon>
                    </div>
                  </div>
                </div>

                <div v-if="isFieldsExpanded(t)" class="table-fields" v-loading="isFieldsLoading(t)">
                  <div class="fields-mini-head">
                    <span class="fields-mini-title">字段备注</span>
                    <el-button size="small" type="primary" text @click="saveFieldNotes(t)">
                      保存
                    </el-button>
                  </div>
                  <div
                    v-for="row in fieldsMap[t.table_name] || []"
                    :key="row.name"
                    class="field-row"
                  >
                    <span class="field-name" :title="row.name">{{ row.name }}</span>
                    <el-input
                      v-model="row.manual"
                      size="small"
                      class="field-input"
                      :placeholder="row.comment || '补充备注'"
                      @input="onFieldInput(t)"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 右侧：表信息 + 执行 SQL -->
          <div class="right-panel">
            <template v-if="!currentTable">
              <el-empty description="请在左侧选择一张表" />
            </template>
            <template v-else>
              <div class="note-head">
                <div class="note-head-left">
                  <span class="note-title">{{ currentTable }}</span>
                  <span class="note-comment" :title="currentTableComment">{{ currentTableComment }}</span>
                </div>
                <div class="note-actions">
                  <el-button size="small" :loading="noteSaving" @click="reloadNote">重置</el-button>
                  <el-button size="small" type="primary" :loading="noteSaving" @click="saveSqlRecords">保存 SQL</el-button>
                  <el-button
                    size="small"
                    type="success"
                    :loading="executing"
                    :disabled="!noteForm.sqlRecords.trim()"
                    @click="runSql"
                  >
                    执行 SQL
                  </el-button>
                  <el-button size="small" :loading="executing" @click="clearResult">清空结果</el-button>
                </div>
              </div>

              <p class="panel-label">相关执行 SQL（多条 SQL 用换行分隔，关键字自动高亮）</p>
              <div class="sql-editor">
                <pre ref="sqlHighlightRef" class="sql-highlight" aria-hidden="true"><code v-html="highlightedSql"></code></pre>
                <textarea
                  ref="sqlTextareaRef"
                  v-model="noteForm.sqlRecords"
                  class="sql-textarea"
                  spellcheck="false"
                  placeholder="记录这张表相关的执行 SQL，如查询、更新语句等"
                  @scroll="onSqlScroll"
                  @paste="onSqlPaste"
                  @input="onSqlInput"
                  @blur="onSqlBlur"
                ></textarea>
              </div>
            </template>
          </div>
        </div>

        <!-- 下半：执行结果，全宽独占 -->
        <div v-if="result" class="result-area">
          <div class="result-head">
            <span class="result-title">执行结果</span>
            <span v-if="result.is_write" class="result-meta">
              影响 {{ result.affected }} 行
            </span>
            <span v-else class="result-meta">
              共 {{ result.row_count }} 行{{ result.truncated ? '（已截断，最多显示 ' + maxRows + ' 行）' : '' }}
            </span>
          </div>
          <el-alert
            v-if="result.is_write"
            :title="'执行成功，影响 ' + result.affected + ' 行'"
            type="success"
            :closable="false"
            show-icon
          />
          <template v-else>
            <el-table
              v-if="result.columns && result.columns.length"
              :data="result.rows"
              size="small"
              border
              max-height="420"
              empty-text="查询无数据"
            >
              <el-table-column
                v-for="(col, idx) in result.columns"
                :key="idx"
                :prop="String(idx)"
                :label="col"
                min-width="120"
                show-overflow-tooltip
              />
            </el-table>
            <el-empty v-else description="无返回结果" :image-size="60" />
          </template>
        </div>
      </div>
    </el-card>

    <!-- 连接配置弹窗 -->
    <el-dialog
      v-model="connDialogVisible"
      :title="connEditingId ? '编辑连接' : '新增连接'"
      width="520px"
      destroy-on-close
      @closed="onConnDialogClosed"
    >
      <el-form ref="connFormRef" :model="connForm" :rules="connRules" label-width="90px">
        <el-form-item label="连接标识" prop="id">
          <el-input v-model="connForm.id" :disabled="!!connEditingId" placeholder="唯一标识，如 kolsys" />
        </el-form-item>
        <el-form-item label="显示名称" prop="name">
          <el-input v-model="connForm.name" placeholder="如 达人系统库" />
        </el-form-item>
        <el-form-item label="地址" prop="host">
          <el-input v-model="connForm.host" placeholder="如 127.0.0.1" />
        </el-form-item>
        <el-form-item label="端口" prop="port">
          <el-input v-model="connForm.port" placeholder="默认 3306" />
        </el-form-item>
        <el-form-item label="用户名" prop="user">
          <el-input v-model="connForm.user" placeholder="数据库用户名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="connForm.password"
            type="password"
            show-password
            :placeholder="connEditingId ? '留空表示保持原密码不变' : '数据库密码'"
          />
        </el-form-item>
        <el-form-item label="数据库" prop="database">
          <el-input v-model="connForm.database" placeholder="库名，如 kolsys" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="connDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="connSaving" @click="submitConn">确定</el-button>
      </template>
    </el-dialog>

    <!-- 表备注编辑弹窗 -->
    <el-dialog
      v-model="noteDialogVisible"
      title="表备注"
      width="560px"
      destroy-on-close
    >
      <div class="note-dialog-table">{{ noteDialogTable }}</div>
      <el-input
        v-model="noteDialogForm.note"
        type="textarea"
        :rows="6"
        placeholder="记录这张表是什么表、用途等说明"
      />
      <template #footer>
        <el-button @click="noteDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="noteSaving" @click="saveNoteDialog">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Setting, Search, ChatLineRound, EditPen, ArrowRight, ArrowDown } from '@element-plus/icons-vue'
import {
  fetchConnectionList,
  saveConnection,
  deleteConnection,
  fetchTableList,
  fetchTableNote,
  fetchTableFields,
  saveTableNote,
  executeSql,
} from '../../api/db_table_note/index.js'

const connections = ref([])
const currentConnId = ref('')
const tables = ref([])
const tableKeyword = ref('')
const tableLoading = ref(false)
const currentTable = ref('')
const currentTableComment = ref('')
const noteSaving = ref(false)

/* ---- 执行 SQL ---- */
const executing = ref(false)
const result = ref(null)   // { columns: [...], rows: [[...]], row_count, truncated }
const maxRows = 500        // 与后端 MAX_QUERY_ROWS 一致，仅用于提示文案

const currentConn = computed(() =>
  connections.value.find((c) => c.id === currentConnId.value)
)

const noteForm = reactive({
  note: '',
  sqlRecords: '',
})

// 已保存快照：切换表/连接前对比，有未保存改动则自动落库
const savedSqlSnapshot = ref('')
const savedFieldNotesSnapshot = ref('')
// 记录哪些表字段有未保存的手动改动
const dirtyFields = ref({})  // { table_name: true }

/* ---- 表备注弹窗 ---- */
const noteDialogVisible = ref(false)
const noteDialogTable = ref('')
const noteDialogForm = reactive({ note: '' })

/* ---- 字段注释（左侧表项内联展开） ---- */
// 每个表独立记录：字段列表、展开态、加载态
const fieldsMap = ref({})        // { table_name: [ {name, comment, manual} ] }
const fieldsExpanded = ref({})   // { table_name: true }
const fieldsLoadingMap = ref({}) // { table_name: true }

/* ---- 连接 ---- */
const connDialogVisible = ref(false)
const connSaving = ref(false)
const connEditingId = ref(null)
const connFormRef = ref(null)

const connForm = reactive({
  id: '',
  name: '',
  host: '',
  port: 3306,
  user: '',
  password: '',
  database: '',
})

const connRules = {
  id: [{ required: true, message: '请输入连接标识', trigger: 'blur' }],
  host: [{ required: true, message: '请输入地址', trigger: 'blur' }],
  user: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  database: [{ required: true, message: '请输入数据库名', trigger: 'blur' }],
}

function resetConnForm() {
  connEditingId.value = null
  connForm.id = ''
  connForm.name = ''
  connForm.host = ''
  connForm.port = 3306
  connForm.user = ''
  connForm.password = ''
  connForm.database = ''
}

function openConnDialog(conn) {
  resetConnForm()
  if (conn) {
    connEditingId.value = conn.id
    connForm.id = conn.id
    connForm.name = conn.name
    connForm.host = conn.host
    connForm.port = conn.port
    connForm.user = conn.user
    connForm.password = ''
    connForm.database = conn.database
  }
  connDialogVisible.value = true
}

function onConnDialogClosed() {
  connFormRef.value?.resetFields()
  resetConnForm()
}

async function loadConnections() {
  try {
    const res = await fetchConnectionList()
    connections.value = res.code === 0 && Array.isArray(res.data) ? res.data : []
  } catch {
    connections.value = []
  }
}

async function submitConn() {
  if (!connFormRef.value) return
  try {
    await connFormRef.value.validate()
  } catch {
    return
  }
  connSaving.value = true
  try {
    const res = await saveConnection({
      id: connForm.id.trim(),
      name: connForm.name.trim(),
      host: connForm.host.trim(),
      port: connForm.port,
      user: connForm.user.trim(),
      password: connForm.password,
      database: connForm.database.trim(),
    })
    if (res.code === 0) {
      ElMessage.success(res.message || '保存成功')
      connDialogVisible.value = false
      await loadConnections()
      if (!connEditingId.value && connForm.id) {
        currentConnId.value = connForm.id
        await loadTables()
      }
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    connSaving.value = false
  }
}

function onConnCommand(command) {
  if (command === 'add') {
    openConnDialog()
  } else if (command === 'edit') {
    openConnDialog(currentConn.value)
  } else if (command === 'delete') {
    onDeleteConn(currentConn.value)
  }
}

async function onDeleteConn(conn) {
  try {
    await ElMessageBox.confirm(`确定删除连接「${conn.name}」？`, '删除', {
      type: 'warning',
      confirmButtonText: '删除',
      confirmButtonClass: 'el-button--danger',
    })
  } catch {
    return
  }
  try {
    const res = await deleteConnection(conn.id)
    if (res.code === 0) {
      ElMessage.success(res.message || '已删除')
      if (currentConnId.value === conn.id) {
        currentConnId.value = ''
        tables.value = []
        currentTable.value = ''
      }
      await loadConnections()
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
  }
}

/* ---- 表列表 ---- */
async function loadTables() {
  if (!currentConnId.value) {
    tables.value = []
    return
  }
  tableLoading.value = true
  try {
    const res = await fetchTableList(currentConnId.value, tableKeyword.value)
    tables.value = res.code === 0 && Array.isArray(res.data) ? res.data : []
  } catch (e) {
    ElMessage.error(e.message || '获取表列表失败')
    tables.value = []
  } finally {
    tableLoading.value = false
  }
}

async function onConnChange() {
  // 切换连接前，先把当前表未保存的 SQL / 字段备注落库
  await autoSaveCurrent()
  currentTable.value = ''
  currentTableComment.value = ''
  noteForm.note = ''
  noteForm.sqlRecords = ''
  fieldsMap.value = {}
  fieldsExpanded.value = {}
  fieldsLoadingMap.value = {}
  dirtyFields.value = {}
  savedSqlSnapshot.value = ''
  savedFieldNotesSnapshot.value = ''
  clearResult()
  loadTables()
}

function onTableSearch() {
  loadTables()
}

async function selectTable(t) {
  if (t.table_name === currentTable.value) return
  // 切换表前，先把上一张表未保存的 SQL / 字段备注落库
  await autoSaveCurrent()
  currentTable.value = t.table_name
  currentTableComment.value = t.comment || ''
  clearResult()
  loadNote(t.table_name)
}

/* ---- 字段注释（左侧内联展开） ---- */
function isFieldsExpanded(t) {
  return !!fieldsExpanded.value[t.table_name]
}

function isFieldsLoading(t) {
  return !!fieldsLoadingMap.value[t.table_name]
}

async function toggleTableFields(t) {
  if (isFieldsExpanded(t)) {
    fieldsExpanded.value[t.table_name] = false
    return
  }
  fieldsExpanded.value[t.table_name] = true
  if (!fieldsMap.value[t.table_name]) {
    await loadFieldsForTable(t.table_name)
  }
}

async function loadFieldsForTable(tableName) {
  if (!currentConnId.value || !tableName) return
  fieldsLoadingMap.value[tableName] = true
  try {
    const res = await fetchTableFields(currentConnId.value, tableName)
    if (res.code === 0 && Array.isArray(res.data)) {
      fieldsMap.value[tableName] = res.data
    } else {
      ElMessage.error(res.message || '加载字段失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '加载字段失败')
  } finally {
    fieldsLoadingMap.value[tableName] = false
  }
}

/** 组装某表的字段手动备注为 {字段名: 备注}，仅保留非空项 */
function buildFieldNotesFor(tableName) {
  const map = {}
  for (const f of fieldsMap.value[tableName] || []) {
    const manual = (f.manual || '').trim()
    if (manual) map[f.name] = manual
  }
  return map
}

/** 字段手动输入时标记该表有未保存改动 */
function onFieldInput(t) {
  dirtyFields.value[t.table_name] = true
}

/**
 * 切换表/连接前，自动保存当前表未保存的内容：
 * - 右侧 SQL 输入框与快照不一致时保存 sql_records
 * - 字段有手动改动时保存 field_notes
 */
async function autoSaveCurrent() {
  if (!currentConnId.value || !currentTable.value) return
  const sqlDirty = noteForm.sqlRecords !== savedSqlSnapshot.value
  const fieldDirty = !!dirtyFields.value[currentTable.value]

  if (!sqlDirty && !fieldDirty) return

  noteSaving.value = true
  try {
    const payload = { connection_id: currentConnId.value, table_name: currentTable.value }
    if (sqlDirty) payload.sql_records = noteForm.sqlRecords
    if (fieldDirty) payload.field_notes = buildFieldNotesFor(currentTable.value)

    const res = await saveTableNote(payload)
    if (res.code === 0) {
      savedSqlSnapshot.value = noteForm.sqlRecords
      savedFieldNotesSnapshot.value = JSON.stringify(buildFieldNotesFor(currentTable.value))
      delete dirtyFields.value[currentTable.value]
    } else {
      ElMessage.error(res.message || '自动保存失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '自动保存失败')
  } finally {
    noteSaving.value = false
  }
}

/** 只保存某表的字段手动备注（不碰 note / sql_records） */
async function saveFieldNotes(t) {
  if (!currentConnId.value) return
  noteSaving.value = true
  try {
    const map = buildFieldNotesFor(t.table_name)
    const res = await saveTableNote({
      connection_id: currentConnId.value,
      table_name: t.table_name,
      field_notes: map,
    })
    if (res.code === 0) {
      ElMessage.success('字段备注已保存')
      delete dirtyFields.value[t.table_name]
      savedFieldNotesSnapshot.value = JSON.stringify(map)
      await loadTables()
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    noteSaving.value = false
  }
}

/* ---- 备注（表备注弹窗 + 执行 SQL） ---- */
async function loadNote(tableName) {
  if (!currentConnId.value || !tableName) return
  try {
    const res = await fetchTableNote(currentConnId.value, tableName)
    if (res.code === 0 && res.data) {
      noteForm.note = res.data.note || ''
      noteForm.sqlRecords = res.data.sql_records || ''
    }
  } catch {
    noteForm.note = ''
    noteForm.sqlRecords = ''
  }
  // 同步快照，作为「未保存改动」的基准
  savedSqlSnapshot.value = noteForm.sqlRecords
}

async function reloadNote() {
  await loadNote(currentTable.value)
}

/** 打开表备注编辑弹窗（携带当前表名与已加载的 note） */
function openNoteDialog(t) {
  noteDialogTable.value = t.table_name
  // 优先用弹窗对应的表 note（t.note 由 table_list 返回），避免依赖右侧选中的表
  noteDialogForm.note = t.note || ''
  noteDialogVisible.value = true
}

async function saveNoteDialog() {
  if (!currentConnId.value || !noteDialogTable.value) return
  noteSaving.value = true
  try {
    const res = await saveTableNote({
      connection_id: currentConnId.value,
      table_name: noteDialogTable.value,
      note: noteDialogForm.note,
    })
    if (res.code === 0) {
      ElMessage.success(res.message || '保存成功')
      noteDialogVisible.value = false
      await loadTables()
      // 若编辑的正是右侧选中的表，同步本地 note
      if (noteDialogTable.value === currentTable.value) {
        noteForm.note = noteDialogForm.note
      }
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    noteSaving.value = false
  }
}

/** SQL 关键字集合（大写） */
const SQL_KEYWORDS = new Set([
  'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'NOT', 'IN', 'IS', 'NULL', 'LIKE',
  'AS', 'ON', 'JOIN', 'LEFT', 'RIGHT', 'INNER', 'OUTER', 'FULL', 'CROSS',
  'GROUP', 'BY', 'ORDER', 'HAVING', 'LIMIT', 'OFFSET', 'DISTINCT', 'UNION',
  'ALL', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'INSERT', 'INTO', 'VALUES',
  'UPDATE', 'SET', 'DELETE', 'CREATE', 'TABLE', 'ALTER', 'DROP', 'TRUNCATE',
  'ADD', 'COLUMN', 'INDEX', 'PRIMARY', 'KEY', 'FOREIGN', 'REFERENCES',
  'ASC', 'DESC', 'BETWEEN', 'EXISTS', 'COUNT', 'SUM', 'AVG', 'MIN', 'MAX',
])

const sqlHighlightRef = ref(null)
const sqlTextareaRef = ref(null)

/** 生成带高亮的 SQL HTML（关键字着色，字符串/数字/注释区分） */
function buildHighlightedSql() {
  const raw = noteForm.sqlRecords || ''
  if (!raw) return ''
  // 归一化弯引号为直引号，避免字符串引号不匹配（如 'xxx’）导致 token 无法闭合、后续关键字不高亮
  const normalized = raw.replace(/[‘’]/g, "'").replace(/[“”]/g, '"')
  const escaped = normalized
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  // 单次匹配 token，按优先级分类：注释 > 字符串 > 数字 > 关键字。
  // 全局匹配不重叠，注释/字符串整体作为一个 token，内部不会再被二次高亮（避免嵌套 span 乱码）。
  const tokenRe = /(--[^\n]*|'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|\b\d+\.?\d*\b|\b[A-Za-z_][A-Za-z0-9_]*\b)/g
  return escaped.replace(tokenRe, (m) => {
    if (m.startsWith('--')) return `<span class="sql-cmt">${m}</span>`
    if (m.startsWith("'") || m.startsWith('"')) return `<span class="sql-str">${m}</span>`
    if (/^\d/.test(m)) return `<span class="sql-num">${m}</span>`
    return SQL_KEYWORDS.has(m.toUpperCase()) ? `<span class="sql-kw">${m}</span>` : m
  })
}

const highlightedSql = computed(() => buildHighlightedSql())

/**
 * SQL 格式化：仅将 SQL 关键字转大写，完全保留原有空白/换行/缩进（不做 trim、折叠、子句重排）。
 * 在粘贴 / 失焦时自动调用，不弹窗确认。
 */
function formatSqlText() {
  const raw = noteForm.sqlRecords || ''
  if (!raw.trim()) return

  // 归一化弯引号，保证字符串引号匹配
  const normalized = raw.replace(/[‘’]/g, "'").replace(/[“”]/g, '"')

  // 按字符扫描，仅处理引号与注释之外的关键字（不触碰引号内字符串，也不改动任何空白字符）
  let inSingle = false
  let inDouble = false
  let inLineComment = false
  let result = ''
  let i = 0
  const n = normalized.length

  while (i < n) {
    const ch = normalized[i]
    const next = normalized[i + 1]

    // 行注释 --
    if (!inSingle && !inDouble && ch === '-' && next === '-') {
      inLineComment = true
      result += ch + next
      i += 2
      continue
    }

    if (inLineComment) {
      if (ch === '\n') {
        inLineComment = false
      }
      result += ch
      i += 1
      continue
    }

    // 字符串起始/结束
    if (!inDouble && ch === "'") {
      inSingle = !inSingle
      result += ch
      i += 1
      continue
    }
    if (!inSingle && ch === '"') {
      inDouble = !inDouble
      result += ch
      i += 1
      continue
    }

    if (inSingle || inDouble) {
      result += ch
      i += 1
      continue
    }

    // 标识符：连续字母/数字/下划线，若命中关键字则转大写
    if (/[A-Za-z_]/.test(ch)) {
      let j = i
      while (j < n && /[A-Za-z0-9_]/.test(normalized[j])) j += 1
      const word = normalized.slice(i, j)
      const up = word.toUpperCase()
      result += SQL_KEYWORDS.has(up) ? up : word
      i = j
      continue
    }

    result += ch
    i += 1
  }

  noteForm.sqlRecords = result
}

/** 手动接管粘贴：自己替换选中区间（避免默认粘贴与 v-model 竞态导致「追加而非替换」），随后格式化 + 高亮 */
function onSqlPaste(e) {
  const ta = sqlTextareaRef.value
  if (!ta) return
  e.preventDefault()
  const text = (e.clipboardData || window.clipboardData).getData('text') || ''

  const start = ta.selectionStart
  const end = ta.selectionEnd
  const old = noteForm.sqlRecords || ''
  const next = old.slice(0, start) + text + old.slice(end)
  noteForm.sqlRecords = next

  nextTick(() => {
    ta.focus()
    const caret = start + text.length
    ta.setSelectionRange(caret, caret)
    formatSqlText()
  })
}

/** 手动输入时仅高亮（v-model 已同步值，不触发格式化） */
function onSqlInput() {
  // 高亮由 computed(highlightedSql) 自动重算
}

/** 失焦时兜底格式化一次（手动输入的内容也规整） */
function onSqlBlur() {
  formatSqlText()
}

function onSqlScroll(e) {
  if (sqlHighlightRef.value) {
    sqlHighlightRef.value.scrollTop = e.target.scrollTop
    sqlHighlightRef.value.scrollLeft = e.target.scrollLeft
  }
}

/** 只保存右侧执行 SQL（不碰 note / field_notes） */
async function saveSqlRecords() {
  if (!currentConnId.value || !currentTable.value) return
  noteSaving.value = true
  try {
    const res = await saveTableNote({
      connection_id: currentConnId.value,
      table_name: currentTable.value,
      sql_records: noteForm.sqlRecords,
    })
    if (res.code === 0) {
      ElMessage.success('SQL 已保存')
      savedSqlSnapshot.value = noteForm.sqlRecords
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    noteSaving.value = false
  }
}

/** 从 textarea 取「选中的 SQL」，无选中则返回整段内容 */
function getSelectedSql() {
  const ta = sqlTextareaRef.value
  if (!ta) return (noteForm.sqlRecords || '').trim()
  const s = ta.selectionStart
  const e = ta.selectionEnd
  if (s === e) return (noteForm.sqlRecords || '').trim()
  return (noteForm.sqlRecords || '').slice(s, e).trim()
}

/** 判断 SQL 是否为写操作（UPDATE/DELETE），并检测有无 WHERE */
function isWriteSql(sql) {
  const stripped = sql
    .replace(/--[^\n]*/g, ' ')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/'(?:[^'\\]|\\.)*'/g, ' ')
    .replace(/"(?:[^"\\]|\\.)*"/g, ' ')
  const first = (stripped.trim().split(/\s+/, 1) || [''])[0].toUpperCase()
  if (first !== 'UPDATE' && first !== 'DELETE') return false
  return !/\bWHERE\b/i.test(stripped)
}

/** 执行 SQL：优先执行选中的 SQL；写操作无 WHERE 时确认后再执行 */
async function runSql() {
  if (!currentConnId.value) return
  const sql = getSelectedSql()
  if (!sql) {
    ElMessage.warning('请输入或选中要执行的 SQL')
    return
  }

  let force = false
  if (isWriteSql(sql)) {
    try {
      await ElMessageBox.confirm(
        '该语句没有 WHERE 条件，将影响全表数据，是否继续执行？',
        '危险操作确认',
        {
          type: 'warning',
          confirmButtonText: '仍要执行',
          cancelButtonText: '取消',
          confirmButtonClass: 'el-button--danger',
        },
      )
      force = true
    } catch {
      return
    }
  }

  executing.value = true
  try {
    const res = await executeSql(currentConnId.value, sql, force)
    if (res.code === 0 && res.data) {
      if (res.data.is_write) {
        // 写操作：无结果集，展示影响行数
        result.value = {
          columns: [],
          rows: [],
          row_count: res.data.affected,
          truncated: false,
          is_write: true,
          affected: res.data.affected,
        }
      } else {
        result.value = res.data
      }
    } else {
      ElMessage.error(res.message || '执行失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '执行失败')
  } finally {
    executing.value = false
  }
}

function clearResult() {
  result.value = null
}

onMounted(async () => {
  await loadConnections()
  if (connections.value.length) {
    currentConnId.value = connections.value[0].id
    await loadTables()
  }
})
</script>

<style scoped>
.db-table-note-page {
  width: 100%;
}

.layout {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 520px;
}

.top-area {
  display: flex;
  gap: 16px;
  align-items: stretch;
}

.left-panel {
  width: 360px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.conn-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.table-search {
  width: 100%;
}

.table-list {
  flex: 1;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 6px;
  overflow-y: auto;
  max-height: 560px;
  box-sizing: border-box;
  background: var(--el-fill-color-blank);
}

.table-item {
  padding: 8px 10px;
  border-radius: 6px;
  border-left: 3px solid transparent;
  transition: background-color 0.15s, border-color 0.15s;
}

.table-item:hover {
  background: var(--el-color-primary-light-9);
  border-left-color: var(--el-color-primary-light-3);
}

.table-item.is-active {
  background: var(--el-color-primary-light-8);
  border-left-color: var(--el-color-primary);
}

.table-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  cursor: pointer;
}

.expand-arrow {
  flex-shrink: 0;
  margin-top: 4px;
  font-size: 14px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  transition: transform 0.15s, color 0.15s;
}

.expand-arrow:hover {
  color: var(--el-color-primary);
}

.table-main {
  flex: 1;
  min-width: 0;
}

.table-name {
  font-family: 'SF Mono', 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-primary);
  display: flex;
  align-items: center;
  gap: 6px;
  word-break: break-all;
  line-height: 1.5;
}

.table-item.is-active .table-name {
  color: var(--el-color-primary-dark-2);
}

.table-comment {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
}

.comment-icon {
  flex-shrink: 0;
  font-size: 13px;
  color: var(--el-text-color-placeholder);
}

.comment-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-style: italic;
  color: var(--el-text-color-regular);
}

.note-edit-icon {
  flex-shrink: 0;
  margin-left: auto;
  font-size: 13px;
  color: var(--el-text-color-placeholder);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s;
}

.table-item:hover .note-edit-icon {
  opacity: 1;
}

.note-edit-icon:hover {
  color: var(--el-color-primary);
}

.table-fields {
  margin-top: 8px;
  padding: 8px;
  border-radius: 6px;
  background: var(--el-fill-color-light);
}

.fields-mini-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.fields-mini-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-regular);
}

.field-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.field-row:last-child {
  margin-bottom: 0;
}

.field-name {
  width: 130px;
  flex-shrink: 0;
  font-family: 'SF Mono', 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 12px;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.field-input {
  flex: 1;
  min-width: 0;
}

.right-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.note-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.note-head-left {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}

.note-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.note-comment {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel-label {
  font-size: 13px;
  color: var(--el-text-color-regular);
  margin: 6px 0 4px;
}

.note-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.sql-editor {
  position: relative;
  flex: 1;
  min-height: 420px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  background: #fff;
  overflow: hidden;
}

.sql-editor:focus-within {
  border-color: var(--el-color-primary);
}

.sql-highlight,
.sql-textarea {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  margin: 0;
  padding: 10px 12px;
  box-sizing: border-box;
  font-family: 'SF Mono', 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-all;
  overflow: auto;
  tab-size: 4;
}

.sql-highlight {
  color: var(--el-text-color-primary);
  pointer-events: none;
}

.sql-highlight code {
  font-family: inherit;
  font-size: inherit;
}

.sql-textarea {
  border: none;
  outline: none;
  resize: none;
  background: transparent;
  color: transparent;
  caret-color: #000;
  -webkit-text-fill-color: transparent;
}

.sql-highlight :deep(.sql-kw) {
  color: #d63384;
  font-weight: 600;
}

.sql-highlight :deep(.sql-str) {
  color: #0a3069;
}

.sql-highlight :deep(.sql-num) {
  color: #953800;
}

.sql-highlight :deep(.sql-cmt) {
  color: #6e7781;
  font-style: italic;
}

.note-dialog-table {
  font-family: 'SF Mono', 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-primary);
  margin-bottom: 10px;
}

.result-area {
  width: 100%;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 10px 12px;
  box-sizing: border-box;
}

.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.result-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.result-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
