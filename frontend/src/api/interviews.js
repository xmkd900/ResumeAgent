/**
 * 面试会话 API。
 *
 * 契约（ARCHITECTURE.md 第六节）：
 *   POST /interviews                     建会话：返回开场问题与预算
 *   GET  /interviews/{id}                会话快照：turns + 当前题
 *   POST /interviews/{id}/answer         判卷 + 出下一题
 *   POST /interviews/{id}/pause|resume   用户随时暂停/继续
 *   POST /interviews/{id}/finish         结束并生成评估
 *   POST /interviews/{id}/abort          中止（不计入评估）
 */
import { getToken, http } from './client'

export const interviewApi = {
  createInterview(payload) {
    // 建会话要提炼 JD 能力项并写开场，给足 60s
    return http
      .post('/interviews', payload, { timeout: 60000 })
      .then((response) => response.data)
  },
  getInterview(id) {
    return http.get(`/interviews/${id}`).then((response) => response.data)
  },
  submitAnswer(id, answer) {
    // 判卷 + 面试官决策跨 2-3 次模型调用
    return http
      .post(`/interviews/${id}/answer`, { answer }, { timeout: 180000 })
      .then((response) => response.data)
  },
  finishInterview(id) {
    return http
      .post(`/interviews/${id}/finish`, null, { timeout: 120000 })
      .then((response) => response.data)
  },
  pauseInterview(id) {
    return http.post(`/interviews/${id}/pause`).then((response) => response.data)
  },
  resumeInterview(id) {
    return http.post(`/interviews/${id}/resume`).then((response) => response.data)
  },
  abortInterview(id) {
    return http.post(`/interviews/${id}/abort`).then((response) => response.data)
  },
  listInterviews(params = {}) {
    return http.get('/interviews', { params }).then((response) => response.data)
  },
}

/**
 * 流式提交回答（SSE）：逐节点推送进度，最后返回与 /answer 相同结构的结果。
 *
 * onEvent({ type: 'stage', node, status, detail }) 用于展示"正在判卷/检索"。
 */
export async function streamAnswer(id, answer, { onEvent, signal } = {}) {
  const base = import.meta.env.VITE_API_BASE_URL || '/api/v1'
  const token = getToken()
  const response = await fetch(`${base}/interviews/${id}/answer/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ answer }),
    signal,
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    const message =
      typeof payload.detail === 'string' ? payload.detail : `提交失败（${response.status}）`
    throw new Error(message)
  }
  if (!response.body) throw new Error('当前浏览器不支持流式响应，请升级浏览器')

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let result = null

  function handleFrame(frame) {
    let event = 'message'
    const dataLines = []
    for (const line of frame.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
    }
    if (!dataLines.length) return

    const payload = JSON.parse(dataLines.join('\n'))
    if (event === 'stage') {
      onEvent?.({ type: 'stage', ...payload })
    } else if (event === 'result') {
      result = payload
    } else if (event === 'error') {
      throw new Error(payload.detail || '面试服务暂时不可用，请稍后重试')
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, '\n')
    let index = buffer.indexOf('\n\n')
    while (index !== -1) {
      const frame = buffer.slice(0, index)
      buffer = buffer.slice(index + 2)
      if (frame.trim()) handleFrame(frame)
      index = buffer.indexOf('\n\n')
    }
  }

  if (!result) throw new Error('流式响应提前结束，请重试')
  return result
}
