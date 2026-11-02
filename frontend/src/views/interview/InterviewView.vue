<script setup>
import { computed, nextTick, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight, Promotion, VideoPlay } from '@element-plus/icons-vue'

import PageHeader from '@/components/PageHeader.vue'
import ScoreRing from '@/components/ScoreRing.vue'
import SectionCard from '@/components/SectionCard.vue'
import { VERDICT_META } from '@/constants'

const router = useRouter()

/* ---------------- 演示数据 ---------------- */

const POSITIONS = ['后端开发工程师', '前端开发工程师', '算法工程师', '数据分析师']
const JD_OPTIONS = [
  { value: 'jd-1', label: '字节跳动 · 后端开发（交易方向）' },
  { value: 'jd-2', label: '美团 · Java 后端开发' },
]

const OPENING_MESSAGES = [
  {
    id: 1,
    role: 'interviewer',
    content: '我们先从索引聊起。你简历里提到对订单查询做过优化，当时慢查询的根因是什么？',
  },
  {
    id: 2,
    role: 'candidate',
    content:
      '订单列表页要按用户、状态、时间三个条件过滤，但当时只有 user_id 单列索引，回表之后还要过滤大量数据。订单量到千万级之后，接口 P99 超过了 800ms。',
    judgement: {
      verdict: 'good',
      hits: ['定位到回表是主要成本', '给出了真实数据量级与指标'],
      misses: ['没有说明用执行计划验证的方式'],
    },
  },
  {
    id: 3,
    role: 'interviewer',
    content: '嗯，根因清楚。那你最后怎么设计索引的？为什么不是把三个字段都建成独立索引？',
  },
  {
    id: 4,
    role: 'candidate',
    content:
      '我建了 (user_id, status, created_at) 的联合索引。独立索引在 AND 条件下通常只会选一个走，另外两个条件还要回表过滤；联合索引可以把过滤都放在索引层完成，只回表取需要的列。',
    judgement: {
      verdict: 'partial',
      hits: ['说明了联合索引的最左前缀', '解释了独立索引在 AND 下的选择问题'],
      misses: ['没有提到覆盖索引进一步避免回表', '缺少上线后的效果对比'],
    },
  },
  {
    id: 5,
    role: 'interviewer',
    content: '如果这个查询还要按金额排序，你的索引会怎么调整？代价是什么？',
  },
]

const FOLLOW_UPS = [
  '如果缓存和数据库出现短暂不一致，你怎么保证用户最终看到的结果是对的？',
  '线上突然冒出一批慢查询，你的排查顺序是什么？',
  '最后一个问题：如果让你重新设计这个模块，你会改动哪一处？',
]

const SUMMARY = {
  score: 78,
  headline: '技术判断扎实，表达可以更聚焦结果。',
  description:
    '8 道题中 6 道回答到位，索引与并发部分有真实的工程细节；薄弱环节集中在「如何验证效果」和「失败经验的复盘」，这也是后续练习的重点。',
  stats: [
    { label: '覆盖题目', value: '8', suffix: '题' },
    { label: '追问深度', value: '1.6', suffix: '层' },
    { label: '要点覆盖', value: '11/16', suffix: '' },
  ],
  strengths: ['索引优化有真实数据支撑', '能主动说明技术取舍', '回答结构清晰'],
  improvements: ['缺少量化验证方式', '缓存一致性只提到最终一致', '复盘缺少失败经验'],
}

/* ---------------- 页面状态 ---------------- */

const stage = ref('setup') // setup | ongoing | summary
const starting = ref(false)
const setupForm = reactive({ position: POSITIONS[0], jd: '' })

const session = reactive({
  position: POSITIONS[0],
  current: 3,
  total: 8,
  topic: '索引与查询优化',
  depth: 1,
  maxDepth: 2,
})

const messages = ref(OPENING_MESSAGES.map((item) => ({ ...item })))
const answer = ref('')
const chatEl = ref(null)
let seed = 100

const progress = computed(() => Math.round((session.current / session.total) * 100))

async function startInterview() {
  if (!setupForm.position) {
    ElMessage.warning('请先选择目标岗位')
    return
  }
  starting.value = true
  await new Promise((resolve) => setTimeout(resolve, 600))
  session.position = setupForm.position
  session.current = 3
  session.depth = 1
  messages.value = OPENING_MESSAGES.map((item) => ({ ...item }))
  stage.value = 'ongoing'
  starting.value = false
  scrollChat()
  ElMessage.success('面试已开始（示例数据）')
}

