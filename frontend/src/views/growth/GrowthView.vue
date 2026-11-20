<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowRight, Check, Clock, EditPen } from '@element-plus/icons-vue'

import PageHeader from '@/components/PageHeader.vue'
import SectionCard from '@/components/SectionCard.vue'
import { growthApi } from '@/api/growth'
import { SEVERITY_META, VERDICT_META, WEAK_STATUS_META } from '@/constants'

const router = useRouter()

const queue = ref({
  stats: { open: 0, due: 0, resolved: 0 },
  fix: [],
  review: [],
  next_review_at: null,
})
const loading = ref(true)
const loadError = ref('')
const resolvedItems = ref([])
const resolvedOpen = ref(false)

const selected = ref(null)
const card = ref(null)
const cardLoading = ref(false)

const drawerOpen = ref(false)
const mode = ref('fix')
const answer = ref('')
const submitting = ref(false)
const result = ref(null)

const queueItems = computed(() => [...queue.value.fix, ...queue.value.review])

async function loadAll(showLoading = true) {
  if (showLoading) loading.value = true
  loadError.value = ''
  try {
    const [queueData, allData] = await Promise.all([
      growthApi.getQueue(),
      growthApi.listWeakPoints(),
    ])
    queue.value = queueData
    resolvedItems.value = (allData.items || []).filter(
      (item) => item.resolved || item.status === 'resolved',
    )

    const keep =
      selected.value && queueItems.value.find((item) => item.id === selected.value.id)
    selected.value = keep || queueItems.value[0] || null
    if (selected.value) await loadCard(selected.value.id)
    else card.value = null
  } catch (err) {
    loadError.value = err?.message || '今日队列加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

async function loadCard(id) {
  cardLoading.value = true
  try {
    card.value = await growthApi.getGapCard(id)
  } catch {
    card.value = null
  } finally {
    cardLoading.value = false
  }
}

function selectItem(item) {
  selected.value = item
  loadCard(item.id)
}

function openAction(item, kind) {
  if (!item) return
  selected.value = item
  mode.value = kind
  answer.value = ''
  result.value = null
  drawerOpen.value = true
  if (!card.value || card.value.weak_point.id !== item.id) loadCard(item.id)
}

async function submit() {
  const point = selected.value
  if (!point) return
  if (!answer.value.trim()) {
    ElMessage.warning('先写下你的回答')
    return
  }
  submitting.value = true
  try {
    const data =
      mode.value === 'fix'
        ? await growthApi.submitFix(point.id, answer.value)
        : await growthApi.submitReview(point.id, {
            answer: answer.value,
            questionId: card.value?.review_question?.question_id ?? null,
          })
    result.value = { mode: mode.value, ...data }
    ElMessage.success(data.message || (data.gap_covered ? '这条补上了' : '还没补到点上'))
    await loadAll(false)
    // 修复后这条会离开"待修复"队列，但抽屉要停在它上面展示结果
    if (data.weak_point) {
      selected.value = data.weak_point
      await loadCard(data.weak_point.id)
    }
  } catch (err) {
    ElMessage.error(err?.message || '提交失败，请稍后重试')
  } finally {
    submitting.value = false
  }
}

function statusMeta(item) {
  return WEAK_STATUS_META[item?.status] || WEAK_STATUS_META.open
}

function verdictLabel(verdict) {
  return VERDICT_META[verdict]?.label || verdict
}

function shortText(text, limit = 90) {
  const value = (text || '').trim()
  return value.length > limit ? `${value.slice(0, limit)}…` : value
}

function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return `${date.getMonth() + 1} 月 ${date.getDate()} 日`
}

onMounted(() => loadAll())
</script>

<template>
  <div class="page">
    <PageHeader
      eyebrow="Growth Loop"
      title="成长闭环"
      subtitle="面试暴露的缺口，先补这一句，再按间隔用变体题复查；复查通过才算真正掌握。"
    >
      <template #actions>
        <span v-if="!loading && !loadError" class="pill pill--soft">
          今日 {{ queue.fix.length + queue.review.length }} 项
        </span>
      </template>
    </PageHeader>

    <div class="stats">
      <div class="stat">
        <span class="stat__label">待修复</span>
        <span class="stat__value num">{{ queue.stats.open }}<small>条</small></span>
        <span class="stat__hint">只补缺的那一句，30 秒</span>
      </div>
      <div class="stat">
        <span class="stat__label">今日复查</span>
        <span class="stat__value num">{{ queue.stats.due }}<small>条</small></span>
        <span class="stat__hint">
          {{
            queue.stats.due
              ? '到期了，用变体题确认没忘'
              : `下次复查 ${formatDate(queue.next_review_at)}`
          }}
        </span>
      </div>
      <div class="stat">
        <span class="stat__label">已掌握</span>
        <span class="stat__value num">{{ queue.stats.resolved }}<small>条</small></span>
        <span class="stat__hint">按记忆曲线拉长，最长 30 天</span>
      </div>
    </div>

    <div class="grid">
      <SectionCard class="span-7" title="今日队列" subtitle="先修复，再复查；没有到期项就不打扰你">
        <p v-if="loading" class="state">正在整理今天的队列…</p>
        <p v-else-if="loadError" class="state state--error">{{ loadError }}</p>

        <div v-else-if="!queueItems.length" class="empty">
          <p class="empty__title">今天没有待办</p>
          <p class="empty__desc">
            完成一场模拟面试后，得分低于 60 的题目会变成「缺口卡」出现在这里；复查到期时也会回到队列。
          </p>
          <el-button type="primary" plain @click="router.push('/interview')">
            去做一场模拟面试
          </el-button>
        </div>

        <template v-else>
          <section v-if="queue.fix.length" class="group">
            <header class="group__head">
              <span class="dot dot--warn" />
              <h3>待修复</h3>
              <span class="group__count">{{ queue.fix.length }}</span>
              <span class="group__hint">补上缺的那一句</span>
            </header>
            <ul class="rows">
              <li
                v-for="item in queue.fix"
                :key="item.id"
                class="row"
                :class="{ 'is-active': selected?.id === item.id }"
                @click="selectItem(item)"
              >
                <div class="row__body">
                  <div class="row__top">
                    <p class="row__topic">{{ item.topic }}</p>
                    <span class="pill" :class="`pill--sev-${item.severity}`">
                      {{ SEVERITY_META[item.severity]?.label }}
                    </span>
                  </div>
                  <p class="row__gap">
                    缺：{{ shortText(item.gap_point || item.last_evidence) }}
                  </p>
                  <p class="row__meta">
                    复发 {{ item.relapse_count }} 次 · 来自{{
                      item.source === 'interview' ? '面试' : '自测'
                    }}
                  </p>
                </div>
                <el-button
                  size="small"
                  type="primary"
                  plain
                  @click.stop="openAction(item, 'fix')"
                >
                  补这一句
                </el-button>
              </li>
            </ul>
          </section>

          <section v-if="queue.review.length" class="group">
            <header class="group__head">
              <span class="dot dot--accent" />
              <h3>今日复查</h3>
              <span class="group__count">{{ queue.review.length }}</span>
              <span class="group__hint">变体题，不看原文</span>
            </header>
            <ul class="rows">
              <li
                v-for="item in queue.review"
                :key="item.id"
                class="row"
                :class="{ 'is-active': selected?.id === item.id }"
                @click="selectItem(item)"
              >
                <div class="row__body">
                  <div class="row__top">
                    <p class="row__topic">{{ item.topic }}</p>
                    <span class="pill pill--accent">待复查</span>
                  </div>
                  <p class="row__gap">
                    复查重点：{{ shortText(item.gap_point || item.last_evidence) }}
                  </p>
                  <p class="row__meta">
                    第 {{ item.review_stage }} 阶段 · 已复查 {{ item.review_count }} 次
                  </p>
                </div>
                <el-button size="small" plain @click.stop="openAction(item, 'review')">
                  去复查
                </el-button>
              </li>
            </ul>
          </section>
        </template>

        <div v-if="resolvedItems.length" class="resolved">
          <button type="button" class="resolved__toggle" @click="resolvedOpen = !resolvedOpen">
            <el-icon><Check /></el-icon>
            已掌握 {{ resolvedItems.length }} 条
            <span>{{ resolvedOpen ? '收起' : '展开' }}</span>
          </button>
          <ul v-if="resolvedOpen" class="resolved__list">
            <li v-for="item in resolvedItems" :key="item.id">
              <span class="resolved__topic">{{ item.topic }}</span>
              <span class="resolved__gap">
                {{ shortText(item.gap_point || item.last_evidence, 48) }}
              </span>
            </li>
          </ul>
        </div>
      </SectionCard>

      <SectionCard
        class="span-5"
        title="缺口卡"
        :subtitle="selected ? '原题、原话与缺的那一条' : '选择左侧一项查看'"
      >
        <p v-if="!selected" class="state">左侧还没有待办；面试后会自动生成缺口卡。</p>
        <p v-else-if="cardLoading" class="state">正在回放原题…</p>
        <p v-else-if="!card" class="state state--error">缺口卡加载失败</p>

        <div v-else class="gapcard">
          <div class="gapcard__top">
            <h3>{{ card.weak_point.topic }}</h3>
            <span class="pill" :class="`pill--status-${statusMeta(card.weak_point).tone}`">
              {{ statusMeta(card.weak_point).label }}
            </span>
          </div>

          <div class="block">
            <p class="block__label">原题</p>
            <p class="block__text">{{ card.source.question || '（这条缺口没有关联原题）' }}</p>
          </div>

          <div v-if="card.source.quote || card.source.answer" class="block block--quote">
            <p class="block__label">你当时的原话</p>
            <p class="block__text">
              {{ shortText(card.source.quote || card.source.answer, 160) }}
            </p>
          </div>

          <div class="block block--gap">
            <p class="block__label">缺的那一条</p>
            <p class="block__text">{{ card.weak_point.gap_point || '未记录具体缺口' }}</p>
          </div>

          <div class="block">
            <p class="block__label">怎么补</p>
            <p class="block__text">{{ card.suggestion }}</p>
          </div>

          <div v-if="card.review_question" class="block">
            <p class="block__label">复查会换一道题</p>
            <p class="block__text">{{ card.review_question.title }}</p>
            <p class="block__meta">
              {{ card.review_question.type }} · {{ card.review_question.difficulty }}
            </p>
          </div>

          <div class="gapcard__foot">
            <span class="gapcard__hint">
              <el-icon><Clock /></el-icon>
              {{
                card.weak_point.next_review_at
                  ? `下次复查 ${formatDate(card.weak_point.next_review_at)}`
                  : statusMeta(card.weak_point).hint
              }}
            </span>
            <el-button
              v-if="card.weak_point.status === 'open'"
              type="primary"
              :icon="EditPen"
              @click="openAction(card.weak_point, 'fix')"
            >
              补这一句
            </el-button>
            <el-button
              v-else-if="card.weak_point.status === 'fixed'"
              type="primary"
              plain
              @click="openAction(card.weak_point, 'review')"
            >
              去复查
            </el-button>
            <span v-else class="pill pill--accent">已掌握</span>
          </div>
        </div>
      </SectionCard>
    </div>

    <el-drawer v-model="drawerOpen" size="520px" :with-header="false" destroy-on-close>
      <div v-if="selected" class="practice">
        <header class="practice__head">
          <button
            class="practice__close"
            type="button"
            aria-label="关闭"
            @click="drawerOpen = false"
          >
            ×
          </button>
          <div class="practice__tags">
            <span class="pill pill--primary">{{ mode === 'fix' ? '补一句' : '变体复查' }}</span>
            <span class="pill" :class="`pill--status-${statusMeta(selected).tone}`">
              {{ statusMeta(selected).label }}
            </span>
          </div>
          <h2>{{ selected.topic }}</h2>
          <p class="practice__sub">
            {{
              mode === 'fix'
                ? '只补缺的那一条，不用重答整道题'
                : '换了一道题，重点看这条缺口还在不在'
            }}
          </p>
        </header>

        <div class="practice__body">
          <div class="block block--gap">
            <p class="block__label">这次只补这一点</p>
            <p class="block__text">{{ selected.gap_point || '未记录具体缺口' }}</p>
          </div>

          <div
            v-if="mode === 'fix' && (card?.source?.quote || card?.source?.answer)"
            class="block block--quote"
          >
            <p class="block__label">上次你是这么说的</p>
            <p class="block__text">
              {{ shortText(card.source.quote || card.source.answer, 200) }}
            </p>
          </div>

          <div v-if="mode === 'review'" class="block">
            <p class="block__label">复查题</p>
            <p class="block__text">
              {{
                card?.review_question?.title ||
                `换个场景：如果项目里要用到「${selected.topic}」，你会怎么讲清这一点？`
              }}
            </p>
          </div>

          <el-input
            v-model="answer"
            type="textarea"
            :rows="5"
            maxlength="2000"
            show-word-limit
            resize="none"
            :placeholder="
              mode === 'fix'
                ? '用 1-3 句话把这一点补上…'
                : '不看原文，用自己的话讲一遍…'
            "
          />

          <div class="practice__actions">
            <span class="practice__hint">判卷只看这一条缺口，不重判整题</span>
            <el-button type="primary" :loading="submitting" @click="submit">
              {{ mode === 'fix' ? '提交补法' : '提交复查' }}
            </el-button>
          </div>

          <div v-if="result" class="result">
            <div class="result__head">
              <span
                class="pill"
                :class="result.gap_covered ? 'pill--accent' : 'pill--sev-high'"
              >
                {{ result.gap_covered ? '这条补上了' : '还没补到点上' }}
              </span>
              <span class="result__verdict">{{ verdictLabel(result.judgement.verdict) }}</span>
            </div>
            <p class="result__message">{{ result.message }}</p>

            <div v-if="result.mode === 'fix'" class="result__diff">
              <div>
                <p class="block__label">上次</p>
                <p class="result__text">
                  {{ shortText(result.before_answer || '（无原话记录）', 120) }}
                </p>
              </div>
              <el-icon class="result__arrow"><ArrowRight /></el-icon>
              <div>
                <p class="block__label">这次</p>
                <p class="result__text">{{ shortText(result.after_answer, 120) }}</p>
              </div>
            </div>

            <p v-if="result.judgement.feedback" class="result__feedback">
              {{ result.judgement.feedback }}
            </p>
            <p v-if="result.weak_point.next_review_at" class="result__next">
              下次复查：{{ formatDate(result.weak_point.next_review_at) }} · 第
              {{ result.weak_point.review_stage }} 阶段
            </p>
          </div>
        </div>

        <footer class="practice__foot">
          <span class="practice__foot-hint">
            {{
              mode === 'fix'
                ? '通过后 1 天复查，之后按记忆曲线拉长（最长 30 天）'
                : '通过后进入下一间隔；忘了就回到待修复'
            }}
          </span>
          <el-button @click="drawerOpen = false">关闭</el-button>
        </footer>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
}

.stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 16px 20px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow-card);
}

.stat__label {
  font-size: 11.5px;
  color: var(--ink-3);
}

.stat__value {
  font-size: 27px;
  font-weight: 680;
  letter-spacing: -0.035em;
  line-height: 1.2;
  color: var(--ink);
}

.stat__value small {
  margin-left: 3px;
  font-size: 11.5px;
  font-weight: 500;
  color: var(--ink-3);
}

.stat__hint {
  font-size: 10.5px;
  color: var(--ink-4);
}

.grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 18px;
  margin-top: 18px;
  align-items: start;
}

.span-7 {
  grid-column: span 7;
}

.span-5 {
  grid-column: span 5;
}

.state {
  padding: 18px 0;
  font-size: 12px;
  color: var(--ink-3);
}

.state--error {
  color: #b03e3d;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding: 26px 20px;
  border: 1px dashed var(--line-strong);
  border-radius: 12px;
  background: var(--surface-2);
}

.empty__title {
  font-size: 13px;
  font-weight: 650;
  color: var(--ink);
}

.empty__desc {
  max-width: 460px;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--ink-3);
}

.group + .group {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px dashed var(--line);
}

.group__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.group__head h3 {
  font-size: 12.5px;
  font-weight: 650;
  color: var(--ink);
}

