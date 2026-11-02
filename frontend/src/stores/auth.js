import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import * as authApi from '@/api/auth'
import { clearToken, getCachedUser, getToken, setCachedUser, setToken } from '@/api/client'

const STATUS = {
  IDLE: 'idle',
  LOADING: 'loading',
  AUTHED: 'authed',
  GUEST: 'guest',
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(getToken())
  const user = ref(getCachedUser())
  const status = ref(token.value ? STATUS.IDLE : STATUS.GUEST)
  const bootstrapped = ref(false)
  const submitting = ref(false)

  const isAuthed = computed(() => status.value === STATUS.AUTHED)
  const isReady = computed(() => status.value !== STATUS.IDLE && status.value !== STATUS.LOADING)
  const username = computed(() => user.value?.username || '')
  const initial = computed(() => (username.value.charAt(0) || 'U').toUpperCase())

  function persistToken(next) {
    token.value = next || ''
    setToken(token.value)
  }

  function persistUser(next) {
    user.value = next
    setCachedUser(next)
  }

  function reset() {
    persistToken('')
    persistUser(null)
    status.value = STATUS.GUEST
    authApi.logout()
  }

  async function fetchMe() {
    const data = await authApi.me()
    persistUser(data)
    status.value = STATUS.AUTHED
    return data
  }

  /** 登录：拿 token → 立刻校验身份，避免带着无效 token 进工作台 */
  async function login(credentials) {
    submitting.value = true
    try {
      const data = await authApi.login(credentials)
      persistToken(data.access_token)
      await fetchMe()
      return user.value
    } catch (error) {
      persistToken('')
      persistUser(null)
      status.value = STATUS.GUEST
      throw error
    } finally {
      submitting.value = false
    }
  }

  /** 注册后自动登录（后端 register 只返回用户，不返回 token） */
  async function register(credentials) {
    submitting.value = true
    try {
      await authApi.register({ username: credentials.username, password: credentials.password })
    } finally {
      submitting.value = false
    }
    return login({ username: credentials.username, password: credentials.password })
  }

  /** 应用启动时的鉴权自检：有 token 就走 /auth/me 校验，不能只信本地标记 */
  async function bootstrap() {
    if (bootstrapped.value) return status.value
    if (!token.value) {
      status.value = STATUS.GUEST
      bootstrapped.value = true
      return status.value
    }
    status.value = STATUS.LOADING
    try {
      await fetchMe()
    } catch (error) {
      if (error?.status === 401) {
        reset()
      } else {
        // 网络异常：保留 token 等用户主动重试，但不放行受保护页面
        status.value = STATUS.GUEST
      }
    } finally {
      bootstrapped.value = true
    }
    return status.value
  }

  function logout() {
    reset()
    bootstrapped.value = true
  }

  /** 全局 401 回调：token 被后端拒绝时统一登出 */
  function handleUnauthorized() {
    if (!token.value) return false
    reset()
    return true
  }

  return {
    token,
    user,
    status,
    bootstrapped,
    submitting,
    isAuthed,
    isReady,
    username,
    initial,
    login,
    register,
    fetchMe,
    bootstrap,
    logout,
    reset,
    handleUnauthorized,
  }
})
