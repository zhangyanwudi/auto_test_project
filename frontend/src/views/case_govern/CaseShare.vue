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
      @back="goHome"
      @saved="() => {}"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchCaseList } from '../../api/case_govern/caseGovern.js'
import MindMapEditor from './MindMapEditor.vue'

const route = useRoute()
const router = useRouter()
const caseId = ref(null)
const caseName = ref('')

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
