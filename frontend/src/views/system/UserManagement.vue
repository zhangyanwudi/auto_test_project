<template>
  <div class="user-mgmt">
    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <span>用户列表（z_user）</span>
          <el-button type="primary" @click="openCreate">新增用户</el-button>
        </div>
      </template>
      <el-table v-loading="loading" :data="list" border stripe>
        <el-table-column prop="id" label="ID" width="70"/>
        <el-table-column prop="user_name" label="用户名" min-width="120"/>
        <el-table-column prop="user_cn_name" label="中文名" min-width="120"/>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.user_status === 1 ? 'success' : 'info'">
              {{ row.user_status === 1 ? '正常' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="user_power" label="权限" width="80"/>
        <el-table-column prop="create_time" label="创建时间" min-width="170" show-overflow-tooltip/>
        <el-table-column prop="login_time" label="最近登录时间" min-width="170" show-overflow-tooltip/>
        <el-table-column label="角色" min-width="160">
          <template #default="{ row }">
            <el-tag v-if="row.is_admin" type="warning" size="small" class="mr">系统管理员</el-tag>
            <span v-if="row.role_name">{{ row.role_name }}</span>
            <span v-else-if="!row.is_admin" class="muted">未分配</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <div class="table-ops">
              <el-button type="primary" size="small" @click="openEdit(row)">编辑</el-button>
              <el-button type="warning" size="small" @click="openPassword(row)">改密码</el-button>
              <el-tooltip
                v-if="!isSuperAdmin()"
                content="仅超级管理员角色可删除用户"
                placement="top"
              >
                <span class="del-wrap">
                  <el-button type="danger" size="small" disabled>删除</el-button>
                </span>
              </el-tooltip>
              <el-tooltip
                v-else-if="row.is_admin"
                content="系统管理员用户不可删除"
                placement="top"
              >
                <span class="del-wrap">
                  <el-button type="danger" size="small" disabled>删除</el-button>
                </span>
              </el-tooltip>
              <el-button
                v-else
                type="danger"
                size="small"
                @click="onDelete(row)"
              >
                删除
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <p v-if="list.length && list[0]?.is_admin" class="tip">ID 最小的用户为系统管理员，不可删除；改密后需重新登录。</p>
    </el-card>

    <!-- 新增：打开后再次清空密码/中文名，避免浏览器自动填充 -->
    <el-dialog
      v-model="createVisible"
      title="新增用户"
      width="480px"
      destroy-on-close
      @closed="resetCreate"
      @opened="onCreateDialogOpened"
    >
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="100px" autocomplete="off">
        <el-form-item label="用户名" prop="user_name">
          <el-input
            v-model="createForm.user_name"
            placeholder="登录账号"
            name="new_account_user_name"
            autocomplete="off"
            autocorrect="off"
            spellcheck="false"
          />
        </el-form-item>
        <el-form-item label="中文名" prop="user_cn_name">
          <el-input
            v-model="createForm.user_cn_name"
            placeholder="选填，不填则与用户名一致"
            name="new_account_cn_name"
            autocomplete="off"
            autocorrect="off"
            spellcheck="false"
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="createForm.password"
            type="password"
            show-password
            placeholder="请设置初始密码"
            name="new_account_password"
            autocomplete="new-password"
          />
        </el-form-item>
        <el-form-item label="角色" prop="role_id">
          <el-select v-model="createForm.role_id" placeholder="可选" clearable filterable style="width: 100%">
            <el-option
                v-for="r in enabledRoles"
                :key="r.id"
                :label="r.role_name"
                :value="r.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" prop="user_status">
          <el-radio-group v-model="createForm.user_status">
            <el-radio :label="1">正常</el-radio>
            <el-radio :label="0">停用</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="createSaving" @click="submitCreate">确定</el-button>
      </template>
    </el-dialog>

    <!-- 编辑 -->
    <el-dialog v-model="editVisible" title="编辑用户" width="480px" destroy-on-close @closed="resetEdit">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="100px">
        <el-form-item label="用户名">
          <el-input :model-value="editRow?.user_name" disabled/>
        </el-form-item>
        <el-form-item label="中文名" prop="user_cn_name">
          <el-input v-model="editForm.user_cn_name" placeholder="显示名称"/>
        </el-form-item>
        <el-form-item label="角色" prop="role_id">
          <el-select v-model="editForm.role_id" placeholder="可选" clearable filterable style="width: 100%">
            <el-option
                v-for="r in allRoles"
                :key="r.id"
                :label="r.role_name + (r.status !== 1 ? '（已停用）' : '')"
                :value="r.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" prop="user_status">
          <el-radio-group v-model="editForm.user_status" :disabled="editRow?.is_admin">
            <el-radio :label="1">正常</el-radio>
            <el-radio :label="0">停用</el-radio>
          </el-radio-group>
          <p v-if="editRow?.is_admin" class="field-hint">系统管理员须保持为「正常」</p>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 改密码 -->
    <el-dialog v-model="pwdVisible" title="修改密码" width="440px" destroy-on-close @closed="resetPwd">
      <p v-if="pwdRow" class="pwd-user">用户：<strong>{{ pwdRow.user_name }}</strong></p>
      <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="100px">
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="pwdForm.new_password" type="password" show-password autocomplete="new-password"/>
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm">
          <el-input v-model="pwdForm.confirm" type="password" show-password/>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdVisible = false">取消</el-button>
        <el-button type="primary" :loading="pwdSaving" @click="submitPwd">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import {ref, reactive, computed, onMounted, nextTick} from 'vue'
import {ElMessage, ElMessageBox} from 'element-plus'
import {fetchUserList, createUser, updateUser, deleteUser, changeUserPassword} from '../../api/system/user.js'
import {fetchRoleList} from '../../api/system/role.js'
import {isSuperAdmin} from '../../common/request.js'

const loading = ref(false)
const list = ref([])
/** 全部角色（编辑时用）；新增时仅用启用中的 */
const allRoles = ref([])
const enabledRoles = computed(() => allRoles.value.filter((r) => r.status === 1))

const createVisible = ref(false)
const createSaving = ref(false)
const createFormRef = ref(null)
const createForm = reactive({
  user_name: '',
  user_cn_name: '',
  password: '',
  user_status: 1,
  role_id: null,
})
const createRules = {
  user_name: [{required: true, message: '请输入用户名', trigger: 'blur'}],
  password: [{required: true, message: '请输入密码', trigger: 'blur'}],
}

const editVisible = ref(false)
const editSaving = ref(false)
const editRow = ref(null)
const editFormRef = ref(null)
const editForm = reactive({
  user_cn_name: '',
  user_status: 1,
  role_id: null,
})
const editRules = {
  user_cn_name: [{required: true, message: '请输入中文名', trigger: 'blur'}],
}

const pwdVisible = ref(false)
const pwdSaving = ref(false)
const pwdRow = ref(null)
const pwdFormRef = ref(null)
const pwdForm = reactive({new_password: '', confirm: ''})
const pwdRules = {
  new_password: [{required: true, message: '请输入新密码', trigger: 'blur'}],
  confirm: [
    {required: true, message: '请再次输入', trigger: 'blur'},
    {
      validator: (_r, v, cb) => {
        if (v !== pwdForm.new_password) cb(new Error('两次密码不一致'))
        else cb()
      },
      trigger: 'blur',
    },
  ],
}

async function loadRoles() {
  try {
    const res = await fetchRoleList()
    allRoles.value = res.code === 0 && Array.isArray(res.data) ? res.data : []
  } catch {
    allRoles.value = []
  }
}

async function loadList() {
  loading.value = true
  try {
    const res = await fetchUserList()
    if (res.code === 0 && Array.isArray(res.data)) {
      list.value = res.data
    } else {
      list.value = []
    }
  } catch {
    list.value = []
  } finally {
    loading.value = false
  }
}

function resetCreate() {
  createForm.user_name = ''
  createForm.user_cn_name = ''
  createForm.password = ''
  createForm.user_status = 1
  createForm.role_id = null
}

function openCreate() {
  resetCreate()
  createVisible.value = true
}

/** 弹窗完全打开后再清空一次，避免 Chrome 等在「用户名」后自动填入已保存的密码/姓名 */
function onCreateDialogOpened() {
  nextTick(() => {
    setTimeout(() => {
      createForm.password = ''
      createForm.user_cn_name = ''
      createFormRef.value?.clearValidate?.(['password', 'user_cn_name'])
    }, 80)
  })
}

async function submitCreate() {
  try {
    await createFormRef.value?.validate()
  } catch {
    return
  }
  createSaving.value = true
  try {
    const body = {
      user_name: createForm.user_name.trim(),
      user_cn_name: (createForm.user_cn_name || createForm.user_name).trim(),
      password: createForm.password,
      user_status: createForm.user_status,
    }
    if (createForm.role_id != null) {
      body.role_id = createForm.role_id
    }
    const res = await createUser(body)
    if (res.code === 0) {
      ElMessage.success(res.message || '创建成功')
      createVisible.value = false
      await loadList()
    } else {
      ElMessage.error(res.message || '创建失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '创建失败')
  } finally {
    createSaving.value = false
  }
}

function resetEdit() {
  editRow.value = null
  editForm.user_cn_name = ''
  editForm.user_status = 1
  editForm.role_id = null
}

function openEdit(row) {
  editRow.value = row
  editForm.user_cn_name = row.user_cn_name || row.user_name
  editForm.user_status = row.user_status
  editForm.role_id = row.role_id ?? null
  editVisible.value = true
}

async function submitEdit() {
  try {
    await editFormRef.value?.validate()
  } catch {
    return
  }
  if (!editRow.value) return
  editSaving.value = true
  try {
    const body = {
      user_cn_name: editForm.user_cn_name.trim(),
      user_status: editForm.user_status,
      role_id: editForm.role_id,
    }
    const res = await updateUser(editRow.value.id, body)
    if (res.code === 0) {
      ElMessage.success(res.message || '保存成功')
      editVisible.value = false
      await loadList()
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    editSaving.value = false
  }
}

function resetPwd() {
  pwdRow.value = null
  pwdForm.new_password = ''
  pwdForm.confirm = ''
}

function openPassword(row) {
  pwdForm.new_password = ''
  pwdForm.confirm = ''
  pwdRow.value = row
  pwdVisible.value = true
}

async function submitPwd() {
  try {
    await pwdFormRef.value?.validate()
  } catch {
    return
  }
  pwdSaving.value = true
  try {
    const res = await changeUserPassword(pwdRow.value.id, pwdForm.new_password)
    if (res.code === 0) {
      ElMessage.success(res.message || '密码已更新')
      pwdVisible.value = false
    } else {
      ElMessage.error(res.message || '修改失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '修改失败')
  } finally {
    pwdSaving.value = false
  }
}

async function onDelete(row) {
  if (row.is_admin) {
    ElMessage.warning('管理员用户不可删除')
    return
  }
  try {
    await ElMessageBox.confirm(`确定删除用户「${row.user_name}」？`, '提示', {type: 'warning'})
  } catch {
    return
  }
  try {
    const res = await deleteUser(row.id)
    if (res.code === 0) {
      ElMessage.success('已删除')
      await loadList()
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
  }
}

onMounted(() => {
  loadRoles()
  loadList()
})
</script>

<style scoped>
.user-mgmt {
  width: 100%;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.tip {
  margin: 12px 0 0;
  font-size: 13px;
  color: #909399;
}

.pwd-user {
  margin: 0 0 16px;
  font-size: 14px;
  color: #606266;
}

.muted {
  color: #c0c4cc;
  font-size: 13px;
}

.mr {
  margin-right: 6px;
}

.field-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: #909399;
}

.del-wrap {
  display: inline-block;
  vertical-align: middle;
}
</style>