.group__count {
  padding: 0 6px;
  border-radius: 5px;
  background: var(--surface-3);
  font-size: 10.5px;
  color: var(--ink-2);
}

.group__hint {
  margin-left: auto;
  font-size: 10.5px;
  color: var(--ink-4);
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.dot--warn {
  background: #d8a12c;
}

.dot--accent {
  background: var(--accent);
}

.rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid transparent;
  border-radius: 11px;
  background: var(--surface-2);
  cursor: pointer;
  transition: border-color 0.16s ease, background-color 0.16s ease;
}

.row:hover {
  border-color: var(--line-strong);
  background: #fff;
}

.row.is-active {
  border-color: #d9d7f7;
  background: #fbfaff;
}

.row__body {
  flex: 1;
  min-width: 0;
}

.row__top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.row__topic {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink);
}

.row__gap {
  margin-top: 3px;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--ink-2);
}

.row__meta {
  margin-top: 2px;
  font-size: 10.5px;
  color: var(--ink-4);
}

.pill--sev-high {
  background: var(--danger-soft);
  color: #b03e3d;
}

.pill--sev-medium {
  background: var(--warn-soft);
  color: #96600f;
}

.pill--sev-low {
  background: var(--surface-3);
  color: var(--ink-2);
}

.pill--status-warn {
  background: var(--warn-soft);
  color: #96600f;
}

