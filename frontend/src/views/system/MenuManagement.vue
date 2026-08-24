<template>
  <div class="menu-mgmt">
    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <span>菜单列表</span>
          <el-button type="primary" @click="openDialog()">新增菜单</el-button>
        </div>
      </template>
      <el-table
        v-loading="loading"
        :data="list"
        border
        stripe
        style="width: 100%"
        :default-sort="{ prop: 'sort_order', order: 'ascending' }"
      >
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="menu_name" label="菜单名称" min-width="120" />
        <el-table-column prop="menu_code" label="菜单编码" min-width="120" />
        <el-table-column prop="path" label="前端路径（备注）" min-width="160" show-overflow-tooltip />
        <el-table-column prop="parent_id" label="父级ID" width="90" />
        <el-table-column prop="icon" label="图标" width="100" />
        <el-table-column prop="sort_order" label="排序" width="90" sortable />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'info'">
              {{ row.status === 1 ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <div class="table-ops">
              <el-button type="primary" size="small" @click="openDialog(row)">编辑</el-button>
              <el-button
                size="small"
                :type="row.status === 1 ? 'warning' : 'success'"
                @click="toggleStatus(row)"
              >
                {{ row.status === 1 ? '停用' : '启用' }}
              </el-button>
              <el-tooltip
                v-if="!isSuperAdmin()"
                content="仅超级管理员角色可删除菜单"
                placement="top"
              >
                <span class="del-wrap">
                  <el-button type="danger" size="small" disabled>删除</el-button>
                </span>
              </el-tooltip>
              <template v-else>
                <el-tooltip
                  v-if="row.status === 1"
                  content="请先停用菜单后再删除"
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
              </template>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑菜单' : '新增菜单'"
      width="520px"
      destroy-on-close
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="菜单名称" prop="menu_name">
          <el-input v-model="form.menu_name" placeholder="显示名称" />
        </el-form-item>
        <el-form-item label="菜单编码" prop="menu_code">
          <el-input v-model="form.menu_code" placeholder="唯一英文编码，如 home" :disabled="!!editingId" />
        </el-form-item>
        <el-form-item label="前端路径" prop="path">
          <el-input
            v-model="form.path"
            placeholder="选填：对应 Vue 文件路径，仅作文档备注"
          />
          <p class="form-item-hint">实际打开哪个页面由「菜单编码」与首页 viewMap 配置决定，此处不写不影响使用。</p>
        </el-form-item>
        <el-form-item label="父菜单ID" prop="parent_id">
          <el-input-number v-model="form.parent_id" :min="0" :controls="false" placeholder="空为顶级" />
        </el-form-item>
        <el-form-item label="图标" prop="icon">
          <el-input v-model="form.icon" placeholder="Element 图标名" />
        </el-form-item>
        <el-form-item label="排序" prop="sort_order">
          <el-input-number v-model="form.sort_order" :min="0" />
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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchMenuList, createMenu, updateMenu, setMenuStatus, deleteMenu } from '../../api/system/menu.js'
import { isSuperAdmin } from '../../common/request.js'

const loading = ref(false)
const list = ref([])
const dialogVisible = ref(false)
const saving = ref(false)
const editingId = ref(null)
const formRef = ref(null)

const form = reactive({
  menu_name: '',
  menu_code: '',
  path: '',
  parent_id: null,
  icon: '',
  sort_order: 0,
  status: 1,
})

const rules = {
  menu_name: [{ required: true, message: '请输入菜单名称', trigger: 'blur' }],
  menu_code: [{ required: true, message: '请输入菜单编码', trigger: 'blur' }],
}

async function loadList() {
  loading.value = true
  try {
    const res = await fetchMenuList()
    if (res.code === 0 && Array.isArray(res.data)) {
      // 按「排序」从小到大，同排序再按 id
      list.value = [...res.data].sort((a, b) => {
        const so = (a.sort_order ?? 0) - (b.sort_order ?? 0)
        if (so !== 0) return so
        return (a.id ?? 0) - (b.id ?? 0)
      })
    } else {
      list.value = []
    }
  } catch (e) {
    list.value = []
  } finally {
    loading.value = false
  }
}

function resetForm() {
  editingId.value = null
  form.menu_name = ''
  form.menu_code = ''
  form.path = ''
  form.parent_id = null
  form.icon = ''
  form.sort_order = 0
  form.status = 1
}

function openDialog(row) {
  resetForm()
  if (row) {
    editingId.value = row.id
    form.menu_name = row.menu_name
    form.menu_code = row.menu_code
    form.path = row.path || ''
    form.parent_id = row.parent_id || null
    form.icon = row.icon || ''
    form.sort_order = row.sort_order ?? 0
    form.status = row.status
  }
  dialogVisible.value = true
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
      menu_name: form.menu_name,
      menu_code: form.menu_code,
      path: form.path,
      icon: form.icon,
      sort_order: form.sort_order,
      parent_id: form.parent_id == null || form.parent_id === '' ? null : form.parent_id,
    }
    let res
    if (editingId.value) {
      res = await updateMenu(editingId.value, payload)
    } else {
      payload.status = form.status
      res = await createMenu(payload)
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

async function toggleStatus(row) {
  const next = row.status === 1 ? 0 : 1
  const tip = next === 0 ? '确定停用该菜单？' : '确定启用该菜单？'
  try {
    await ElMessageBox.confirm(tip, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    const res = await setMenuStatus(row.id, next)
    if (res.code === 0) {
      ElMessage.success('已更新')
      await loadList()
      window.dispatchEvent(new CustomEvent('admin-menu-updated'))
    } else {
      ElMessage.error(res.message || '操作失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '操作失败')
  }
}

async function onDelete(row) {
  if (row.status !== 0) {
    ElMessage.warning('请先停用菜单后再删除')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定永久删除菜单「${row.menu_name}」？删除后不可恢复，且需无子菜单。`,
      '删除菜单',
      { type: 'warning', confirmButtonText: '删除', confirmButtonClass: 'el-button--danger' },
    )
  } catch {
    return
  }
  try {
    const res = await deleteMenu(row.id)
    if (res.code === 0) {
      ElMessage.success(res.message || '已删除')
      await loadList()
      window.dispatchEvent(new CustomEvent('admin-menu-updated'))
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
.menu-mgmt {
  width: 100%;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.del-wrap {
  display: inline-block;
  vertical-align: middle;
}
.form-item-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
</style>
