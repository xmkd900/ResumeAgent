/** 只接受站内路径，防止 ?redirect= 被拿来做开放跳转 */
export function safeRedirect(raw) {
  if (typeof raw !== 'string') return null
  if (!raw.startsWith('/') || raw.startsWith('//')) return null
  if (raw.startsWith('/login') || raw.startsWith('/register')) return null
  return raw
}
