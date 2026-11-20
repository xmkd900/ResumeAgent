/**
 * 成长闭环 API。
 *
 * 契约（ARCHITECTURE.md 第六节）：
 *   GET  /weak-points                     薄弱点列表 + 概览统计
 *   GET  /weak-points/{id}/exercises       练习视图：讲解（带来源）+ 推荐练习
 *   POST /weak-points/{id}/practice        提交复述：判卷 + 更新掌握度
 *   POST /weak-points/{id}/resolve         标记已掌握
 */
import { http } from './client'

export const growthApi = {
  getQueue() {
    return http.get('/weak-points/queue').then((response) => response.data)
  },
  getGapCard(id) {
    return http.get(`/weak-points/${id}/gap`).then((response) => response.data)
  },
  submitFix(id, answer) {
    return http
      .post(`/weak-points/${id}/fix`, { answer }, { timeout: 60000 })
      .then((response) => response.data)
  },
  submitReview(id, { answer, questionId = null }) {
    return http
      .post(
        `/weak-points/${id}/review`,
        { answer, question_id: questionId },
        { timeout: 60000 },
      )
      .then((response) => response.data)
  },
  listWeakPoints(params = {}) {
    return http
      .get('/weak-points', { params })
      .then((response) => response.data)
  },
  getExercises(id, withContent = true) {
    // 讲解由模型基于题库资料生成，给足 30s；列表预取传 false 不烧模型
    return http
      .get(`/weak-points/${id}/exercises`, {
        params: { with_content: withContent },
        timeout: 30000,
      })
      .then((response) => response.data)
  },
  submitPractice(id, { answer, questionId = null }) {
    return http
      .post(
        `/weak-points/${id}/practice`,
        { answer, question_id: questionId },
        { timeout: 60000 },
      )
      .then((response) => response.data)
  },
  resolveWeakPoint(id) {
    return http.post(`/weak-points/${id}/resolve`).then((response) => response.data)
  },
}