.pill--status-accent {
  background: var(--accent-soft);
  color: #0b7269;
}

.pill--status-success {
  background: var(--accent-soft);
  color: #0b7269;
}

.resolved {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px dashed var(--line);
}

.resolved__toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 0;
  border: none;
  background: none;
  font-size: 11.5px;
  color: var(--ink-3);
  cursor: pointer;
}

.resolved__toggle span {
  margin-left: auto;
  color: var(--ink-4);
}

.resolved__list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.resolved__list li {
  display: flex;
  align-items: baseline;
  gap: 10px;
  font-size: 11px;
  color: var(--ink-3);
}

.resolved__topic {
  min-width: 120px;
  color: var(--ink-2);
}

.gapcard__top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.gapcard__top h3 {
  font-size: 15px;
  letter-spacing: -0.02em;
}

.block {
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--surface-2);
  border: 1px solid var(--line);
}

.block + .block {
  margin-top: 8px;
}

.block--quote {
  background: #fbfaff;
  border-color: #e6e3fb;
}

.block--gap {
  background: var(--warn-soft);
  border-color: #f0dcc0;
}

.block__label {
  font-size: 10px;
  font-weight: 650;
  letter-spacing: 0.06em;
  color: var(--ink-4);
  margin-bottom: 4px;
}

