<template>
  <el-card shadow="hover">
    <template #header>
      <span>{{ title }}</span>
    </template>
    <p class="tip">{{ description }}</p>
  </el-card>
</template>

<script setup>
defineProps({
  title: { type: String, default: '页面' },
  description: { type: String, default: '该功能模块开发中，敬请期待。' },
})
</script>

<style scoped>
.tip {
  color: #909399;
  margin: 0;
}
</style>
