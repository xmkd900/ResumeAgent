import { computed, nextTick, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { interviewApi, streamAnswer } from '@/api/interviews'
import { listResumes } from '@/api/resumes'
import { DIMENSION_META } from '@/constants'

export const INTERVIEW_POSITIONS = ['后端开发', '前端开发', 'Agent 开发']

const STAGE_LABELS = {
  judge: { start: '正在判卷…', done: '判卷完成，正在决定下一题…' },
  director: { start: '正在决定下一题…', done: '方向已定，正在组织问题…' },
  search: { start: '正在检索题库…', done: '已找到候选题，正在挑选…' },
  compose: { start: '正在挑选最合适的一道…', done: '正在整理问法…' },
  persist: { start: '正在整理问题…', done: '正在准备下一题…' },
  finish: { start: '正在收尾评估…', done: '评估完成' },
}

function stageLabel(event) {
  const entry = STAGE_LABELS[event.node]
  return (entry && entry[event.status]) || '面试官正在思考…'
}

const DEFAULT_SUMMARY = {
  score: 0,
  headline: '本场面试已完成',
  description: '',
  stats: [],
  strengths: [],
  improvements: [],
}

function dimensionRows(raw) {
  const source = (raw && raw.dimensions) || {}
  return Object.keys(DIMENSION_META)
    .filter((key) => key !== 'coverage' && source[key] !== undefined)
    .map((key) => ({
      key,
      label: DIMENSION_META[key].label,
      max: DIMENSION_META[key].max,
      value: Number(source[key]) || 0,
      percent: Math.round(((Number(source[key]) || 0) / DIMENSION_META[key].max) * 100),
    }))
}

function normalizeJudgement(raw) {
  if (!raw) return null
  return {
    verdict: raw.verdict || 'partial',
    score: Number(raw.score) || 0,
    hits: raw.hit_points || raw.hits || [],
    misses: raw.missing_points || raw.misses || [],
    feedback: raw.feedback || '',
    hint: raw.followup_hint || '',
    depth: raw.depth || '',
    dimensions: dimensionRows(raw),
    hedging: Array.isArray(raw.hedging) ? raw.hedging : [],
    // 旧记录没有证据字段，保持空数组即可
    evidence: Array.isArray(raw.evidence) ? raw.evidence : [],
  }
}

function normalizeQuestion(raw) {
  if (!raw) return null
  return {
    turnId: raw.turn_id,
    index: Number(raw.turn_index) || 1,
    depth: Number(raw.depth) || 0,
    content: raw.content || '',
    competency: raw.competency || '综合',
    source: raw.source || 'generated',
    action: raw.action || 'ask',
  }
}

/** 把 turn 列表摊平成聊天气泡：一问一答，判卷挂在回答上。 */
function buildMessages(turns) {
  const list = []
  for (const turn of turns || []) {
    list.push({
      id: `q-${turn.id}`,
      role: 'interviewer',
      content: turn.question,
      meta: turn.competency,
      judgement: null,
    })
    if (turn.answer) {
      list.push({
        id: `a-${turn.id}`,
        role: 'candidate',
        content: turn.answer,
        judgement: normalizeJudgement(turn.judgement),
      })
    }
  }
  return list
}

function normalizeEvaluation(raw, session) {
  if (!raw) return null
  return {
    score: Number(raw.score) || 0,
    decision: raw.decision || '',
    headline: raw.headline || DEFAULT_SUMMARY.headline,
    description: raw.description || session?.summary || '',
    stats: Array.isArray(raw.stats) ? raw.stats : [],
    strengths: Array.isArray(raw.strengths) ? raw.strengths : [],
    improvements: Array.isArray(raw.improvements) ? raw.improvements : [],
    dimensions: Array.isArray(raw.dimensions) ? raw.dimensions : [],
  }
}

export function useInterviewSession() {
  const stage = ref('setup') // setup | ongoing | summary
  const setup = reactive({
    position: INTERVIEW_POSITIONS[0],
    resumeId: null,
    jdText: '',
    maxQuestions: 10,
  })

  const resumes = ref([])
  const resumesLoading = ref(false)
  const resumeError = ref('')
  const session = ref(null)
  const currentQuestion = ref(null)
  const messages = ref([])
  const evaluation = ref(null)
  const covered = ref([])
  const chatEl = ref(null)
  const starting = ref(false)
  const answering = ref(false)
  const finishing = ref(false)
  const pausing = ref(false)
  const answerStage = ref('')
  const error = ref('')

  const asked = computed(() => Number(session.value?.asked_count) || 0)
  const maxQuestions = computed(() => Number(session.value?.max_questions) || setup.maxQuestions)
  const paused = computed(() => session.value?.status === 'paused')
  const depth = computed(() => currentQuestion.value?.depth || 0)
  const topic = computed(() => currentQuestion.value?.competency || '准备中')
  const progress = computed(() => {
    if (!maxQuestions.value || !asked.value) return 0
    return Math.min(100, Math.round((asked.value / maxQuestions.value) * 100))
  })
  const canStart = computed(() => Boolean(setup.position) && !starting.value)
  const selectedResume = computed(
    () => resumes.value.find((item) => item.id === setup.resumeId) || null,
  )
  // 简历要点决定面试能不能深挖项目；没有就提示会先自动抽取
  const claimHint = computed(() => {
    const resume = selectedResume.value
    if (!resume) return ''
    const count = Number(resume.claim_count) || 0
    return count > 0
      ? `已提取 ${count} 条面试要点，面试官会据此深挖项目`
      : '这份简历还没有面试要点，开始时会先自动提取（约 5-10 秒）'
  })
  const summary = computed(() => evaluation.value || DEFAULT_SUMMARY)

  function scrollChat() {
    nextTick(() => {
      if (!chatEl.value) return
      chatEl.value.scrollTop = chatEl.value.scrollHeight
      // 反馈块和新气泡可能在同一帧插入，再补一次对齐到底部
      requestAnimationFrame(() => {
        if (chatEl.value) chatEl.value.scrollTop = chatEl.value.scrollHeight
      })
    })
  }

  // 新消息落地后统一滚动，避免"最后一句被挡住半截"
  watch(
    () => messages.value.length,
    () => scrollChat(),
    { flush: 'post' },
  )

  function applyDetail(data) {
    session.value = data
    currentQuestion.value = normalizeQuestion(data.current_question)
    messages.value = buildMessages(data.turns)
    covered.value = data.covered_competencies || []
  }

  async function loadResumes() {
    resumesLoading.value = true
    resumeError.value = ''
    try {
      const data = await listResumes({ page: 1, pageSize: 50 })
      resumes.value = (data.items || []).filter((item) => item.parse_status === 'done')
      if (!setup.resumeId && resumes.value.length) {
        setup.resumeId = resumes.value[0].id
      }
    } catch (err) {
      resumeError.value = err?.message || '简历列表加载失败，可稍后重试'
    } finally {
      resumesLoading.value = false
    }
  }

  async function startInterview() {
    if (!setup.position || starting.value) return false
    starting.value = true
    error.value = ''
    try {
      const data = await interviewApi.createInterview({
        position: setup.position,
        resume_id: setup.resumeId || undefined,
        jd_text: setup.jdText.trim() || undefined,
        max_questions: setup.maxQuestions,
      })
      evaluation.value = null
      covered.value = []
      applyDetail(data)
      stage.value = 'ongoing'
      scrollChat()
      if (Array.isArray(data.warnings) && data.warnings.length) {
        ElMessage.warning(data.warnings[0])
      }
      return true
    } catch (err) {
      error.value = err?.message || '面试创建失败，请稍后重试'
      return false
    } finally {
      starting.value = false
    }
  }

  async function finishSession() {
    if (!session.value || finishing.value) return false
    finishing.value = true
    error.value = ''
    try {
      const data = await interviewApi.finishInterview(session.value.id)
      evaluation.value = normalizeEvaluation(data.evaluation, data)
      session.value = { ...session.value, ...data }
      currentQuestion.value = null
      stage.value = 'summary'
      return true
    } catch (err) {
      error.value = err?.message || '评估生成失败，请稍后重试'
      return false
    } finally {
      finishing.value = false
    }
  }

  async function submitAnswer(text) {
    const content = String(text || '').trim()
    if (!content || !session.value || answering.value) return false

    answering.value = true
    error.value = ''
    const tempId = `temp-${Date.now()}`
    messages.value.push({ id: tempId, role: 'candidate', content, judgement: null })

    try {
      const result = await streamAnswer(session.value.id, content, {
        onEvent: (event) => {
          if (event.type === 'stage') answerStage.value = stageLabel(event)
        },
      })
      const message = messages.value.find((item) => item.id === tempId)
      if (message) message.judgement = normalizeJudgement(result.judgement)

      if (result.next_question) {
        const next = normalizeQuestion(result.next_question)
        currentQuestion.value = next
        messages.value.push({
          id: `q-${next.turnId || Date.now()}`,
          role: 'interviewer',
          content: next.content,
          meta: next.competency,
          judgement: null,
        })
        session.value = {
          ...session.value,
          asked_count: result.asked_count,
          max_questions: result.max_questions,
        }
        scrollChat()
        return true
      }

      if (result.finished) {
        currentQuestion.value = null
        await finishSession()
      }
      return true
    } catch (err) {
      messages.value = messages.value.filter((item) => item.id !== tempId)
      error.value = err?.message || '回答提交失败，请稍后重试'
      return false
    } finally {
      answering.value = false
      answerStage.value = ''
    }
  }

  async function pauseInterview() {
    if (!session.value || pausing.value) return false
    pausing.value = true
    error.value = ''
    try {
      const data = await interviewApi.pauseInterview(session.value.id)
      // 暂停时后端不再返回 current_question；保留当前题展示，避免顶部能力项闪回"准备中"
      session.value = { ...session.value, ...data }
      return true
    } catch (err) {
      error.value = err?.message || '暂停失败，请稍后重试'
      return false
    } finally {
      pausing.value = false
    }
  }

  async function resumeInterview() {
    if (!session.value || pausing.value) return false
    pausing.value = true
    error.value = ''
    try {
      const data = await interviewApi.resumeInterview(session.value.id)
      applyDetail(data)
      return true
    } catch (err) {
      error.value = err?.message || '继续失败，请稍后重试'
      return false
    } finally {
      pausing.value = false
    }
  }

  async function restartInterview() {
    if (session.value?.status === 'ongoing' || session.value?.status === 'paused') {
      try {
        await interviewApi.abortInterview(session.value.id)
      } catch {
        // 中止失败不阻塞重新开始
      }
    }
    stage.value = 'setup'
    session.value = null
    currentQuestion.value = null
    messages.value = []
    evaluation.value = null
    covered.value = []
    error.value = ''
    setup.jdText = ''
  }

  return {
    positions: INTERVIEW_POSITIONS,
    setup,
    resumes,
    resumesLoading,
    resumeError,
    stage,
    session,
    currentQuestion,
    messages,
    evaluation,
    summary,
    covered,
    chatEl,
    starting,
    answering,
    finishing,
    pausing,
    paused,
    answerStage,
    error,
    asked,
    maxQuestions,
    depth,
    topic,
    progress,
    canStart,
    selectedResume,
    claimHint,
    loadResumes,
    startInterview,
    submitAnswer,
    pauseInterview,
    resumeInterview,
    finishSession,
    restartInterview,
  }
}
