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

const form = reactive({ username: '', password: '', confirm: '' })

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    {
      pattern: /^[a-zA-Z0-9_]{3,32}$/,
      message: '3-32 位字母、数字或下划线',
      trigger: 'blur',
    },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 4, max: 10, message: '密码长度为 4-10 位', trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== form.password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}

const redirectTarget = computed(() => safeRedirect(route.query.redirect) || '/resume')

async function onSubmit() {
  if (busy.value) return
  error.value = ''
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  busy.value = true
  try {
    await auth.register({ username: form.username, password: form.password })
    ElMessage.success('注册成功，已为你登录')
    router.replace(redirectTarget.value)
  } catch (err) {
    error.value = err?.message || '注册失败，请稍后重试'
  } finally {
    busy.value = false
  }
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
      <p class="eyebrow">Get started</p>
      <h2>创建你的账号</h2>
      <p class="auth-form__sub">诊断记录、面试复盘与薄弱点都按账号沉淀。</p>
    </header>

    <div v-if="USE_MOCK" class="mode-banner" role="status">
      <span class="mode-banner__tag">演示模式</span>
      <p>注册只会写入本机浏览器，不会写入数据库；数据库账号请关闭 VITE_USE_MOCK 后再注册。</p>
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
          placeholder="3-32 位字母、数字或下划线"
          autocomplete="username"
          :prefix-icon="User"
        />
      </el-form-item>

      <el-form-item label="密码" prop="password">
        <el-input
          v-model="form.password"
          size="large"
          type="password"
          placeholder="4-10 位字符"
          autocomplete="new-password"
          show-password
          :prefix-icon="Lock"
        />
      </el-form-item>

      <el-form-item label="确认密码" prop="confirm">
        <el-input
          v-model="form.confirm"
          size="large"
          type="password"
          placeholder="再次输入密码"
          autocomplete="new-password"
          show-password
          :prefix-icon="Lock"
        />
      </el-form-item>

      <p class="auth-form__hint">密码长度 4-10 位，与后端校验规则保持一致。</p>

      <el-button
        type="primary"
        size="large"
        class="auth-form__submit"
        :loading="busy"
        native-type="submit"
      >
        注册并进入工作台
      </el-button>
    </el-form>

    <p class="auth-form__switch">
      已有账号？
      <router-link :to="{ name: 'login', query: route.query }">返回登录</router-link>
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
  margin-bottom: 24px;
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

.auth-form__hint {
  margin: -6px 0 16px;
  font-size: 11.5px;
  color: var(--ink-4);
}

.auth-form__submit {
  width: 100%;
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

.mode-banner__tag {
  display: block;
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.04em;
  color: #96600f;
  margin-bottom: 3px;
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
