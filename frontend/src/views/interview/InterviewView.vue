<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight, Microphone, Promotion, VideoPause, VideoPlay } from '@element-plus/icons-vue'

import PageHeader from '@/components/PageHeader.vue'
import ScoreRing from '@/components/ScoreRing.vue'
import SectionCard from '@/components/SectionCard.vue'
import { VERDICT_META } from '@/constants'
import { useInterviewSession } from '@/composables/useInterviewSession'
import { useSpeechInput } from '@/composables/useSpeechInput'

const router = useRouter()
const answer = ref('')

const {
  positions,
  setup,
  resumes,
  resumesLoading,
  resumeError,
  stage,
  session,
  currentQuestion,
  messages,
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
} = useInterviewSession()

const BUDGET_OPTIONS = [6, 8, 10, 12, 16]

// 语音输入：识别结果直接追加到输入框，不覆盖已经打好的字
const {
  supported: speechSupported,
  listening,
  interim: speechInterim,
  error: speechError,
  toggle: toggleSpeech,
  stop: stopSpeech,
} = useSpeechInput({ onFinal: appendSpeech })

function appendSpeech(text) {
  const current = answer.value.trim()
  answer.value = current ? `${current} ${text}` : text
}

watch(paused, (value) => {
  if (value) stopSpeech()
})
watch(stage, (value) => {
  if (value !== 'ongoing') stopSpeech()
})
watch(speechError, (value) => {
  if (value) ElMessage.warning(value)
})

let composing = false

function handleCompositionStart() {
  composing = true
}

function handleCompositionEnd() {
  composing = false
}

function handleKeydown(event) {
  if (event.key !== 'Enter') return
  // 中文输入法选词时的 Enter 不能触发提交
  if (event.isComposing || composing || event.shiftKey) return
  event.preventDefault()
  handleSubmit()
}

onMounted(loadResumes)

async function handleStart() {
  const ok = await startInterview()
  if (ok) ElMessage.success('面试已开始')
}

async function handleSubmit() {
  if (answering.value || paused.value) return
  stopSpeech()
  const text = answer.value.trim()
  if (!text) {
    ElMessage.warning('先写下你的回答')
    return
  }
  const ok = await submitAnswer(text)
  if (ok) answer.value = ''
}

async function handleFinish() {
  if (!session.value || finishing.value) return
  try {
    await ElMessageBox.confirm(
      '结束后会生成本场评估摘要。确定现在结束吗？',
      '结束面试',
      {
        confirmButtonText: '结束并查看评估',
        cancelButtonText: '继续面试',
        type: 'info',
        customClass: 'interview-confirm',
      },
    )
  } catch {
    return
  }
  const ok = await finishSession()
  if (ok) window.scrollTo({ top: 0, behavior: 'smooth' })
}

async function handlePause() {
  const ok = paused.value ? await resumeInterview() : await pauseInterview()
  if (ok) ElMessage.info(paused.value ? '面试已继续' : '面试已暂停，随时可以回来')
}

async function handleRestart() {
  if (stage.value === 'ongoing') {
    try {
      await ElMessageBox.confirm('重新开始会中止当前面试，已产生的回答不会计入本场评估。', '重新开始', {
        confirmButtonText: '重新开始',
        cancelButtonText: '继续面试',
        type: 'warning',
      })
    } catch {
      return
    }
  }
  await restartInterview()
}

function goGrowth() {
  router.push('/growth')
}

function clearError() {
  error.value = ''
}

function verdictLabel(verdict) {
  return VERDICT_META[verdict]?.label || verdict
}
</script>

