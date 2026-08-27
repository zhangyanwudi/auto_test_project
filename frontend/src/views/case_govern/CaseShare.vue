<template>
  <div class="case-share-page">
    <div class="share-head">
      <el-button size="small" @click="goHome">返回首页</el-button>
      <span class="share-title">{{ caseName || '用例分享' }}</span>
    </div>
    <div v-if="!caseId" class="share-tip">
      <el-empty description="未找到该用例" />
    </div>
    <MindMapEditor
      v-else
      :case-id="caseId"
      :case-name="caseName"
      expand-on-load
      @back="goHome"
      @saved="() => {}"
      @dirty-change="dirty = $event"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { fetchCaseList } from '../../api/case_govern/caseGovern.js'
import MindMapEditor from './MindMapEditor.vue'

const route = useRoute()
const router = useRouter()
const caseId = ref(null)
const caseName = ref('')
const dirty = ref(false)

function parseId() {
  const raw = Number(route.params.id)
  caseId.value = Number.isFinite(raw) && raw > 0 ? raw : null
}

async function loadName() {
  if (!caseId.value) return
  try {
    const res = await fetchCaseList()
    if (res.code === 0 && Array.isArray(res.data)) {
      const found = res.data.find((c) => c.id === caseId.value)
      if (found) caseName.value = found.case_name || ''
    }
  } catch {
    // 静默失败
  }
}

function goHome() {
  router.push('/home')
}

onMounted(() => {
  parseId()
  loadName()
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
.case-share-page {
  min-height: 100vh;
  padding: 16px;
  box-sizing: border-box;
  background: #f0f2f5;
}

.share-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.share-title {
  font-weight: 600;
  font-size: 16px;
  color: #303133;
}

.share-tip {
  padding: 40px 0;
}

.case-share-page :deep(.mind-editor) {
  height: calc(100vh - 110px);
}
</style>