.block__text {
  font-size: 12px;
  line-height: 1.7;
  color: var(--ink-2);
}

.block__meta {
  margin-top: 4px;
  font-size: 10px;
  color: var(--ink-4);
}

.gapcard__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 12px;
}

.gapcard__hint {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10.5px;
  color: var(--ink-4);
}

.practice {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.practice__head {
  position: relative;
  padding: 24px 56px 16px 26px;
  border-bottom: 1px solid var(--line);
  background: linear-gradient(180deg, #fbfaff, #fff);
}

.practice__close {
  position: absolute;
  top: 18px;
  right: 18px;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--ink-3);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
}

.practice__tags {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

.practice__head h2 {
  font-size: 18px;
  letter-spacing: -0.02em;
}

.practice__sub {
  margin-top: 4px;
  font-size: 11.5px;
  color: var(--ink-3);
}

.practice__body {
  flex: 1;
  overflow-y: auto;
  padding: 20px 26px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.practice__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.practice__hint {
  font-size: 10.5px;
  color: var(--ink-4);
}

.practice__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 26px;
  border-top: 1px solid var(--line);
  background: #fff;
}

.practice__foot-hint {
  font-size: 10.5px;
  color: var(--ink-3);
}

.result {
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: var(--surface-2);
}

.result__head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.result__verdict {
  font-size: 10.5px;
  color: var(--ink-4);
}

.result__message {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--ink-2);
}

.result__diff {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--line);
}

.result__text {
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--ink-2);
}

.result__arrow {
  color: var(--ink-4);
}

.result__feedback {
  margin-top: 8px;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--ink-3);
}

.result__next {
  margin-top: 6px;
  font-size: 10.5px;
  color: var(--ink-4);
}

@media (max-width: 1080px) {
  .span-7,
  .span-5 {
    grid-column: span 12;
  }
}

@media (max-width: 720px) {
  .stats {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .stat {
    flex-direction: row;
    align-items: baseline;
    justify-content: space-between;
    flex-wrap: wrap;
    padding: 12px 16px;
  }

  .row {
    flex-wrap: wrap;
  }

  .result__diff {
    grid-template-columns: 1fr;
  }

  .result__arrow {
    display: none;
  }
}
</style>
