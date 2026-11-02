/**
 * 鉴权接口封装，契约见 ARCHITECTURE.md 第六节：
 *   POST /auth/register {username, password} → UserOut(201)
 *   POST /auth/login    {username, password} → {access_token, token_type}
 *   GET  /auth/me                            → UserOut
 */
import { http } from './client'
import { mockLogin, mockLogout, mockMe, mockRegister } from './mock'

export const USE_MOCK = String(import.meta.env.VITE_USE_MOCK) === 'true'

export async function register(payload) {
  if (USE_MOCK) return mockRegister(payload)
  const { data } = await http.post('/auth/register', payload)
  return data
}

export async function login(payload) {
  if (USE_MOCK) return mockLogin(payload)
  const { data } = await http.post('/auth/login', payload)
  return data
}

export async function me() {
  if (USE_MOCK) return mockMe()
  const { data } = await http.get('/auth/me')
  return data
}

export function logout() {
  if (USE_MOCK) mockLogout()
}
