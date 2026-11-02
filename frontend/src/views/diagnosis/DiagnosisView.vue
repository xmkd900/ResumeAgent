<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, UploadFilled } from '@element-plus/icons-vue'

import ChartBox from '@/components/ChartBox.vue'
import EmptyState from '@/components/EmptyState.vue'
import PageHeader from '@/components/PageHeader.vue'
import ScoreRing from '@/components/ScoreRing.vue'
import SectionCard from '@/components/SectionCard.vue'
import { ISSUE_TYPE_LABELS, SEVERITY_META } from '@/constants'

/* ---------------- 演示数据（业务接口未接入） ---------------- */

const SAMPLE_JD = `岗位：后端开发工程师（2026 校招）
职责：负责交易/订单核心链路设计与开发；参与系统性能优化与稳定性建设。
要求：熟悉 Java 与 Spring Boot；掌握 MySQL 索引与慢查询优化；了解 Redis 缓存设计；有高并发项目经验者优先。`

const DIMENSIONS = [
  { name: '项目深度', score: 78 },
  { name: '技术广度', score: 85 },
  { name: '表达结构', score: 88 },
  { name: '成果量化', score: 62 },
  { name: '岗位匹配', score: 81 },
]

const ISSUES = [
  {
    id: 1,
    type: 'quantification',
    severity: 'high',
    dimension: '成果量化',
    quote: '负责订单系统的开发与维护，提升了系统性能。',
    problem: '只有动作没有结果。性能提升了多少、影响多大范围，招聘方无法判断，这句话几乎不产生信息增量。',
    rewritten:
      '主导订单系统性能优化：定位到慢查询源于回表过滤，重构联合索引并引入缓存，下单接口 P99 从 820ms 降至 210ms，支撑大促单日 120 万单。',
  },
  {
    id: 2,
    type: 'depth',
    severity: 'high',
    dimension: '项目深度',
    quote: '使用 Redis 缓存热点数据。',
    problem: '只写了「用了什么」，没有「为什么这样选」和「踩过什么坑」。技术选型的取舍才是面试官真正想追问的部分。',
    rewritten:
      '针对商品详情页峰值 3k QPS 的热点 key，采用 Redis + 本地 Caffeine 二级缓存，并加互斥锁防止缓存击穿；命中率提升至 96%，数据库读负载下降约 70%。',
  },
  {
    id: 3,
    type: 'structure',
    severity: 'medium',
    dimension: '表达结构',
    quote: '技能：Java、MySQL、Redis、Kafka、Spring Boot、Docker、Kubernetes、Git……',
    problem: '技能平铺罗列、没有熟练度分层，招聘方无法在 10 秒内定位你的强项，反而稀释了核心竞争力。',
    rewritten:
      'Java（主力语言，2 年）· MySQL（索引优化 / 慢查询治理）· Redis（缓存设计与分布式锁）· Kafka（了解，做过日志管道）',
  },
  {
    id: 4,
    type: 'completeness',
    severity: 'low',
    dimension: '信息完整',
    quote: '项目经历：校园二手交易平台。',
    problem: '缺少角色、规模与技术难点的最小信息集，项目看起来像课程作业而不是工程实践。',
    rewritten:
      '独立负责校园二手交易平台后端（注册用户 1.2 万、日均订单 800），设计商品检索与订单状态机，主导支付对账模块，线上零资损。',
  },
]

const HISTORY = [
  { id: 1, date: '今天 11:32', score: 82, filename: '张明-后端开发-2026.pdf', current: true },
  { id: 2, date: '10-28', score: 76, filename: '张明-后端开发-v3.pdf', current: false },
  { id: 3, date: '10-21', score: 71, filename: '张明-后端开发-v2.pdf', current: false },
  { id: 4, date: '10-14', score: 64, filename: '张明-后端开发-v1.pdf', current: false },
]

/* ---------------- 页面状态 ---------------- */

const fileInput = ref(null)
const reportEl = ref(null)
const file = ref(null)
const dragging = ref(false)
const jd = ref('')
const analyzing = ref(false)
const reportReady = ref(false)

let parseTimer = null
let analyzeTimer = null

onBeforeUnmount(() => {
  clearTimeout(parseTimer)
  clearTimeout(analyzeTimer)
})

