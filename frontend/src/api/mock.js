/**
 * 演示模式：后端未启动时用 localStorage 模拟 /auth 三个端点，
 * 保证登录 / 注册 / 鉴权校验的完整链路可点击验证。
 * 关闭方式：.env.development 中 VITE_USE_MOCK=false
 */
import { ApiError, getToken } from './client'

const USERS_KEY = 'jdagent.mock.users'
const delay = (ms = 420) => new Promise((resolve) => setTimeout(resolve, ms))

function readUsers() {
  try {
    const raw = localStorage.getItem(USERS_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function writeUsers(users) {
  localStorage.setItem(USERS_KEY, JSON.stringify(users))
}

/** 首次使用时内置一个演示账号，便于直接登录 */
function ensureSeed() {
  const users = readUsers()
  if (users.length) return users
  const seeded = [
    {
      id: 1,
      username: 'demo',
      password: 'demo1234',
      created_at: new Date('2026-09-01T09:00:00+08:00').toISOString(),
    },
  ]
  writeUsers(seeded)
  return seeded
}

export async function mockRegister({ username, password }) {
  await delay()
  if (!/^[a-zA-Z0-9_]{3,32}$/.test(username)) {
    throw new ApiError('用户名需为 3-32 位字母、数字或下划线', 422)
  }
  if (password.length < 4 || password.length > 10) {
    throw new ApiError('密码长度需为 4-10 位', 422)
  }
  const users = ensureSeed()
  if (users.some((u) => u.username === username)) {
    throw new ApiError('用户名已被占用', 409)
  }
  const user = {
    id: users.reduce((max, u) => Math.max(max, u.id), 0) + 1,
    username,
    password,
    created_at: new Date().toISOString(),
  }
  writeUsers([...users, user])
  return { id: user.id, username: user.username, created_at: user.created_at }
}

export async function mockLogin({ username, password }) {
  await delay()
  const user = ensureSeed().find((u) => u.username === username)
  if (!user || user.password !== password) {
    throw new ApiError('用户名或密码错误', 401)
  }
  return { access_token: `mock.${username}`, token_type: 'bearer' }
}

export async function mockMe() {
  await delay(240)
  // 与真实后端一致：身份只从 token 解析，token 无效即 401
  const token = getToken()
  const username = token.startsWith('mock.') ? token.slice('mock.'.length) : ''
  const user = username ? ensureSeed().find((u) => u.username === username) : null
  if (!user) throw new ApiError('登录状态已失效，请重新登录', 401)
  return { id: user.id, username: user.username, created_at: user.created_at }
}

export function mockLogout() {
  // token 由调用方清除；这里只保留函数占位，便于与真实模式接口对齐
}
