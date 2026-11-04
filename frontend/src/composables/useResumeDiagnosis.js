import { computed, onScopeDispose, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  diagnoseResume,
  getResume,
  listReports,
  listResumes,
  reparseResume,
  uploadResume,
} from '@/api/resumes'
import { formatFileSize } from '@/utils/format'

const ALLOWED_EXTENSIONS = ['pdf', 'docx']
const MAX_FILE_SIZE = 10 * 1024 * 1024
const PAGE_SIZE = 30
const POLL_INTERVAL = 1500
const POLL_TIMEOUT = 120000

/**
 * 简历诊断页的数据编排：
 * 列表 → 选中简历 → 报告；上传后轮询解析状态；诊断后刷新列表与报告。
 * 组件只负责渲染，所有请求与状态机集中在这里。
 */
export function useResumeDiagnosis() {
  const resumes = ref([])
  const total = ref(0)
  const listLoading = ref(false)
  const listError = ref('')

  const activeResume = ref(null)
  const reports = ref([])
  const reportsLoading = ref(false)
  const pageError = ref('')

  const uploading = ref(false)
  const uploadProgress = ref(0)
  const analyzing = ref(false)
  const reparsing = ref(false)
  const pollExpired = ref(false)

  let pollTimer = null
  let pollStartedAt = 0
  let pollResumeId = null

  const activeReport = computed(() => reports.value[0] || null)
  const isParsing = computed(() => activeResume.value?.parse_status === 'pending')
  const parseFailed = computed(() => activeResume.value?.parse_status === 'failed')
  const canDiagnose = computed(
    () => activeResume.value?.parse_status === 'done' && !analyzing.value && !uploading.value,
  )

  function stopPolling() {
    clearTimeout(pollTimer)
    pollTimer = null
    pollResumeId = null
  }

  function patchActiveResume(patch) {
    if (!activeResume.value) return
    activeResume.value = { ...activeResume.value, ...patch }
  }

  async function loadResumes({ silent = false } = {}) {
    if (!silent) listLoading.value = true
    listError.value = ''
    try {
      const data = await listResumes({ page: 1, pageSize: PAGE_SIZE })
      resumes.value = Array.isArray(data?.items) ? data.items : []
      total.value = Number(data?.total ?? resumes.value.length)

      // 列表是简历状态的权威来源：同步当前选中项，避免上传后状态滞后
      if (activeResume.value) {
        const fresh = resumes.value.find((item) => item.id === activeResume.value.id)
        if (fresh) patchActiveResume(fresh)
      }
      return data
    } catch (error) {
      listError.value = error?.message || '加载历史诊断失败'
      return null
    } finally {
      listLoading.value = false
    }
  }

  async function loadReports(resumeId) {
    reportsLoading.value = true
    pageError.value = ''
    try {
      const data = await listReports(resumeId)
      if (activeResume.value?.id !== resumeId) return
      reports.value = Array.isArray(data?.items) ? data.items : []
    } catch (error) {
      if (activeResume.value?.id !== resumeId) return
      reports.value = []
      pageError.value = error?.message || '加载诊断报告失败'
    } finally {
      reportsLoading.value = false
    }
  }

  function startPolling(resumeId) {
    stopPolling()
    pollResumeId = resumeId
    pollStartedAt = Date.now()
    pollExpired.value = false

    const tick = async () => {
      if (pollResumeId !== resumeId) return
      try {
        const fresh = await getResume(resumeId)
        if (pollResumeId !== resumeId) return
        activeResume.value = fresh
        if (fresh.parse_status !== 'pending') {
          stopPolling()
          await loadResumes({ silent: true })
          if (fresh.parse_status === 'failed') {
            ElMessage.error(fresh.parse_error || '简历解析失败，请重新上传')
          }
          return
        }
      } catch {
        // 轮询期间的网络抖动不打断，超时后由 pollExpired 提示手动刷新
      }

      if (Date.now() - pollStartedAt >= POLL_TIMEOUT) {
        stopPolling()
        pollExpired.value = true
        return
      }
      pollTimer = setTimeout(tick, POLL_INTERVAL)
    }

    pollTimer = setTimeout(tick, 1200)
  }

  async function selectResume(resumeId) {
    const fromList = resumes.value.find((item) => item.id === resumeId)
    stopPolling()
    reports.value = []
    pageError.value = ''
    activeResume.value = fromList ? { ...fromList } : { id: resumeId }

    if (fromList?.parse_status === 'pending') startPolling(resumeId)
    await loadReports(resumeId)
  }

  function validateFile(file) {
    if (!file) return '请选择一份简历'
    const extension = file.name.split('.').pop()?.toLowerCase()
    if (!ALLOWED_EXTENSIONS.includes(extension)) return '只支持 PDF 或 DOCX 格式'
    if (file.size > MAX_FILE_SIZE) return `文件不能超过 ${formatFileSize(MAX_FILE_SIZE)}`
    return ''
  }

  async function uploadFile(file) {
    const message = validateFile(file)
    if (message) {
      ElMessage.warning(message)
      return null
    }

    uploading.value = true
    uploadProgress.value = 0
    pageError.value = ''
    pollExpired.value = false
    try {
      const resume = await uploadResume(file, {
        onProgress: (percent) => {
          uploadProgress.value = percent
        },
      })
      activeResume.value = resume
      reports.value = []
      await loadResumes({ silent: true })
      if (resume.parse_status === 'pending') startPolling(resume.id)
      return resume
    } catch (error) {
      pageError.value = error?.message || '上传失败，请稍后重试'
      ElMessage.error(pageError.value)
      return null
    } finally {
      uploading.value = false
    }
  }

  async function runDiagnosis(jdText) {
    if (!activeResume.value) {
      ElMessage.warning('请先上传并选择一份简历')
      return null
    }
    if (activeResume.value.parse_status !== 'done') {
      ElMessage.warning('简历尚未解析完成，请稍候')
      return null
    }

    analyzing.value = true
    pageError.value = ''
    try {
      const report = await diagnoseResume(activeResume.value.id, { jdText })
      reports.value = [report, ...reports.value.filter((item) => item.id !== report.id)]
      await loadResumes({ silent: true })
      return report
    } catch (error) {
      pageError.value = error?.message || '诊断失败，请稍后重试'
      ElMessage.error(pageError.value)
      return null
    } finally {
      analyzing.value = false
    }
  }

  /** 解析失败/任务中断时复用原文件重试 */
  async function reparseActiveResume() {
    if (!activeResume.value) return null
    reparsing.value = true
    pageError.value = ''
    try {
      const resume = await reparseResume(activeResume.value.id)
      activeResume.value = resume
      reports.value = []
      pollExpired.value = false
      await loadResumes({ silent: true })
      startPolling(resume.id)
      return resume
    } catch (error) {
      pageError.value = error?.message || '重新解析失败'
      ElMessage.error(pageError.value)
      return null
    } finally {
      reparsing.value = false
    }
  }

  /** 解析超时或状态可疑时，手动拉一次最新状态 */
  async function refreshActiveResume() {
    if (!activeResume.value) {
      await loadResumes()
      return
    }
    try {
      const fresh = await getResume(activeResume.value.id)
      activeResume.value = fresh
      await loadResumes({ silent: true })
      if (fresh.parse_status === 'pending') startPolling(fresh.id)
    } catch (error) {
      pageError.value = error?.message || '刷新简历状态失败'
    }
  }

  async function init() {
    const data = await loadResumes()
    const first = data?.items?.[0]
    if (first) await selectResume(first.id)
  }

  async function reload() {
    await loadResumes()
    if (!activeResume.value && resumes.value.length) {
      await selectResume(resumes.value[0].id)
    }
  }

  onScopeDispose(stopPolling)

  return {
    resumes,
    total,
    listLoading,
    listError,
    activeResume,
    reports,
    reportsLoading,
    activeReport,
    pageError,
    uploading,
    uploadProgress,
    analyzing,
    reparsing,
    pollExpired,
    isParsing,
    parseFailed,
    canDiagnose,
    init,
    reload,
    selectResume,
    uploadFile,
    reparseActiveResume,
    runDiagnosis,
    refreshActiveResume,
  }
}