const report = {
  overall: 82,
  summary:
    '技术栈与目标岗位匹配度高，项目具备真实复杂度；主要失分在成果量化与技术决策的取舍说明，按下列 4 条改写后预计可提升 8-12 分。',
  diagnosedAt: '今天 11:32',
}

const statusMeta = computed(() => {
  if (!file.value) return null
  const map = {
    pending: { dot: 'dot--pending', text: '解析中', hint: '正在抽取文本并分节' },
    done: { dot: 'dot--live', text: '解析完成', hint: '已完成文本抽取与结构分节' },
    failed: { dot: 'dot--failed', text: '解析失败', hint: '文件可能已损坏或为扫描件' },
  }
  return map[file.value.status]
})

const criticalCount = computed(() => ISSUES.filter((i) => i.severity === 'high').length)

const radarOption = computed(() => ({
  tooltip: { trigger: 'item' },
  radar: {
    indicator: DIMENSIONS.map((d) => ({ name: d.name, max: 100 })),
    center: ['50%', '54%'],
    radius: '62%',
    splitNumber: 4,
    axisName: { color: '#4d5266', fontSize: 11 },
    axisLine: { lineStyle: { color: '#e8eaf2' } },
    splitLine: { lineStyle: { color: '#edeff6' } },
    splitArea: { areaStyle: { color: ['rgba(91,91,214,0.02)', 'rgba(91,91,214,0.055)'] } },
  },
  series: [
    {
      type: 'radar',
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: 2, color: '#5b5bd6' },
      itemStyle: { color: '#5b5bd6', borderColor: '#fff', borderWidth: 1.5 },
      areaStyle: { color: 'rgba(91,91,214,0.16)' },
      data: [{ value: DIMENSIONS.map((d) => d.score), name: '本次诊断' }],
    },
  ],
}))

/* ---------------- 交互（仅前端演示） ---------------- */

function formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function pickFile() {
  fileInput.value?.click()
}

function acceptFile(raw) {
  if (!raw) return
  file.value = { name: raw.name, size: formatSize(raw.size), status: 'pending' }
  reportReady.value = false
  clearTimeout(parseTimer)
  parseTimer = setTimeout(() => {
    if (file.value) file.value.status = 'done'
  }, 1100)
}

function onFileChange(event) {
  acceptFile(event.target.files?.[0])
  event.target.value = ''
}

function onDrop(event) {
  dragging.value = false
  acceptFile(event.dataTransfer?.files?.[0])
}

function fillJd() {
  jd.value = SAMPLE_JD
}

