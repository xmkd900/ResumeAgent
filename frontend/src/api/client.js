import axios from 'axios'

const TOKEN_KEY = 'jdagent.token'
const USER_KEY = 'jdagent.user'

export class ApiError extends Error {
  constructor(message, status = 0, payload = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
  }
}

/* ---------------- token 持久化（localStorage，跨标签页共享） ---------------- */

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* 隐私模式下写不进去时降级为内存态，不影响当前会话 */
  }
}

export function clearToken() {
  setToken('')
}

export function getCachedUser() {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setCachedUser(user) {
  try {
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
    else localStorage.removeItem(USER_KEY)
  } catch {
    /* 同上 */
  }
}

/* ---------------- axios 实例 ---------------- */

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 20000,
})

http.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

/** FastAPI 统一错误体 {detail}；422 的 detail 是校验错误数组 */
function normalizeMessage(error) {
  const status = error.response?.status
  const detail = error.response?.data?.detail

  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0]
    const field = Array.isArray(first?.loc) ? first.loc[first.loc.length - 1] : ''
    const msg = String(first?.msg || '').replace(/^Value error,\s*/i, '')
    return field ? `${field}：${msg}` : msg
  }
  if (!error.response) return '无法连接后端服务，请确认服务已启动'
  if (status === 401) return '登录状态已失效，请重新登录'
  if (status === 403) return '没有访问该资源的权限'
  // Vite 代理在后端未启动时也会返回 500，这里给出可操作的提示
  if (status >= 500) return '服务暂时不可用，请确认后端已启动（127.0.0.1:8000）'
  return `请求失败（${status}）`
}

http.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status ?? 0
    const url = error.config?.url || ''
    const isLoginRequest = url.includes('/auth/login')

    // 已登录状态下 token 失效：通知全局清理，避免各页面重复处理
    if (status === 401 && !isLoginRequest && getToken()) {
      window.dispatchEvent(new CustomEvent('auth:unauthorized'))
    }

    return Promise.reject(new ApiError(normalizeMessage(error), status, error.response?.data ?? null))
  },
)
