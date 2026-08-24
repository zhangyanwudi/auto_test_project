<template>
  <div class="icon-mgmt">
    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <div>
            <span class="title">Element Plus 图标</span>
            <span class="sub">（@element-plus/icons-vue，菜单「图标」字段填下列名称）</span>
          </div>
          <span class="count">共 {{ filteredNames.length }} / {{ allNames.length }} 个</span>
        </div>
      </template>

      <div class="toolbar">
        <el-input
          v-model="keyword"
          clearable
          placeholder="搜索图标名称，如 User、House"
          class="search"
          :prefix-icon="Search"
        />
        <el-button type="primary" size="small" @click="copyAllNames">复制当前列表名称（逗号分隔）</el-button>
      </div>

      <el-scrollbar max-height="calc(100vh - 280px)">
        <div class="icon-grid">
          <div
            v-for="name in filteredNames"
            :key="name"
            class="icon-cell"
            :title="'点击复制：' + name"
            @click="copyName(name)"
          >
            <el-icon :size="28" class="icon-preview">
              <component :is="EP_ICONS[name]" />
            </el-icon>
            <span class="icon-name">{{ name }}</span>
          </div>
        </div>
      </el-scrollbar>
    </el-card>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import * as EP_ICONS from '@element-plus/icons-vue'

/** 全部导出名即组件名（与菜单里填写的 icon 一致） */
const allNames = Object.keys(EP_ICONS).sort((a, b) =>
  a.localeCompare(b, 'en')
)

const keyword = ref('')

const filteredNames = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  if (!q) return allNames
  return allNames.filter((n) => n.toLowerCase().includes(q))
})

/** 通用复制方法：优先 Clipboard API，失败时降级到 execCommand */
async function copyText(text, successMsg, failMsg) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success(successMsg)
  } catch {
    // Clipboard API 不可用时（非安全上下文如局域网 IP 访问），降级到传统方式
    try {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.left = '-9999px'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      ElMessage.success(successMsg)
    } catch {
      ElMessage.error(failMsg)
    }
  }
}

async function copyName(name) {
  await copyText(name, `已复制：${name}`, '复制失败，请手动选择复制')
}

async function copyAllNames() {
  const text = filteredNames.value.join(',')
  await copyText(text, '已复制当前列表全部名称', '复制失败')
}
</script>

<style scoped>
.icon-mgmt {
  width: 100%;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.title {
  font-weight: 600;
}
.sub {
  margin-left: 8px;
  font-size: 13px;
  color: #909399;
  font-weight: normal;
}
.count {
  font-size: 13px;
  color: #606266;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
}
.search {
  max-width: 360px;
  flex: 1;
  min-width: 200px;
}
.icon-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
}
.icon-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 10px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.icon-cell:hover {
  border-color: #409eff;
  background: #ecf5ff;
}
.icon-preview {
  color: #606266;
}
.icon-name {
  font-size: 12px;
  color: #303133;
  text-align: center;
  word-break: break-all;
  line-height: 1.3;
  user-select: all;
}
</style>