function runDiagnosis() {
  if (!file.value) {
    ElMessage.warning('请先上传一份简历')
    return
  }
  if (file.value.status === 'pending') {
    ElMessage.info('简历还在解析中，请稍候')
    return
  }
  analyzing.value = true
  clearTimeout(analyzeTimer)
  analyzeTimer = setTimeout(async () => {
    analyzing.value = false
    reportReady.value = true
    await nextTick()
    reportEl.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, 1400)
}

function resetAll() {
  file.value = null
  reportReady.value = false
  jd.value = ''
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function scrollToHistory() {
  if (!reportReady.value) {
    ElMessage.info('生成报告后即可查看历史诊断')
    return
  }
  document.getElementById('history-card')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制改写建议')
  } catch {
    ElMessage.warning('浏览器拒绝了复制，请手动选择文本')
  }
}

function severityTone(severity) {
  return SEVERITY_META[severity]?.tone || 'muted'
}
</script>

<template>
  <div class="page">
    <PageHeader
      eyebrow="Resume Review"
      title="简历诊断"
      subtitle="上传简历，可选粘贴目标 JD。报告包含综合分、维度雷达与三段式改写建议——每条都引用原文。"
    >
      <template #actions>
        <el-button :icon="Refresh" v-if="reportReady" @click="resetAll">重新诊断</el-button>
        <el-button plain @click="scrollToHistory">历史诊断</el-button>
      </template>
    </PageHeader>

    <div class="grid">
      <SectionCard
        class="span-7"
        title="上传简历"
        subtitle="PDF / DOCX，异步解析后进入诊断"
      >
        <template #extra>
          <span class="pill pill--outline">
            <span class="dot" :class="statusMeta ? statusMeta.dot : ''" />
            {{ statusMeta ? statusMeta.text : '待上传' }}
          </span>
        </template>

        <div
          class="dropzone"
          :class="{ 'is-dragging': dragging, 'is-filled': !!file }"
          role="button"
          tabindex="0"
          @click="pickFile"
          @keydown.enter.prevent="pickFile"
          @keydown.space.prevent="pickFile"
          @dragover.prevent
          @dragenter.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="onDrop"
        >
          <input
            ref="fileInput"
            type="file"
            accept=".pdf,.doc,.docx"
            class="dropzone__input"
            @change="onFileChange"
          />

          <template v-if="!file">
            <span class="dropzone__icon">
              <el-icon><UploadFilled /></el-icon>
            </span>
            <p class="dropzone__title">拖拽简历到这里，或点击选择文件</p>
            <p class="dropzone__hint">PDF / DOCX · 单份不超过 10 MB · 扫描件暂不支持</p>
          </template>

          <template v-else>
            <div class="file">
              <span class="file__icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none">
                  <path d="M6 3h8l4 4v14H6z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" />
                  <path d="M14 3v4h4M9 13h6M9 16.5h4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
                </svg>
              </span>
              <div class="file__meta">
                <p class="file__name truncate">{{ file.name }}</p>
                <p class="file__sub">
                  <span>{{ file.size }}</span>
                  <span class="file__sep">·</span>
                  <span class="file__status" :class="`file__status--${file.status}`">
                    <span class="dot" :class="statusMeta?.dot" />
                    {{ statusMeta?.text }}
                  </span>
                </p>
              </div>
              <span class="file__replace" @click.stop="pickFile">重新上传</span>
            </div>
            <p class="dropzone__hint dropzone__hint--inline">{{ statusMeta?.hint }}</p>
          </template>
        </div>

        <div class="upload-foot">
          <p class="upload-foot__note">
            解析在后台异步执行，不阻塞页面；解析失败可重新上传。
          </p>
          <el-button type="primary" :loading="analyzing" @click="runDiagnosis">
            {{ analyzing ? '正在诊断…' : '开始诊断' }}
          </el-button>
        </div>
      </SectionCard>

      <SectionCard
        class="span-5"
        title="JD 对照（可选）"
        subtitle="粘贴目标岗位 JD，诊断会额外给出岗位匹配维度"
      >
        <el-input
          v-model="jd"
          type="textarea"
          :rows="7"
          maxlength="2000"
          show-word-limit
          resize="none"
          placeholder="把目标岗位的 JD 粘贴到这里：职责、硬性要求、加分项…"
        />
        <div class="jd-foot">
          <span class="muted">未关联 JD 时，只按通用 rubric 评分</span>
          <el-button link type="primary" @click="fillJd">填入示例</el-button>
        </div>
      </SectionCard>
    </div>

    <div ref="reportEl" class="report">
      <SectionCard v-if="!reportReady">
        <EmptyState
          title="报告将在诊断后出现在这里"
          description="上传简历并点击「开始诊断」，即可获得综合分、维度雷达与逐条改写建议。"
        >
          <el-button type="primary" plain :disabled="!file" @click="runDiagnosis">开始诊断</el-button>
        </EmptyState>
      </SectionCard>

      <template v-else>
        <div class="grid">
          <SectionCard class="span-8">
            <div class="score">
              <ScoreRing :score="report.overall" />
              <div class="score__copy">
                <div class="score__tags">
                  <span class="pill pill--primary">可投递</span>
                  <span class="pill pill--soft">结构完整</span>
                  <span class="pill pill--soft">量化偏弱</span>
                </div>
                <p class="score__summary">{{ report.summary }}</p>
                <dl class="score__meta">
                  <div>
                    <dt>诊断时间</dt>
                    <dd>{{ report.diagnosedAt }}</dd>
                  </div>
                  <div>
                    <dt>关联 JD</dt>
                    <dd>{{ jd ? '已关联' : '未关联' }}</dd>
                  </div>
                  <div>
                    <dt>简历文件</dt>
                    <dd class="truncate">{{ file?.name }}</dd>
                  </div>
                </dl>
              </div>
            </div>
            <div class="score__foot">
              <span class="score__foot-item">
                <strong class="num">{{ criticalCount }}</strong> 个高优先级问题
              </span>
              <span class="score__foot-sep" />
              <span class="score__foot-item">
                <strong class="num">{{ ISSUES.length }}</strong> 条改写建议
              </span>
              <span class="score__foot-sep" />
              <span class="score__foot-item">预计可提升 <strong class="num">8-12</strong> 分</span>
            </div>
          </SectionCard>

          <SectionCard
            class="span-4"
            title="维度雷达"
            subtitle="0-100 分，由内置 rubric 各维度加权得出"
          >
            <ChartBox :option="radarOption" height="228px" />
            <ul class="dims">
              <li v-for="dim in DIMENSIONS" :key="dim.name" class="dims__item">
                <span class="dims__name">{{ dim.name }}</span>
                <span class="dims__track">
                  <i :style="{ width: `${dim.score}%` }" :class="{ 'is-low': dim.score < 70 }" />
                </span>
                <span class="dims__value num">{{ dim.score }}</span>
              </li>
            </ul>
          </SectionCard>
        </div>

        <div class="grid grid--second">
          <SectionCard
            class="span-8"
            title="问题清单"
            :subtitle="`${ISSUES.length} 条建议 · 引用原文 → 问题说明 → 改写示例`"
          >
            <template #extra>
              <span class="pill pill--soft">{{ criticalCount }} 高优先级</span>
            </template>

            <div class="issues">
              <article
                v-for="(issue, index) in ISSUES"
                :key="issue.id"
                class="issue"
                :class="`issue--${issue.severity}`"
              >
                <header class="issue__head">
                  <span class="pill" :class="`pill--${severityTone(issue.severity)}`">
                    {{ SEVERITY_META[issue.severity].label }}
                  </span>
                  <span class="issue__type">{{ ISSUE_TYPE_LABELS[issue.type] || issue.type }}</span>
                  <span class="issue__dim">{{ issue.dimension }}</span>
                  <span class="issue__index num">#{{ String(index + 1).padStart(2, '0') }}</span>
                </header>

                <blockquote class="issue__quote">{{ issue.quote }}</blockquote>

                <div class="issue__row">
                  <p class="issue__label">问题</p>
                  <p class="issue__text">{{ issue.problem }}</p>
                </div>

                <div class="issue__row issue__row--fix">
                  <p class="issue__label">改写</p>
                  <p class="issue__text">{{ issue.rewritten }}</p>
                  <button class="issue__copy" type="button" @click="copyText(issue.rewritten)">复制</button>
                </div>
              </article>
            </div>
          </SectionCard>

          <SectionCard
            id="history-card"
            class="span-4"
            title="历史诊断"
            subtitle="同一份简历的分数变化"
          >
            <template #extra>
              <span class="muted num">{{ HISTORY.length }} 次</span>
            </template>

            <ul class="history">
              <li
                v-for="item in HISTORY"
                :key="item.id"
                class="history__item"
                :class="{ 'is-current': item.current }"
              >
                <div class="history__score num">{{ item.score }}</div>
                <div class="history__meta">
                  <p class="history__file truncate">{{ item.filename }}</p>
                  <p class="history__date">
                    {{ item.date }}
                    <span v-if="item.current" class="history__badge">本次</span>
                  </p>
                </div>
                <span class="history__trend" :class="item.current ? 'is-new' : ''">
                  <svg viewBox="0 0 16 16" width="12" height="12" fill="none">
                    <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                </span>
              </li>
            </ul>

            <p class="history__note">报告随时间累积，便于对比修改前后的变化。</p>
          </SectionCard>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
}

.grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 18px;
}

.grid--second {
  margin-top: 18px;
}

.span-7 {
  grid-column: span 7;
}

.span-5 {
  grid-column: span 5;
}

.span-8 {
  grid-column: span 8;
}

.span-4 {
  grid-column: span 4;
}

/* ---------------- 上传区 ---------------- */
.dropzone {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 176px;
  padding: 24px;
  border-radius: var(--radius);
  border: 1.5px dashed var(--line-strong);
  background: var(--surface-2);
  cursor: pointer;
  text-align: center;
  transition: border-color 0.18s ease, background-color 0.18s ease;
}

.dropzone:hover,
.dropzone:focus-visible {
  border-color: #b9b7ea;
  background: #fbfaff;
  outline: none;
}

.dropzone.is-dragging {
  border-color: var(--primary);
  background: var(--primary-soft);
}

.dropzone.is-filled {
  align-items: stretch;
  justify-content: center;
  gap: 10px;
  border-style: solid;
  border-color: var(--line);
  background: var(--surface);
  cursor: default;
  padding: 20px;
}

.dropzone__input {
  display: none;
}

.dropzone__icon {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: 14px;
  background: var(--primary-soft);
  color: var(--primary);
  font-size: 20px;
  margin-bottom: 8px;
}

.dropzone__title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--ink-2);
}

