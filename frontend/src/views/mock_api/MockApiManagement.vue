<template>
  <div class="mock-api-mgmt">
    <!-- ===== 代理状态栏（共享服务，页面不启停） ===== -->
    <el-card shadow="never" class="proxy-card">
      <div class="proxy-bar">
        <span class="proxy-left">
          <span class="status-dot" :class="proxyRunning ? 'dot-on' : 'dot-off'"></span>
          <el-tag :type="proxyRunning ? 'success' : 'info'" size="small" effect="dark">
            {{ proxyRunning ? '代理运行中' : '代理未运行' }}
          </el-tag>
          <span v-if="proxyRunning" class="proxy-hint">端口 {{ proxyPort }}</span>
          <span class="proxy-tip">
            代理为测试服共享服务，本页只管理规则；启用/停用会自动同步到运行中的代理
          </span>
        </span>
        <span class="proxy-right">
          <el-button size="small" :loading="statusLoading" @click="fetchProxyStatus">刷新状态</el-button>
        </span>
      </div>
      <div v-if="!proxyRunning" class="proxy-offline-tip">
        当前代理未运行。请在测试服务器上执行：
        <code>python scripts/start_mock_proxy.py --port {{ proxyPort }} --reload-interval 2</code>
      </div>
      <div v-if="proxyRunning" class="cert-tip">
        <el-icon style="margin-right: 6px;"><WarningFilled /></el-icon>
        <span>
          手机端需安装代理证书才能拦截 HTTPS 请求：手机设置代理后，浏览器访问
          <strong>http://mitm.it</strong>
          下载并安装对应平台的证书。如无法访问，请检查代理 IP 和端口配置是否正确。
        </span>
      </div>
    </el-card>

    <!-- ===== 规则列表 ===== -->
    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <span>Mock 规则列表</span>
          <el-button type="primary" size="small" @click="openRuleDialog()">新增规则</el-button>
        </div>
      </template>
      <el-table
        v-loading="loading"
        :data="list"
        border
        stripe
        style="width: 100%"
        empty-text="暂无 Mock 规则，点击上方「新增规则」创建"
      >
        <el-table-column prop="id" label="ID" width="55" align="center" />
        <el-table-column prop="rule_name" label="规则名称" min-width="120" show-overflow-tooltip />
        <el-table-column prop="url_pattern" label="URL 拦截地址" min-width="200" show-overflow-tooltip />
        <el-table-column prop="match_type" label="匹配方式" width="85" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.match_type === 'regex' ? 'warning' : ''">
              {{ matchTypeLabel(row.match_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status_code" label="状态码" width="75" align="center" />
        <el-table-column label="状态" width="75" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'info'" size="small">
              {{ row.status === 1 ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip />
        <el-table-column label="操作" width="220">
          <template #default="{ row }">
            <el-button type="primary" size="small" link @click="openRuleDialog(row)">编辑</el-button>
            <el-button
              size="small" link
              :type="row.status === 1 ? 'warning' : 'success'"
              @click="handleToggleRuleStatus(row)"
            >
              {{ row.status === 1 ? '停用' : '启用' }}
            </el-button>
            <el-button
              type="danger" size="small" link
              :disabled="row.status === 1"
              @click="handleDeleteRule(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ===== 规则编辑对话框 ===== -->
    <el-dialog
      v-model="ruleDialogVisible"
      :title="editingRuleId ? '编辑规则' : '新增规则'"
      width="580px"
      destroy-on-close
      :close-on-click-modal="false"
    >
      <el-form :model="ruleForm" label-width="105px" size="default">
        <el-form-item label="规则名称" required>
          <el-input v-model="ruleForm.rule_name" placeholder="如：ECPM接口Mock" maxlength="128" />
        </el-form-item>
        <el-form-item label="拦截地址" required>
          <el-input v-model="ruleForm.url_pattern" placeholder="拦截的 URL 关键字或正则表达式" maxlength="512" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="匹配方式">
              <el-select v-model="ruleForm.match_type" style="width: 100%">
                <el-option label="包含 (contains)" value="contains" />
                <el-option label="正则 (regex)" value="regex" />
                <el-option label="精确 (exact)" value="exact" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="HTTP 状态码">
              <el-input-number v-model="ruleForm.status_code" :min="100" :max="599" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="返回内容" required>
          <el-input
            v-model="ruleForm.response_data"
            type="textarea"
            :rows="6"
            placeholder='{"code": 0, "message": "ok", "data": {...}}'
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="ruleForm.remark" placeholder="规则说明（可选）" maxlength="512" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ruleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSaveRule">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { WarningFilled } from '@element-plus/icons-vue'
import {
  getRules, createRule, updateRule, toggleRuleStatus, deleteRule,
  getProxyStatus,
} from '../../api/mock_api/index.js'

const loading = ref(false)
const list = ref([])
const saving = ref(false)
const ruleDialogVisible = ref(false)
const editingRuleId = ref(null)

const proxyRunning = ref(false)
const proxyPort = ref(8080)
const statusLoading = ref(false)
let statusTimer = null

const defaultForm = () => ({
  rule_name: '',
  url_pattern: '',
  match_type: 'contains',
  status_code: 200,
  response_data: '',
  sort_order: 0,
  status: 1,
  remark: '',
})

const ruleForm = reactive(defaultForm())

function matchTypeLabel(type) {
  const map = { contains: '包含', regex: '正则', exact: '精确' }
  return map[type] || type
}

async function fetchRules() {
  loading.value = true
  try {
    const res = await getRules()
    if (res && res.code === 0) {
      list.value = res.data || []
    }
  } catch {
    ElMessage.error('加载规则失败')
  } finally {
    loading.value = false
  }
}

function openRuleDialog(row = null) {
  editingRuleId.value = row ? row.id : null
  Object.assign(ruleForm, defaultForm())
  if (row) {
    Object.assign(ruleForm, {
      rule_name: row.rule_name || '',
      url_pattern: row.url_pattern || '',
      match_type: row.match_type || 'contains',
      status_code: row.status_code || 200,
      response_data: row.response_data || '',
      sort_order: row.sort_order || 0,
      status: row.status,
      remark: row.remark || '',
    })
  }
  ruleDialogVisible.value = true
}

async function handleSaveRule() {
  if (!(ruleForm.rule_name || '').trim() || !(ruleForm.url_pattern || '').trim()) {
    ElMessage.warning('规则名称与拦截地址不能为空')
    return
  }
  if (!(ruleForm.response_data || '').trim()) {
    ElMessage.warning('返回内容不能为空')
    return
  }
  saving.value = true
  try {
    const payload = {
      rule_name: ruleForm.rule_name.trim(),
      url_pattern: ruleForm.url_pattern.trim(),
      match_type: ruleForm.match_type,
      status_code: ruleForm.status_code,
      response_data: ruleForm.response_data.trim(),
      sort_order: ruleForm.sort_order,
      status: ruleForm.status,
      remark: (ruleForm.remark || '').trim(),
    }
    const res = editingRuleId.value
      ? await updateRule(editingRuleId.value, payload)
      : await createRule(payload)
    if (res && res.code === 0) {
      ElMessage.success(editingRuleId.value ? '保存成功' : '创建成功')
      ruleDialogVisible.value = false
      await fetchRules()
    } else {
      ElMessage.error((res && res.message) || '保存失败')
    }
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function handleToggleRuleStatus(row) {
  const next = row.status === 1 ? 0 : 1
  const action = next === 1 ? '启用' : '停用'
  try {
    await ElMessageBox.confirm(`确认${action}规则「${row.rule_name}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    const res = await toggleRuleStatus(row.id, next)
    if (res && res.code === 0) {
      ElMessage.success(res.message || `已${action}`)
      await fetchRules()
    } else {
      ElMessage.error((res && res.message) || `${action}失败`)
    }
  } catch {
    ElMessage.error(`${action}失败`)
  }
}

async function handleDeleteRule(row) {
  try {
    await ElMessageBox.confirm(`确认删除规则「${row.rule_name}」？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    const res = await deleteRule(row.id)
    if (res && res.code === 0) {
      ElMessage.success('已删除')
      await fetchRules()
    } else {
      ElMessage.error((res && res.message) || '删除失败')
    }
  } catch {
    ElMessage.error('删除失败')
  }
}

async function fetchProxyStatus() {
  statusLoading.value = true
  try {
    const res = await getProxyStatus()
    if (res && res.code === 0 && res.data) {
      proxyRunning.value = !!res.data.running
      if (res.data.port) {
        proxyPort.value = res.data.port
      }
    }
  } catch { /* 忽略 */ } finally {
    statusLoading.value = false
  }
}

onMounted(() => {
  fetchRules()
  fetchProxyStatus()
  // 定时刷新状态，方便看到服务器侧代理是否在跑
  statusTimer = setInterval(fetchProxyStatus, 10000)
})

onUnmounted(() => {
  if (statusTimer) {
    clearInterval(statusTimer)
    statusTimer = null
  }
})
</script>

<style scoped>
.mock-api-mgmt {
  padding: 0;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.proxy-card {
  margin-bottom: 16px;
}

.proxy-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.proxy-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.proxy-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.proxy-hint {
  color: #606266;
  font-size: 13px;
}

.proxy-tip {
  color: #909399;
  font-size: 12px;
}

.proxy-offline-tip {
  margin-top: 10px;
  padding: 8px 12px;
  background: #fdf6ec;
  color: #b88230;
  font-size: 12px;
  border-radius: 4px;
  line-height: 1.6;
}

.proxy-offline-tip code {
  display: inline-block;
  margin-left: 4px;
  padding: 1px 6px;
  background: #fff;
  border-radius: 3px;
  font-size: 12px;
  color: #303133;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.dot-on {
  background: #67c23a;
  box-shadow: 0 0 6px rgba(103, 194, 58, 0.7);
}

.dot-off {
  background: #c0c4cc;
}

.cert-tip {
  margin-top: 10px;
  padding: 8px 12px;
  background: #ecf5ff;
  color: #409eff;
  font-size: 12px;
  border-radius: 4px;
  line-height: 1.6;
  display: flex;
  align-items: flex-start;
}

.cert-tip strong {
  color: #337ecc;
}
</style>