<template>
  <div class="page">
    <PageHeader
      eyebrow="Mock Interview"
      title="模拟面试"
      subtitle="面试官拿到你的简历和 JD 后，按你的回答实时决定问什么、追多深；随时可以暂停。"
    >
      <template #actions>
        <span v-if="stage === 'ongoing' && !paused" class="pill pill--accent">
          <span class="dot dot--live" />进行中
        </span>
        <span v-if="stage === 'ongoing' && paused" class="pill pill--soft">已暂停</span>
        <el-button v-if="stage !== 'setup'" @click="handleRestart">重新开始</el-button>
      </template>
    </PageHeader>

    <el-alert
      v-if="error"
      class="page__error"
      :title="error"
      type="error"
      show-icon
      @close="clearError"
    />

    <!-- ================= 开始面试 ================= -->
    <div v-if="stage === 'setup'" class="setup">
      <SectionCard class="setup__main" title="开始一场模拟面试">
        <div class="setup__body">
          <div class="setup__field">
            <label class="setup__label">目标岗位</label>
            <el-select v-model="setup.position" size="large" placeholder="选择岗位" class="setup__control">
              <el-option v-for="p in positions" :key="p" :label="p" :value="p" />
            </el-select>
            <p class="setup__hint">决定题库的领域范围，也决定面试官默认考哪些能力。</p>
          </div>

          <div class="setup__field">
            <label class="setup__label">关联简历（推荐）</label>
            <el-select
              v-model="setup.resumeId"
              size="large"
              clearable
              :loading="resumesLoading"
              placeholder="选择一份已解析简历"
              class="setup__control"
            >
              <el-option
                v-for="resume in resumes"
                :key="resume.id"
                :label="resume.filename"
                :value="resume.id"
              />
            </el-select>
            <p class="setup__hint">有简历时从你的项目问起；没有则按岗位与 JD 出题。</p>
            <p
              v-if="claimHint"
              class="setup__hint"
              :class="{ 'setup__hint--warn': !selectedResume?.claim_count }"
            >
              {{ claimHint }}
            </p>
            <p v-if="resumeError" class="setup__hint setup__hint--warn">{{ resumeError }}</p>
          </div>

          <div class="setup__field">
            <label class="setup__label">目标 JD（可选）</label>
            <el-input
              v-model="setup.jdText"
              type="textarea"
              :rows="4"
              maxlength="2000"
              show-word-limit
              resize="none"
              placeholder="粘贴岗位 JD，面试官会先提炼能力要求再决定考什么…"
            />
            <p class="setup__hint">不填则按岗位通用能力与简历出题。</p>
          </div>

          <div class="setup__field">
            <label class="setup__label">题目上限</label>
            <el-select v-model="setup.maxQuestions" size="large" class="setup__control">
              <el-option v-for="n in BUDGET_OPTIONS" :key="n" :label="`最多 ${n} 题`" :value="n" />
            </el-select>
            <p class="setup__hint">只是上限。问透了面试官会提前收尾，不会为凑数硬问。</p>
          </div>

          <div class="setup__preview">
            <div class="setup__preview-head">
              <span>本场怎么进行</span>
              <span class="pill pill--soft">按回答实时决定</span>
            </div>
            <ul class="setup__plan">
              <li>
                <span class="num">01</span>
                开场
                <span class="setup__plan-meta">自我介绍 / 讲一段经历</span>
              </li>
              <li>
                <span class="num">02</span>
                简历深挖
                <span class="setup__plan-meta">项目、取舍、指标来源</span>
              </li>
              <li>
                <span class="num">03</span>
                能力覆盖
                <span class="setup__plan-meta">JD 缺口，从题库取题</span>
              </li>
              <li>
                <span class="num">04</span>
                收尾
                <span class="setup__plan-meta">问透即停，不凑题数</span>
              </li>
            </ul>
            <p class="setup__hint setup__hint--foot">
              题目不会提前排好：你答到哪、答得怎么样，决定下一句问什么。
            </p>
          </div>

          <el-button
            type="primary"
            size="large"
            class="setup__cta"
            :icon="VideoPlay"
            :loading="starting"
            :disabled="!canStart"
            @click="handleStart"
          >
            {{ starting ? '正在准备第一题…' : '开始面试' }}
          </el-button>
        </div>
      </SectionCard>

      <SectionCard class="setup__side" title="本场机制" subtitle="面试官自主决策，规则只做兜底">
        <ol class="mech">
          <li>
            <span class="mech__idx">1</span>
            <div><p>出题</p><small>读简历与 JD，决定开场问什么</small></div>
          </li>
          <li>
            <span class="mech__idx">2</span>
            <div><p>判卷</p><small>按要点给出分数、命中与缺口</small></div>
          </li>
          <li>
            <span class="mech__idx">3</span>
            <div><p>追问</p><small>答得浅就往下追，答得好就换方向</small></div>
          </li>
          <li>
            <span class="mech__idx">4</span>
            <div><p>收束</p><small>问透或到上限即收尾，生成复盘</small></div>
          </li>
        </ol>

        <div class="mech__note">
          <span class="mech__note-title">沉浸优先</span>
          <p>面试页不展示题目来源、判卷 rubric 与决策过程——真实面试官不会给你看草稿纸。</p>
        </div>

        <div class="mech__meta">
          <div><span>预计时长</span><strong>20-30 分钟</strong></div>
          <div><span>题目数量</span><strong>由面试官决定</strong></div>
          <div><span>追问深度</span><strong>视回答而定</strong></div>
        </div>
      </SectionCard>
    </div>

    <!-- ================= 面试进行中 ================= -->
    <div v-else-if="stage === 'ongoing'" class="session">
      <SectionCard class="session__bar" :padded="true">
        <div class="bar">
          <div class="bar__main">
            <div class="bar__title">
              <h2>{{ session?.position || setup.position }}</h2>
              <span class="pill pill--primary">{{ topic }}</span>
            </div>
            <div class="bar__meta">
              <span>第 <strong class="num">{{ asked }}</strong> 题</span>
              <span class="bar__sep" />
              <span>已覆盖 <strong class="num">{{ covered.length }}</strong> 项能力</span>
              <template v-if="depth > 0">
                <span class="bar__sep" />
                <span class="bar__depth">
                  追问 · 第 <strong class="num">{{ depth }}</strong> 层
                </span>
              </template>
            </div>
          </div>
          <div class="bar__actions">
            <el-button
              :icon="paused ? VideoPlay : VideoPause"
              :loading="pausing"
              :disabled="finishing"
              @click="handlePause"
            >
              {{ paused ? '继续面试' : '暂停' }}
            </el-button>
            <el-button
              class="bar__end"
              :loading="finishing"
              :disabled="answering || paused"
              @click="handleFinish"
            >
              结束面试
            </el-button>
          </div>
        </div>
        <div class="bar__progress">
          <span :style="{ width: `${progress}%` }" />
        </div>
      </SectionCard>

      <div class="chat-wrap">
        <div ref="chatEl" class="chat">
          <template v-for="msg in messages" :key="msg.id">
            <div class="msg" :class="`msg--${msg.role}`">
              <span class="msg__avatar" :class="`msg__avatar--${msg.role}`">
                {{ msg.role === 'interviewer' ? '面' : '我' }}
              </span>
              <div class="msg__body">
                <p class="msg__who">
                  {{ msg.role === 'interviewer' ? '面试官' : '我的回答' }}
                  <span v-if="msg.meta" class="msg__tag">{{ msg.meta }}</span>
                </p>
                <div class="msg__bubble">{{ msg.content }}</div>
              </div>
            </div>

            <div v-if="msg.judgement" class="feedback">
              <div class="feedback__head">
                <span class="pill" :class="`verdict verdict--${msg.judgement.verdict}`">
                  {{ verdictLabel(msg.judgement.verdict) }}
                </span>
                <span class="feedback__label">本轮反馈</span>
              </div>
              <div class="feedback__cols">
                <div class="feedback__col">
                  <p class="feedback__title feedback__title--hit">命中要点</p>
                  <ul>
                    <li v-for="hit in msg.judgement.hits" :key="hit">
                      <span class="tick tick--hit">✓</span>{{ hit }}
                    </li>
                    <li v-if="!msg.judgement.hits.length" class="feedback__empty">暂无明确命中</li>
                  </ul>
                </div>
                <div class="feedback__col">
                  <p class="feedback__title feedback__title--miss">待补要点</p>
                  <ul>
                    <li v-for="miss in msg.judgement.misses" :key="miss">
                      <span class="tick tick--miss">–</span>{{ miss }}
                    </li>
                    <li v-if="!msg.judgement.misses.length" class="feedback__empty">本题要点已覆盖</li>
                  </ul>
                </div>
              </div>
              <p v-if="msg.judgement.feedback" class="feedback__note">{{ msg.judgement.feedback }}</p>
            </div>
          </template>

          <div v-if="!currentQuestion" class="session__wait">
            <span class="dot dot--live" />正在生成下一题…
          </div>
        </div>

        <div class="composer">
          <div v-if="answering" class="composer__stage">
            <span class="dot dot--live" />
            <span>{{ answerStage || '面试官正在思考…' }}</span>
          </div>
          <div v-if="paused" class="composer__paused">
            面试已暂停 · 点上方「继续面试」接着答
          </div>
          <el-input
            v-model="answer"
            type="textarea"
            :rows="3"
            maxlength="4000"
            show-word-limit
            resize="none"
            :disabled="answering || finishing || paused"
            placeholder="用自己的话回答，尽量给出因果、取舍与验证方式…"
            @keydown="handleKeydown"
            @compositionstart="handleCompositionStart"
            @compositionend="handleCompositionEnd"
          />
          <div v-if="listening" class="composer__voice">
            <span class="dot dot--live" />
            <span>正在聆听，说完停顿一下会自动写入</span>
            <em v-if="speechInterim">{{ speechInterim }}</em>
          </div>
          <div class="composer__foot">
            <span class="composer__hint">Enter 提交 · Shift + Enter 换行 · 语音识别为普通话</span>
            <div class="composer__actions">
              <el-tooltip
                :content="speechSupported ? '语音输入（普通话）' : '当前浏览器不支持语音输入，建议用 Chrome / Edge'"
                placement="top"
              >
                <span>
                  <el-button
                    v-if="speechSupported"
                    :type="listening ? 'danger' : 'default'"
                    :icon="Microphone"
                    :disabled="answering || finishing || paused"
                    @click="toggleSpeech"
                  >
                    {{ listening ? '停止' : '语音' }}
                  </el-button>
                </span>
              </el-tooltip>
              <el-button
                type="primary"
                :icon="Promotion"
                :loading="answering"
                :disabled="answering || finishing || !currentQuestion"
                @click="handleSubmit"
              >
                提交回答
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ================= 整场评估 ================= -->
    <div v-else class="summary">
      <SectionCard class="summary__main">
        <div class="summary__head">
          <ScoreRing :score="summary.score" :size="124" label="本场表现" suffix="/ 100" />
          <div class="summary__copy">
            <p class="eyebrow">Session Summary</p>
            <h2>{{ summary.headline }}</h2>
            <p class="summary__desc">{{ summary.description }}</p>
            <div class="summary__stats">
              <div v-for="stat in summary.stats" :key="stat.label" class="summary__stat">
                <span class="summary__stat-label">{{ stat.label }}</span>
                <span class="summary__stat-value num">
                  {{ stat.value }}<small v-if="stat.suffix">{{ stat.suffix }}</small>
                </span>
              </div>
            </div>
          </div>
        </div>
      </SectionCard>

      <div class="summary__grid">
        <SectionCard title="亮点" subtitle="这场面试里保持住的部分">
          <ul v-if="summary.strengths.length" class="tags">
            <li v-for="item in summary.strengths" :key="item" class="tag tag--good">
              <span class="tag__dot" />{{ item }}
            </li>
          </ul>
          <p v-else class="summary__empty">本场还没有足够稳定的亮点，再面一次看看。</p>
        </SectionCard>

        <SectionCard title="待加强" subtitle="本场判卷中需要补强的部分">
          <ul v-if="summary.improvements.length" class="tags">
            <li v-for="item in summary.improvements" :key="item" class="tag tag--warn">
              <span class="tag__dot" />{{ item }}
            </li>
          </ul>
          <p v-else class="summary__empty">没有明显短板，保持当前表达节奏。</p>
        </SectionCard>
      </div>

      <SectionCard class="summary__next">
        <div class="next">
          <div>
            <p class="next__title">
              下一步：针对这 {{ summary.improvements.length || 0 }} 个待加强项做专项练习
            </p>
            <p class="next__desc">成长闭环接入后，会按严重度排序并推荐对应练习。</p>
          </div>
          <el-button type="primary" :icon="ArrowRight" @click="goGrowth">进入成长闭环</el-button>
        </div>
      </SectionCard>
    </div>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
}