.dropzone__hint {
  font-size: 11.5px;
  color: var(--ink-3);
}

.dropzone__hint--inline {
  text-align: left;
  padding-left: 2px;
}

.file {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: var(--surface-2);
}

.file__icon {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid var(--line);
  color: var(--primary);
  flex: none;
}

.file__meta {
  min-width: 0;
  flex: 1;
}

.file__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
}

.file__sub {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 3px;
  font-size: 11px;
  color: var(--ink-3);
}

.file__sep {
  color: var(--ink-4);
}

.file__status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.file__status--done {
  color: #0b7269;
}

.file__status--pending {
  color: #96600f;
}

.file__status--failed {
  color: #b03e3d;
}

.file__replace {
  flex: none;
  font-size: 12px;
  font-weight: 550;
  color: var(--primary);
  padding: 4px 6px;
  border-radius: 6px;
}

.file__replace:hover {
  background: var(--primary-soft);
}

.upload-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 16px;
}

.upload-foot__note {
  font-size: 11.5px;
  color: var(--ink-3);
  line-height: 1.6;
}

/* ---------------- JD ---------------- */
.jd-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
  font-size: 11.5px;
}

/* ---------------- 报告 ---------------- */
.report {
  margin-top: 18px;
  scroll-margin-top: 78px;
}

.score {
  display: flex;
  align-items: center;
  gap: 26px;
}

.score__copy {
  min-width: 0;
  flex: 1;
}

.score__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.score__summary {
  font-size: 13px;
  line-height: 1.75;
  color: var(--ink-2);
}

.score__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 26px;
  margin: 16px 0 0;
}

.score__meta > div {
  min-width: 0;
}

.score__meta dt {
  font-size: 10.5px;
  color: var(--ink-3);
  letter-spacing: 0.02em;
}

.score__meta dd {
  margin: 3px 0 0;
  font-size: 12px;
  font-weight: 550;
  color: var(--ink-2);
  max-width: 220px;
}

.score__foot {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px dashed var(--line);
  font-size: 12px;
  color: var(--ink-3);
}

.score__foot-item strong {
  color: var(--ink);
  font-weight: 650;
}

.score__foot-sep {
  width: 1px;
  height: 12px;
  background: var(--line-strong);
}

/* ---------------- 雷达图 + 维度 ---------------- */
.dims {
  display: flex;
  flex-direction: column;
  gap: 9px;
  margin-top: 6px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}

.dims__item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 11.5px;
}

.dims__name {
  width: 56px;
  flex: none;
  color: var(--ink-2);
}

.dims__track {
  flex: 1;
  height: 5px;
  border-radius: 4px;
  background: var(--surface-3);
  overflow: hidden;
}

.dims__track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #8b89f2, #5b5bd6);
}

.dims__track i.is-low {
  background: linear-gradient(90deg, #e8b25f, #c67c12);
}

.dims__value {
  width: 22px;
  text-align: right;
  color: var(--ink-2);
  font-weight: 600;
}

/* ---------------- 问题卡 ---------------- */
.issues {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.issue {
  position: relative;
  padding: 16px 18px;
  border-radius: var(--radius);
  border: 1px solid var(--line);
  background: var(--surface);
  overflow: hidden;
}

.issue::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--line-strong);
}

.issue--high::before {
  background: var(--danger);
}

