/**
 * 简历诊断接口封装。
 * 契约与《简历诊断模块后端实现教程》保持一致：
 *   GET  /resumes?page=&page_size=      → { items: Resume[], total }
 *   POST /resumes/upload (multipart)    → Resume
 *   GET  /resumes/{id}                  → Resume（轮询解析状态）
 *   POST /resumes/{id}/diagnose {jd_text?} → Report
 *   GET  /resumes/{id}/reports          → { items: Report[], total }
 */
import { http } from './client'

export function listResumes({ page = 1, pageSize = 20 } = {}) {
  return http
    .get('/resumes', { params: { page, page_size: pageSize } })
    .then((response) => response.data)
}

export function uploadResume(file, { onProgress } = {}) {
  const form = new FormData()
  form.append('file', file)
  return http
    .post('/resumes/upload', form, {
      timeout: 60000,
      onUploadProgress: (event) => {
        if (!onProgress || !event.total) return
        onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)))
      },
    })
    .then((response) => response.data)
}

export function getResume(id) {
  return http.get(`/resumes/${id}`).then((response) => response.data)
}

export function reparseResume(id) {
  return http.post(`/resumes/${id}/reparse`).then((response) => response.data)
}

export function diagnoseResume(id, { jdText } = {}) {
  const body = jdText && jdText.trim() ? { jd_text: jdText.trim() } : {}
  // 诊断是同步 LLM 调用，可能持续 20-60s，单独放宽超时
  return http
    .post(`/resumes/${id}/diagnose`, body, { timeout: 180000 })
    .then((response) => response.data)
}

export function listReports(id) {
  return http.get(`/resumes/${id}/reports`).then((response) => response.data)
}