function scrollChat() {
  nextTick(() => {
    if (chatEl.value) chatEl.value.scrollTop = chatEl.value.scrollHeight
  })
}

function submitAnswer() {
  const text = answer.value.trim()
  if (!text) {
    ElMessage.warning('先写下你的回答')
    return
  }

  messages.value.push({
    id: ++seed,
    role: 'candidate',
    content: text,
    judgement: {
      verdict: 'partial',
      hits: ['回答给出了明确的处理顺序'],
      misses: ['没有说明如何验证效果', '缺少边界情况的讨论'],
    },
  })
  answer.value = ''
  session.depth = Math.min(session.maxDepth, session.depth + 1)

  if (session.current >= session.total) {
    scrollChat()
    ElMessage.info('题目已问完，可以结束面试查看评估')
    return
  }

  session.current += 1
  messages.value.push({
    id: ++seed,
    role: 'interviewer',
    content: FOLLOW_UPS[(session.current - 3) % FOLLOW_UPS.length],
  })
  scrollChat()
}

async function finishInterview() {
  try {
    await ElMessageBox.confirm(
      '结束后会生成本场评估摘要，并更新薄弱点。确定现在结束吗？',
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
  stage.value = 'summary'
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function restart() {
  stage.value = 'setup'
  answer.value = ''
}

function goGrowth() {
  router.push('/growth')
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
      subtitle="按岗位生成出题计划，逐轮判卷并沿追问链下钻。面试过程中不展示检索来源，保持沉浸。"
    >
      <template #actions>
        <span v-if="stage === 'ongoing'" class="pill pill--accent">
          <span class="dot dot--live" />进行中
        </span>
        <el-button v-if="stage !== 'setup'" @click="restart">重新开始</el-button>
      </template>
    </PageHeader>

    <!-- ================= 开始面试 ================= -->
    <div v-if="stage === 'setup'" class="setup">
      <SectionCard class="setup__main" title="开始一场结构化面试">
        <div class="setup__body">
          <div class="setup__field">
            <label class="setup__label">目标岗位</label>
            <el-select
              v-model="setupForm.position"
              size="large"
              placeholder="选择岗位"
              class="setup__control"
            >
              <el-option v-for="p in POSITIONS" :key="p" :label="p" :value="p" />
            </el-select>
            <p class="setup__hint">题库按 position 维护，决定出题范围与追问链。</p>
          </div>

          <div class="setup__field">
            <label class="setup__label">关联 JD（可选）</label>
            <el-select
              v-model="setupForm.jd"
              size="large"
              clearable
              placeholder="选择一份已保存的 JD"
              class="setup__control"
            >
              <el-option v-for="jd in JD_OPTIONS" :key="jd.value" :label="jd.label" :value="jd.value" />
            </el-select>
            <p class="setup__hint">关联后会按 JD 要求调整出题权重。</p>
          </div>

          <div class="setup__preview">
            <div class="setup__preview-head">
              <span>出题计划预览</span>
              <span class="pill pill--soft">快照 8 题</span>
            </div>
            <ul class="setup__plan">
              <li><span class="num">01</span>索引与查询优化<span class="pill pill--primary">进行中</span></li>
              <li><span class="num">02</span>缓存与一致性<span class="setup__plan-meta">追问 2 层</span></li>
              <li><span class="num">03</span>并发与事务<span class="setup__plan-meta">追问 1 层</span></li>
              <li><span class="num">04</span>系统设计（交易下单）<span class="setup__plan-meta">追问 2 层</span></li>
            </ul>
          </div>

          <el-button
            type="primary"
            size="large"
            class="setup__cta"
            :icon="VideoPlay"
            :loading="starting"
            @click="startInterview"
          >
            开始面试
          </el-button>
        </div>
      </SectionCard>

      <SectionCard class="setup__side" title="本场机制" subtitle="工作流可控，决策点自主">
        <ol class="mech">
          <li>
            <span class="mech__idx">1</span>
            <div><p>出题</p><small>从题库取题，计划存为会话快照</small></div>
          </li>
          <li>
            <span class="mech__idx">2</span>
            <div><p>判卷</p><small>按 rubric 给出三档结论与要点命中</small></div>
          </li>
          <li>
            <span class="mech__idx">3</span>
            <div><p>追问</p><small>表现达标则沿预设链下钻，否则换题</small></div>
          </li>
          <li>
            <span class="mech__idx">4</span>
            <div><p>收束</p><small>整场评估，薄弱点写入成长闭环</small></div>
          </li>
        </ol>

        <div class="mech__note">
          <span class="mech__note-title">沉浸优先</span>
          <p>面试页不展示检索来源、追问树状态与 KB 命中细节——真实面试官不会给你看草稿纸。</p>
        </div>

        <div class="mech__meta">
          <div><span>预计时长</span><strong>25-35 分钟</strong></div>
          <div><span>题目数量</span><strong>8 题</strong></div>
          <div><span>最大追问深度</span><strong>2 层</strong></div>
        </div>
      </SectionCard>
    </div>

    <!-- ================= 面试进行中 ================= -->
    <div v-else-if="stage === 'ongoing'" class="session">
      <SectionCard class="session__bar" :padded="true">
        <div class="bar">
          <div class="bar__main">
            <div class="bar__title">
              <h2>{{ session.position }}</h2>
              <span class="pill pill--primary">{{ session.topic }}</span>
            </div>
            <div class="bar__meta">
              <span>第 <strong class="num">{{ session.current }}</strong> / 共
                <strong class="num">{{ session.total }}</strong> 题</span>
              <span class="bar__sep" />
              <span class="bar__depth">
                追问深度
                <span class="depth">
                  <i
                    v-for="n in session.maxDepth"
                    :key="n"
                    :class="{ 'is-on': n <= session.depth }"
                  />
                </span>
                <span class="num">{{ session.depth }}/{{ session.maxDepth }}</span>
              </span>
            </div>
          </div>
          <el-button class="bar__end" @click="finishInterview">结束面试</el-button>
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
                <p class="msg__who">{{ msg.role === 'interviewer' ? '面试官' : '我的回答' }}</p>
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
                  </ul>
                </div>
                <div class="feedback__col">
                  <p class="feedback__title feedback__title--miss">待补要点</p>
                  <ul>
                    <li v-for="miss in msg.judgement.misses" :key="miss">
                      <span class="tick tick--miss">–</span>{{ miss }}
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </template>
        </div>

        <div class="composer">
          <el-input
            v-model="answer"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            resize="none"
            placeholder="用自己的话回答，尽量给出因果、取舍与验证方式…"
            @keydown.enter.exact.prevent="submitAnswer"
          />
          <div class="composer__foot">
            <span class="composer__hint">Enter 提交 · Shift + Enter 换行</span>
            <el-button type="primary" :icon="Promotion" @click="submitAnswer">提交回答</el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- ================= 整场评估 ================= -->
    <div v-else class="summary">
      <SectionCard class="summary__main">
        <div class="summary__head">
          <ScoreRing :score="SUMMARY.score" :size="124" label="本场表现" suffix="/ 100" />
          <div class="summary__copy">
            <p class="eyebrow">Session Summary</p>
            <h2>{{ SUMMARY.headline }}</h2>
            <p class="summary__desc">{{ SUMMARY.description }}</p>
            <div class="summary__stats">
              <div v-for="stat in SUMMARY.stats" :key="stat.label" class="summary__stat">
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
          <ul class="tags">
            <li v-for="item in SUMMARY.strengths" :key="item" class="tag tag--good">
              <span class="tag__dot" />{{ item }}
            </li>
          </ul>
        </SectionCard>

        <SectionCard title="待加强" subtitle="已同步为成长闭环中的薄弱点">
          <ul class="tags">
            <li v-for="item in SUMMARY.improvements" :key="item" class="tag tag--warn">
              <span class="tag__dot" />{{ item }}
            </li>
          </ul>
        </SectionCard>
      </div>

      <SectionCard class="summary__next">
        <div class="next">
          <div>
            <p class="next__title">下一步：去成长闭环补强这 3 个薄弱点</p>
            <p class="next__desc">薄弱点已按严重度排序，配套练习题来自知识库对应知识点。</p>
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

/* ---------------- 评估摘要 ---------------- */
.summary {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.summary__head {
  display: flex;
  align-items: center;
  gap: 26px;
}

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