.issue--medium::before {
  background: #d8a12c;
}

.issue--low::before {
  background: var(--accent);
}

.issue__head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.pill--danger {
  background: var(--danger-soft);
  color: #b03e3d;
}

.pill--warn {
  background: var(--warn-soft);
  color: #96600f;
}

.pill--muted {
  background: var(--surface-3);
  color: var(--ink-2);
}

.issue__type {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink);
}

.issue__dim {
  font-size: 11px;
  color: var(--ink-3);
  padding-left: 8px;
  border-left: 1px solid var(--line-strong);
}

.issue__index {
  margin-left: auto;
  font-size: 11px;
  color: var(--ink-4);
}

.issue__quote {
  margin: 0 0 12px;
  padding: 10px 14px;
  border-radius: 0 8px 8px 0;
  border-left: 2px solid var(--line-strong);
  background: var(--surface-2);
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--ink-2);
}

.issue__row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 4px 0;
}

.issue__row + .issue__row {
  margin-top: 6px;
}

.issue__row--fix {
  position: relative;
  margin-top: 8px;
  padding: 10px 12px;
  border-radius: 9px;
  background: var(--accent-soft);
}

.issue__label {
  flex: none;
  width: 30px;
  font-size: 11px;
  font-weight: 650;
  color: var(--ink-3);
  padding-top: 1px;
}

.issue__row--fix .issue__label {
  color: #0b7269;
}

.issue__text {
  flex: 1;
  font-size: 12.5px;
  line-height: 1.72;
  color: var(--ink-2);
}

.issue__row--fix .issue__text {
  color: #14574f;
  padding-right: 40px;
}

.issue__copy {
  position: absolute;
  right: 8px;
  bottom: 8px;
  border: 0;
  background: rgba(255, 255, 255, 0.7);
  color: #0b7269;
  font-size: 10.5px;
  font-weight: 600;
  padding: 3px 7px;
  border-radius: 5px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.16s ease;
}

.issue:hover .issue__copy,
.issue__copy:focus-visible {
  opacity: 1;
}

/* ---------------- 历史 ---------------- */
.history {
  display: flex;
  flex-direction: column;
}

.history__item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 10px;
  border-radius: 10px;
  transition: background-color 0.16s ease;
}

.history__item + .history__item {
  border-top: 1px dashed var(--line);
}

.history__item:hover {
  background: var(--surface-2);
}

.history__item.is-current {
  background: var(--primary-soft);
}

.history__score {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  flex: none;
  border-radius: 10px;
  background: var(--surface);
  border: 1px solid var(--line);
  font-size: 14px;
  font-weight: 650;
  color: var(--ink);
}

.history__item.is-current .history__score {
  border-color: transparent;
  background: #fff;
  color: var(--primary-strong);
}

.history__meta {
  min-width: 0;
  flex: 1;
}

.history__file {
  font-size: 12px;
  font-weight: 550;
  color: var(--ink-2);
}

.history__date {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 3px;
  font-size: 10.5px;
  color: var(--ink-3);
}

.history__badge {
  padding: 0 6px;
  border-radius: 4px;
  background: var(--primary);
  color: #fff;
  font-size: 9.5px;
  font-weight: 600;
  line-height: 1.6;
}

.history__trend {
  flex: none;
  color: var(--ink-4);
  opacity: 0.7;
}

.history__trend.is-new {
  color: var(--primary);
  opacity: 1;
}

.history__note {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--line);
  font-size: 11px;
  color: var(--ink-3);
  line-height: 1.6;
}

@media (max-width: 1080px) {
  .span-7,
  .span-5,
  .span-8,
  .span-4 {
    grid-column: span 12;
  }

  .dims {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px 22px;
  }
}

@media (max-width: 640px) {
  .score {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
  }

  .score__foot {
    gap: 8px;
  }

  .upload-foot {
    flex-direction: column;
    align-items: stretch;
  }

  .upload-foot :deep(.el-button) {
    width: 100%;
  }

  .dims {
    grid-template-columns: 1fr;
  }

  .issue__row {
    flex-direction: column;
    gap: 4px;
  }

  .issue__label {
    width: auto;
  }

  .issue__copy {
    opacity: 1;
  }
}
</style>
