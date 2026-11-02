<script setup>
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'

import { USE_MOCK } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { safeRedirect } from '@/utils/redirect'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const formRef = ref(null)
const busy = ref(false)
const error = ref('')

const form = reactive({ username: '', password: '' })

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const redirectTarget = computed(() => safeRedirect(route.query.redirect) || '/resume')

async function onSubmit() {
  if (busy.value) return
  error.value = ''
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  busy.value = true
  try {
    await auth.login({ username: form.username, password: form.password })
    ElMessage.success('登录成功，欢迎回来')
    router.replace(redirectTarget.value)
  } catch (err) {
    error.value = err?.message || '登录失败，请稍后重试'
  } finally {
    busy.value = false
  }
}

function fillDemo() {
  form.username = 'demo'
  form.password = 'demo1234'
}
</script>

<template>
  <div class="auth-form">
    <router-link to="/welcome" class="auth-form__back">
      <svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true">
        <path d="M9.5 3.5 5 8l4.5 4.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      返回首页
    </router-link>

    <header class="auth-form__head">
      <p class="eyebrow">Account</p>
      <h2>欢迎回来</h2>
      <p class="auth-form__sub">登录后继续你的面试备战进度。</p>
    </header>

    <div v-if="USE_MOCK" class="mode-banner" role="status">
      <div class="mode-banner__head">
        <span class="mode-banner__tag">演示模式</span>
        <button type="button" class="mode-banner__fill" @click="fillDemo">填入 demo / demo1234</button>
      </div>
      <p>当前登录不会请求后端，账号只存在本机浏览器；数据库里的账号在这里无法登录。</p>
    </div>

    <transition name="fade">
      <div v-if="error" class="alert" role="alert">{{ error }}</div>
    </transition>

    <el-form
      ref="formRef"
      class="auth-form__body"
      :model="form"
      :rules="rules"
      label-position="top"
      hide-required-asterisk
      @submit.prevent="onSubmit"
    >
      <el-form-item label="用户名" prop="username">
        <el-input
          v-model.trim="form.username"
          size="large"
          placeholder="请输入用户名"
          autocomplete="username"
          :prefix-icon="User"
        />
      </el-form-item>

      <el-form-item label="密码" prop="password">
        <el-input
          v-model="form.password"
          size="large"
          type="password"
          placeholder="请输入密码"
          autocomplete="current-password"
          show-password
          :prefix-icon="Lock"
        />
      </el-form-item>

      <el-button
        type="primary"
        size="large"
        class="auth-form__submit"
        :loading="busy"
        native-type="submit"
      >
        登录
      </el-button>
    </el-form>

    <p class="auth-form__switch">
      还没有账号？
      <router-link :to="{ name: 'register', query: route.query }">立即注册</router-link>
    </p>
  </div>
</template>

<style scoped>
.auth-form {
  display: flex;
  flex-direction: column;
}

.auth-form__back {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  align-self: flex-start;
  margin-bottom: 22px;
  font-size: 11.5px;
  color: var(--ink-3);
  padding: 3px 8px 3px 4px;
  border-radius: 6px;
  transition: color 0.16s ease, background-color 0.16s ease;
}

.auth-form__back:hover {
  color: var(--primary-strong);
  background: var(--primary-soft);
}

.auth-form__head {
  margin-bottom: 26px;
}

.auth-form__head .eyebrow {
  margin-bottom: 10px;
  color: var(--primary);
}

.auth-form__head h2 {
  font-size: 26px;
  letter-spacing: -0.03em;
}

.auth-form__sub {
  margin-top: 8px;
  font-size: 13px;
  color: var(--ink-3);
}

.auth-form__body {
  margin-top: 2px;
}

.auth-form__submit {
  width: 100%;
  margin-top: 6px;
  letter-spacing: 0.02em;
}

.auth-form__switch {
  margin-top: 20px;
  font-size: 12.5px;
  color: var(--ink-3);
  text-align: center;
}

.auth-form__switch a {
  font-weight: 600;
  margin-left: 2px;
}

.alert {
  margin-bottom: 16px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid #f4d4d3;
  background: var(--danger-soft);
  color: #b03e3d;
  font-size: 12.5px;
  line-height: 1.55;
}

.mode-banner {
  margin-bottom: 18px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid #f0dfbf;
  background: var(--warn-soft);
  color: #7d5814;
  font-size: 11.5px;
  line-height: 1.65;
}

.mode-banner__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 4px;
}

.mode-banner__tag {
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.04em;
  color: #96600f;
}

.mode-banner__fill {
  border: 0;
  background: transparent;
  color: #96600f;
  font-size: 10.5px;
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 2px;
  cursor: pointer;
  padding: 0;
}

.mode-banner p {
  color: #7d5814;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.18s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
