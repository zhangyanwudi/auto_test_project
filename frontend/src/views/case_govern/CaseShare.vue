<template>
  <el-dialog
    :model-value="true"
    title="查看用例"
    fullscreen
    class="mind-dialog"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    @close="goHome"
  >
    <div v-if="loading" class="share-tip" v-loading="loading">
      <el-empty description="正在校验分享链接…" />
    </div>
    <div v-else-if="!caseId" class="share-tip">
      <el-empty :description="errorMsg || '分享链接无效或已过期'" />
    </div>
    <MindMapEditor
      v-else
      :case-id="caseId"
      :case-name="caseName"
      readonly
      expand-on-load
      :show-back="false"
      @saved="() => {}"
      @dirty-change="dirty = $event"
    />
  </el-dialog>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { verifyShareToken } from '../../api/case_govern/caseGovern.js'
import MindMapEditor from './MindMapEditor.vue'

const route = useRoute()
const router = useRouter()
const caseId = ref(null)
const caseName = ref('')
const dirty = ref(false)
const loading = ref(false)
const errorMsg = ref('')

async function loadByToken() {
  const token = (route.params.token || '').trim()
  if (!token) {
    errorMsg.value = '分享链接无效'
    return
  }
  loading.value = true
  try {
    const res = await verifyShareToken(token)
    if (res.code === 0 && res.data) {
      caseId.value = res.data.case_id
      caseName.value = res.data.case_name || ''
    } else {
      errorMsg.value = res.message || '分享链接无效或已过期'
    }
  } catch (e) {
    errorMsg.value = e.message || '分享链接无效或已过期'
  } finally {
    loading.value = false
  }
}

function goHome() {
  router.push('/home')
}

onMounted(() => {
  loadByToken()
})

// 拦截浏览器后退（Mac 左右滑动）等路由离开，未保存修改时先确认
onBeforeRouteLeave(async () => {
  if (!dirty.value) return true
  try {
    await ElMessageBox.confirm('思维导图有未保存的修改，离开后将丢失，确定离开吗？', '提示', {
      type: 'warning',
      confirmButtonText: '放弃修改并离开',
      cancelButtonText: '继续编辑',
    })
    return true
  } catch {
    return false
  }
})
</script>

<style scoped>
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

.share-tip {
  padding: 40px 0;
}
</style>
