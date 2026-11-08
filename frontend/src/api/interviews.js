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
import { http } from './client'

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
