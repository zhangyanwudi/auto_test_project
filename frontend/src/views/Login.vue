<template>
  <div class="login-page">
    <div class="login-bg" />
    <el-card class="login-card" shadow="always">
      <template #header>
        <div class="card-header">
          <span class="title">{{ pageTitle }}登录</span>
        </div>
      </template>
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        size="large"
        @submit.prevent="onSubmit"
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            clearable
            :prefix-icon="User"
            autocomplete="username"
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            show-password
            clearable
            :prefix-icon="Lock"
            autocomplete="current-password"
            @keyup.enter="onSubmit"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            :loading="loading"
            class="submit-btn"
            native-type="submit"
          >
            {{ loading ? '登录中…' : '登 录' }}
          </el-button>
        </el-form-item>
        <el-alert
          v-if="message"
          :title="message"
          :type="isError ? 'error' : 'success'"
          :closable="false"
          show-icon
          class="message-alert"
        />
      </el-form>
      <div v-if="ssoEnabled" class="sso-area">
        <el-divider>其他登录方式</el-divider>
        <el-button
          class="sso-btn"
          :loading="ssoLoading"
          @click="onSsoLogin"
        >
          SSO统一登录
        </el-button>
      </div>
      <div class="footer">
        <router-link to="/" class="link">返回首页</router-link>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { login as loginApi, getSsoLoginUrl } from '../api/login.js'
import { getPageTitle, isSsoEnabled } from '../common/request.js'

const router = useRouter()
const route = useRoute()
const formRef = ref(null)
const loading = ref(false)
const message = ref('')
const isError = ref(false)
const pageTitle = ref(getPageTitle())

const form = reactive({
  username: '',
  password: '',
})

const ssoEnabled = ref(false)
const ssoLoading = ref(false)

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
  ],
}

async function onSubmit() {
  message.value = ''
  isError.value = false
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    const data = await loginApi({
      username: form.username,
      password: form.password,
    })
    if (data.code === 0 && data.data) {
      message.value = '登录成功'
      isError.value = false
      const redirect =
        typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/')
          ? route.query.redirect
          : ''
      setTimeout(() => router.push(redirect || '/home'), 800)
    } else {
      message.value = data.message || '登录失败，请重试'
      isError.value = true
    }
  } catch (e) {
    message.value = e.message || '登录失败，请重试'
    isError.value = true
  } finally {
    loading.value = false
  }
}

async function onSsoLogin() {
  message.value = ''
  isError.value = false
  ssoLoading.value = true
  try {
    const data = await getSsoLoginUrl()
    if (data.code === 0 && data.data && data.data.login_url) {
      window.location.href = data.data.login_url
    } else {
      message.value = data.message || '获取统一登录地址失败'
      isError.value = true
    }
  } catch (e) {
    message.value = e.message || '获取统一登录地址失败'
    isError.value = true
  } finally {
    ssoLoading.value = false
  }
}

function handleSsoCallback() {
  const q = new URLSearchParams(window.location.search)
  const err = q.get('sso_error')
  if (err) {
    message.value = err
    isError.value = true
    history.replaceState({}, '', '/')
  }
}

onMounted(() => {
  document.title = pageTitle.value + ' - 登录'
  ssoEnabled.value = isSsoEnabled()
  handleSsoCallback()
})
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}
.login-bg {
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, #1e3a5f 0%, #0d1b2a 50%, #1b263b 100%);
}
.login-card {
  position: relative;
  width: 100%;
  max-width: 420px;
  border-radius: 12px;
}
.card-header {
  text-align: center;
}
.title {
  font-size: 1.35rem;
  font-weight: 600;
  color: #303133;
}
.submit-btn {
  width: 100%;
}
.message-alert {
  margin-top: 12px;
}
.sso-area {
  margin-top: 8px;
}
.sso-btn {
  width: 100%;
}
.footer {
  margin-top: 16px;
  text-align: center;
}
.link {
  color: var(--el-color-primary);
  text-decoration: none;
  font-size: 14px;
}
.link:hover {
  text-decoration: underline;
}
</style>