/* ---------------- 开始页 ---------------- */
.setup {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

.setup__body {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.setup__field {
  display: flex;
  flex-direction: column;
}

.setup__label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink-2);
  margin-bottom: 7px;
}

.setup__control {
  width: 100%;
}

.setup__hint {
  margin-top: 6px;
  font-size: 11px;
  color: var(--ink-3);
}

.setup__hint--warn {
  color: #b03e3d;
}

.setup__hint--foot {
  margin-top: 10px;
}

.page__error {
  margin-bottom: 16px;
}

.setup__preview {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface-2);
  padding: 14px 16px;
}

.setup__preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-2);
  padding-bottom: 10px;
  border-bottom: 1px dashed var(--line-strong);
}

.setup__plan li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  font-size: 12.5px;
  color: var(--ink-2);
}

.setup__plan li + li {
  border-top: 1px dashed var(--line);
}

.setup__plan .num {
  color: var(--ink-4);
  font-size: 10.5px;
}

.setup__plan .pill {
  margin-left: auto;
  height: 20px;
  font-size: 10.5px;
}

.setup__plan-meta {
  margin-left: auto;
  font-size: 10.5px;
  color: var(--ink-3);
}

.setup__cta {
  width: 100%;
  margin-top: 2px;
}

/* 机制卡 */
.mech {
  display: flex;
  flex-direction: column;
  gap: 14px;
  counter-reset: step;
}

