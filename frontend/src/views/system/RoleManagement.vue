<template>
  <div class="role-mgmt">
    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <span>角色列表（z_role）</span>
          <el-button type="primary" @click="openCreate">新增角色</el-button>
        </div>
      </template>
      <el-table v-loading="loading" :data="list" border stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="role_name" label="角色名称" min-width="120" />
        <el-table-column prop="role_code" label="角色编码" min-width="120" />
        <el-table-column prop="remark" label="备注" min-width="140" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'info'">
              {{ row.status === 1 ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="已关联菜单" min-width="200">
          <template #default="{ row }">
            <span class="menu-count">{{ (row.menu_ids || []).length }} 项</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <div class="table-ops">
              <el-button type="primary" size="small" @click="openEdit(row)">编辑</el-button>
              <el-tooltip
                v-if="!isSuperAdmin()"
                content="仅超级管理员角色可删除角色"
                placement="top"
              >
                <span class="del-wrap">
                  <el-button type="danger" size="small" disabled>删除</el-button>
                </span>
              </el-tooltip>
              <el-tooltip
                v-else-if="row.role_code === 'super_admin'"
                content="超级管理员角色不可删除"
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
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑角色' : '新增角色'"
      width="560px"
      destroy-on-close
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="角色名称" prop="role_name">
          <el-input v-model="form.role_name" placeholder="显示名称" />
        </el-form-item>
        <el-form-item label="角色编码" prop="role_code">
          <el-input v-model="form.role_code" placeholder="英文唯一，如 editor" :disabled="!!editingId" />
        </el-form-item>
        <el-form-item label="备注" prop="remark">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-radio-group v-model="form.status">
            <el-radio :label="1">启用</el-radio>
            <el-radio :label="0">停用</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="关联菜单">
          <div class="menu-checks">
            <el-checkbox-group v-model="form.menu_ids">
              <el-checkbox v-for="m in menuOptions" :key="m.id" :label="m.id">
                {{ m.menu_name }} <span class="code">({{ m.menu_code }})</span>
              </el-checkbox>
            </el-checkbox-group>
          </div>
          <p class="hint">勾选该角色可访问的菜单；父级菜单需同时勾选子级所需的上级（按业务可再优化树形）。</p>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchRoleList, fetchMenuOptions, createRole, updateRole, deleteRole } from '../../api/system/role.js'
import { isSuperAdmin } from '../../common/request.js'

const loading = ref(false)
const list = ref([])
const menuOptions = ref([])
const dialogVisible = ref(false)
const saving = ref(false)
const editingId = ref(null)
const formRef = ref(null)
const form = reactive({
  role_name: '',
  role_code: '',
  remark: '',
  status: 1,
  menu_ids: [],
})
const rules = {
  role_name: [{ required: true, message: '请输入角色名称', trigger: 'blur' }],
  role_code: [{ required: true, message: '请输入角色编码', trigger: 'blur' }],
}

async function loadMenus() {
  const res = await fetchMenuOptions()
  if (res.code === 0 && Array.isArray(res.data)) {
    menuOptions.value = res.data
  }
}

async function loadList() {
  loading.value = true
  try {
    const res = await fetchRoleList()
    list.value = res.code === 0 && Array.isArray(res.data) ? res.data : []
  } catch {
    list.value = []
  } finally {
    loading.value = false
  }
}

function resetForm() {
  editingId.value = null
  form.role_name = ''
  form.role_code = ''
  form.remark = ''
  form.status = 1
  form.menu_ids = []
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  editingId.value = row.id
  form.role_name = row.role_name
  form.role_code = row.role_code
  form.remark = row.remark || ''
  form.status = row.status
  form.menu_ids = [...(row.menu_ids || [])]
  dialogVisible.value = true
}

async function submitForm() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const payload = {
      role_name: form.role_name.trim(),
      role_code: form.role_code.trim(),
      remark: form.remark,
      status: form.status,
      menu_ids: form.menu_ids,
    }
    let res
    if (editingId.value) {
      res = await updateRole(editingId.value, payload)
    } else {
      res = await createRole(payload)
    }
    if (res.code === 0) {
      ElMessage.success(res.message || '保存成功')
      dialogVisible.value = false
      await loadList()
      window.dispatchEvent(new CustomEvent('admin-menu-updated'))
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onDelete(row) {
  if (row.role_code === 'super_admin') {
    ElMessage.warning('超级管理员角色不可删除')
    return
  }
  try {
    await ElMessageBox.confirm(`确定删除角色「${row.role_name}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    const res = await deleteRole(row.id)
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
  loadMenus()
  loadList()
})
</script>

<style scoped>
.role-mgmt {
  width: 100%;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.menu-count {
  color: #606266;
}
.menu-checks {
  max-height: 260px;
  overflow-y: auto;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 12px;
}
.menu-checks :deep(.el-checkbox) {
  display: block;
  margin-right: 0;
  margin-bottom: 8px;
}
.code {
  color: #909399;
  font-size: 12px;
}
.hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: #909399;
}
.del-wrap {
  display: inline-block;
  vertical-align: middle;
}
</style>