.mech li {
  display: flex;
  gap: 12px;
}

.mech__idx {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  flex: none;
  border-radius: 50%;
  background: var(--surface-3);
  color: var(--ink-2);
  font-size: 10.5px;
  font-weight: 650;
  margin-top: 1px;
}

.mech__idx + div p {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink);
}

.mech small {
  display: block;
  margin-top: 3px;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--ink-3);
}

.mech__note {
  margin-top: 18px;
  padding: 12px 14px;
  border-radius: 10px;
  background: var(--warn-soft);
  border: 1px solid #f5e2c0;
}

.mech__note-title {
  font-size: 11px;
  font-weight: 650;
  color: #96600f;
  letter-spacing: 0.04em;
}

.mech__note p {
  margin-top: 4px;
  font-size: 11.5px;
  line-height: 1.65;
  color: #7d5814;
}

.mech__meta {
  display: flex;
  flex-direction: column;
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px dashed var(--line);
}

.mech__meta > div {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  font-size: 11.5px;
}

.mech__meta span {
  color: var(--ink-3);
}

.mech__meta strong {
  color: var(--ink-2);
  font-weight: 600;
}

/* ---------------- 面试进行中 ---------------- */
.session {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.session__bar {
  position: sticky;
  top: 72px;
  z-index: 12;
}

.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.bar__title {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.bar__title h2 {
  font-size: 16px;
  letter-spacing: -0.01em;
}

.bar__meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 6px;
  font-size: 11.5px;
  color: var(--ink-3);
}

.bar__meta strong {
  color: var(--ink);
  font-weight: 650;
}

.bar__sep {
  width: 1px;
  height: 11px;
  background: var(--line-strong);
}

.bar__depth {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.depth {
  display: inline-flex;
  gap: 3px;
}

.depth i {
  width: 9px;
  height: 4px;
  border-radius: 2px;
  background: var(--line-strong);
}

.depth i.is-on {
  background: var(--primary);
}

.bar__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

.bar__end {
  flex: none;
}

.bar__progress {
  position: relative;
  height: 3px;
  margin: 14px -22px -20px;
  background: var(--surface-3);
  overflow: hidden;
}

.bar__progress span {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #8b89f2, var(--primary));
  transition: width 0.4s ease;
}

.chat-wrap {
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.chat {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 26px 26px 22px;
  max-height: min(56vh, 620px);
  min-height: 320px;
  overflow-y: auto;
  background: linear-gradient(180deg, #fcfcff 0%, #ffffff 40%);
}

.msg {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.msg--candidate {
  flex-direction: row-reverse;
}

.msg__avatar {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  flex: none;
  border-radius: 10px;
  font-size: 11.5px;
  font-weight: 650;
}

.msg__avatar--interviewer {
  background: linear-gradient(150deg, #1d2145, #0d1024);
  color: #c9c7ff;
}

.msg__avatar--candidate {
  background: var(--primary-soft);
  color: var(--primary-strong);
}

.msg__body {
  max-width: 76%;
  min-width: 0;
}

.msg--candidate .msg__body {
  text-align: right;
}

.msg__who {
  font-size: 10.5px;
  color: var(--ink-3);
  margin-bottom: 5px;
  padding: 0 2px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.msg__tag {
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--surface-3);
  color: var(--ink-2);
  font-size: 10px;
}

.msg__bubble {
  display: inline-block;
  text-align: left;
  padding: 12px 15px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.75;
  color: var(--ink-2);
}

.msg--interviewer .msg__bubble {
  background: var(--surface-2);
  border: 1px solid var(--line);
  border-top-left-radius: 4px;
}

.msg--candidate .msg__bubble {
  background: var(--primary-soft);
  border: 1px solid #dedcfb;
  border-top-right-radius: 4px;
  color: #2f2d6b;
}

.feedback {
  margin-left: 42px;
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px dashed var(--line-strong);
  background: #fcfcfe;
}

.feedback__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.feedback__label {
  font-size: 10.5px;
  color: var(--ink-4);
  letter-spacing: 0.04em;
}

.verdict--good {
  background: var(--accent-soft);
  color: #0b7269;
}

.verdict--partial {
  background: var(--warn-soft);
  color: #96600f;
}

.verdict--bad {
  background: var(--danger-soft);
  color: #b03e3d;
}

.feedback__cols {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.feedback__title {
  font-size: 10.5px;
  font-weight: 650;
  letter-spacing: 0.04em;
  margin-bottom: 6px;
}

.feedback__title--hit {
  color: #0b7269;
}

.feedback__title--miss {
  color: #96600f;
}

.feedback__col li {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 11.5px;
  line-height: 1.65;
  color: var(--ink-2);
  padding: 2px 0;
}

.feedback__empty {
  color: var(--ink-4);
  font-size: 11px;
}

.feedback__note {
  margin-top: 10px;
  padding-top: 9px;
  border-top: 1px dashed var(--line);
  font-size: 11.5px;
  line-height: 1.65;
  color: var(--ink-2);
}

.session__wait {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 0 2px 42px;
  font-size: 11.5px;
  color: var(--ink-3);
}

.tick {
  flex: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  display: inline-grid;
  place-items: center;
  font-size: 9px;
  margin-top: 2px;
}

.tick--hit {
  background: var(--accent-soft);
  color: #0b7269;
}

.tick--miss {
  background: var(--warn-soft);
  color: #96600f;
}

.composer {
  border-top: 1px solid var(--line);
  padding: 16px 22px 18px;
  background: var(--surface);
}

.composer__stage {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--surface-3);
  font-size: 12px;
  color: var(--ink-2);
}

.composer__paused {
  margin-bottom: 10px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--surface-3);
  color: var(--ink-2);
  font-size: 12px;
}

.composer__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
}

.composer__hint {
  font-size: 11px;
  color: var(--ink-4);
}

.composer__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

.composer__voice {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding: 6px 10px;
  border-radius: 8px;
  background: var(--surface-3);
  font-size: 12px;
  color: var(--ink-2);
}

.composer__voice em {
  font-style: normal;
  color: var(--ink-3);
  max-width: 60%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ---------------- 评估摘要 ---------------- */
.summary {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.summary__head {
  display: flex;
  align-items: center;
  gap: 26px;}

.summary__copy {
  min-width: 0;
  flex: 1;
}

.summary__copy h2 {
  margin-top: 8px;
  font-size: 21px;
  letter-spacing: -0.025em;
}

.summary__desc {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.75;
  color: var(--ink-2);
  max-width: 640px;
}

.summary__empty {
  font-size: 12px;
  line-height: 1.7;
  color: var(--ink-3);
}

.summary__stats {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
}

.summary__stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 106px;
  padding: 9px 14px;
  border-radius: 10px;
  background: var(--surface-2);
  border: 1px solid var(--line);
}

.summary__stat-label {
  font-size: 10.5px;
  color: var(--ink-3);
}

.summary__stat-value {
  font-size: 17px;
  font-weight: 650;
  color: var(--ink);
}

.summary__stat-value small {
  margin-left: 2px;
  font-size: 10.5px;
  font-weight: 500;
  color: var(--ink-3);
}

.summary__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 12px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px solid transparent;
}

.tag--good {
  background: var(--accent-soft);
  border-color: #d3ece7;
  color: #14574f;
}

.tag--warn {
  background: var(--warn-soft);
  border-color: #f5e2c0;
  color: #7d5814;
}

.tag__dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.6;
}

.next {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
}

.next__title {
  font-size: 14px;
  font-weight: 650;
}

.next__desc {
  margin-top: 4px;
  font-size: 12px;
  color: var(--ink-3);
}

@media (max-width: 1024px) {
  .setup {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .session__bar {
    position: static;
  }

  .bar {
    flex-wrap: wrap;
  }

  .chat {
    padding: 18px 16px;
    max-height: none;
  }

  .msg__body {
    max-width: 86%;
  }

  .feedback {
    margin-left: 0;
  }

  .feedback__cols {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .summary__head {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
  }

  .summary__grid {
    grid-template-columns: 1fr;
  }

  .summary__stat {
    flex: 1;
    min-width: 92px;
  }

  .composer {
    padding: 14px;
  }

  .composer__hint {
    display: none;
  }
}
</style>
