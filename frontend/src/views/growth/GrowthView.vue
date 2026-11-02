<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowRight, Check, Reading } from '@element-plus/icons-vue'

import PageHeader from '@/components/PageHeader.vue'
import SectionCard from '@/components/SectionCard.vue'
import { SEVERITY_META, WEAK_SEVERITY_WEIGHT, WEAK_SOURCE_LABELS } from '@/constants'

/* ---------------- 演示数据 ---------------- */

const weakPoints = ref([
  {
    id: 1,
    topic: 'MySQL 联合索引与最左前缀',
    severity: 'high',
    source: 'interview',
    relapse: 3,
    mastery: 35,
    resolved: false,
    tags: ['MySQL', '索引'],
  },
  {
    id: 2,
    topic: '缓存穿透 / 击穿 / 雪崩',
    severity: 'high',
    source: 'interview',
    relapse: 2,
    mastery: 42,
    resolved: false,
    tags: ['Redis', '缓存'],
  },
  {
    id: 3,
    topic: '分布式事务与最终一致性',
    severity: 'medium',
    source: 'interview',
    relapse: 1,
    mastery: 58,
    resolved: false,
    tags: ['事务', '一致性'],
  },
  {
    id: 4,
    topic: 'HTTP 与 TCP 的连接复用',
    severity: 'medium',
    source: 'self_test',
    relapse: 1,
    mastery: 61,
    resolved: false,
    tags: ['网络'],
  },
  {
    id: 5,
    topic: 'JVM 垃圾回收与调优',
    severity: 'low',
    source: 'self_test',
    relapse: 0,
    mastery: 72,
    resolved: false,
    tags: ['JVM'],
  },
])

const EXERCISES = {
  1: [
    { title: '联合索引的列顺序怎么定？', type: '概念讲解', minutes: 8, tags: ['索引', '最左前缀'] },
    { title: '回表与覆盖索引：把过滤压进索引层', type: '概念讲解', minutes: 10, tags: ['覆盖索引'] },
    { title: '场景题：为订单列表设计一个索引', type: '场景练习', minutes: 12, tags: ['索引设计'] },
  ],
  2: [
    { title: '三种缓存异常的区别与应对', type: '概念讲解', minutes: 9, tags: ['缓存', 'Redis'] },
    { title: '布隆过滤器与空值缓存的取舍', type: '概念讲解', minutes: 7, tags: ['布隆过滤器'] },
    { title: '场景题：热点 key 失效后的 30 秒', type: '场景练习', minutes: 12, tags: ['热点 key'] },
  ],
  3: [
    { title: '2PC、TCC 与本地消息表', type: '概念讲解', minutes: 11, tags: ['分布式事务'] },
    { title: '场景题：订单与库存如何最终一致', type: '场景练习', minutes: 14, tags: ['一致性'] },
  ],
  4: [
    { title: 'Keep-Alive 到底省掉了什么', type: '概念讲解', minutes: 6, tags: ['HTTP', 'TCP'] },
    { title: 'HTTP/2 多路复用的边界', type: '概念讲解', minutes: 8, tags: ['HTTP/2'] },
  ],
  5: [
    { title: 'G1 与 CMS 的取舍', type: '概念讲解', minutes: 10, tags: ['JVM', 'GC'] },
    { title: '一次 Full GC 的排查路径', type: '场景练习', minutes: 12, tags: ['调优'] },
  ],
}

const PRACTICE_CONTENT = {
  1: {
    intro: [
      '联合索引在 B+ 树里按「列顺序」逐级排序，因此查询条件必须从最左列开始连续匹配，才能用上索引的有序性<sup class="cite">[1]</sup>。',
      '更关键的是回表成本：二级索引叶子节点只存主键，索引列之外的字段必须回到聚簇索引再查一次。把过滤条件全部放进索引，才能把回表次数压到最低<sup class="cite">[2]</sup>。',
    ],
    question: '不看上文，用三句话讲清：为什么 (user_id, status, created_at) 能优化订单列表查询，而三个独立索引不行？',
    sources: [
      { idx: 1, title: 'MySQL 索引原理 · 联合索引与最左前缀', meta: '知识库文档 · KB #1024' },
      { idx: 2, title: '内部题库 · 回表与覆盖索引', meta: '知识库文档 · KB #1187' },
    ],
  },
  2: {
    intro: [
      '穿透是查不存在的数据，请求绕过缓存直达数据库；击穿是单个热点 key 失效瞬间的并发冲击；雪崩是大量 key 同时失效<sup class="cite">[1]</sup>。',
      '三者的应对并不通用：穿透适合空值缓存或布隆过滤器，击穿适合互斥锁或逻辑过期，雪崩靠过期时间打散与多级缓存兜底<sup class="cite">[2]</sup>。',
    ],
    question: '用三句话说明：击穿和雪崩的差别，以及各自的第一道防线。',
    sources: [
      { idx: 1, title: 'Redis 缓存设计 · 三类异常', meta: '知识库文档 · KB #1102' },
      { idx: 2, title: '内部题库 · 热点 key 与互斥重建', meta: '知识库文档 · KB #1156' },
    ],
  },
}

const DEFAULT_CONTENT = {
  intro: [
    '这个知识点在面试里通常从「为什么需要它」和「边界情况怎么处理」两个方向追问，背结论很难通过，讲清取舍才行。',
    '先用自己的项目场景复述一遍，再对照来源核对细节，掌握度会随复述质量更新。',
  ],
  question: '不看上文，用三句话讲清这个知识点的核心取舍。',
  sources: [{ idx: 1, title: '知识库 · 相关知识点整理', meta: '知识库文档' }],
}

/* ---------------- 状态 ---------------- */

const selectedId = ref(1)
const drawerOpen = ref(false)
const practiceFor = ref(null)
const practiceAnswer = ref('')
const judgement = ref(null)
const judging = ref(false)

const activePoints = computed(() => weakPoints.value.filter((item) => !item.resolved))

const sortedPoints = computed(() =>
  [...weakPoints.value].sort((a, b) => {
    if (a.resolved !== b.resolved) return a.resolved ? 1 : -1
    const weight = WEAK_SEVERITY_WEIGHT[b.severity] - WEAK_SEVERITY_WEIGHT[a.severity]
    if (weight !== 0) return weight
    return b.relapse - a.relapse
  }),
)

const stats = computed(() => {
  const active = activePoints.value
  const avg = active.length
    ? Math.round(active.reduce((sum, item) => sum + item.mastery, 0) / active.length)
    : 0
  return { active: active.length, avg, weekly: 12 }
})

const selectedPoint = computed(
  () => weakPoints.value.find((item) => item.id === selectedId.value) || activePoints.value[0],
)

const recommendations = computed(() => EXERCISES[selectedPoint.value?.id] || [])

const content = computed(() => PRACTICE_CONTENT[practiceFor.value?.id] || DEFAULT_CONTENT)

function selectPoint(point) {
  selectedId.value = point.id
}

function openPractice(point) {
  practiceFor.value = point
  selectedId.value = point.id
  practiceAnswer.value = ''
  judgement.value = null
  drawerOpen.value = true
}

function judgeAnswer() {
  if (!practiceAnswer.value.trim()) {
    ElMessage.warning('先写下你的复述')
    return
  }
  judging.value = true
  setTimeout(() => {
    judging.value = false
    judgement.value = {
      verdict: 'partial',
      hits: ['用到了「有序性」这个关键前提', '提到了回表的成本来源'],
      misses: ['没有给出覆盖索引这个补救手段', '缺少一个具体查询例子'],
    }
  }, 900)
}

function markMastered() {
  const point = practiceFor.value
  if (!point) return
  const target = weakPoints.value.find((item) => item.id === point.id)
  if (target) {
    target.mastery = 100
    target.resolved = true
  }
  ElMessage.success('已标记为掌握，掌握度更新为 100%')
  drawerOpen.value = false
}

function meterTone(mastery) {
  if (mastery >= 70) return 'meter__fill--accent'
  if (mastery >= 50) return 'meter__fill--warn'
  return 'meter__fill--danger'
}
</script>

<template>
  <div class="page">
    <PageHeader
      eyebrow="Growth Loop"
      title="成长闭环"
      subtitle="薄弱点来自模拟面试与自测，按严重度和复发次数排序。练习判卷只更新掌握度，不新增薄弱点。"
    >
      <template #actions>
        <el-button type="primary" plain :icon="Reading" @click="openPractice(selectedPoint)">
          继续上次练习
        </el-button>
      </template>
    </PageHeader>

    <div class="stats">
      <div class="stat">
        <span class="stat__label">待攻克薄弱点</span>
        <span class="stat__value num">{{ stats.active }}<small>个</small></span>
        <span class="stat__hint">高优先级 {{ activePoints.filter((p) => p.severity === 'high').length }} 个</span>
      </div>
      <div class="stat">
        <span class="stat__label">平均掌握度</span>
        <span class="stat__value num">{{ stats.avg }}<small>%</small></span>
        <span class="stat__hint">练习后自动更新</span>
      </div>
      <div class="stat">
        <span class="stat__label">近 7 天练习</span>
        <span class="stat__value num">{{ stats.weekly }}<small>次</small></span>
        <span class="stat__hint">复述判卷 8 次 · 概念阅读 4 次</span>
      </div>
    </div>

    <div class="grid">
      <SectionCard class="span-8" title="薄弱点" subtitle="按严重度 × 复发次数排序，越靠前越该先补">
        <template #extra>
          <span class="pill pill--outline">{{ sortedPoints.length }} 条</span>
        </template>

        <ul class="weak-list">
          <li
            v-for="point in sortedPoints"
            :key="point.id"
            class="weak"
            :class="{ 'is-active': selectedId === point.id, 'is-resolved': point.resolved }"
            @click="selectPoint(point)"
          >
            <span class="weak__bar" :class="`weak__bar--${point.resolved ? 'done' : point.severity}`" />

            <div class="weak__body">
              <div class="weak__top">
                <p class="weak__topic">{{ point.topic }}</p>
                <span v-if="point.resolved" class="pill pill--accent">已掌握</span>
                <span v-else class="pill" :class="`pill--sev-${point.severity}`">
                  {{ SEVERITY_META[point.severity].label }}
                </span>
              </div>

              <p class="weak__meta">
                复发 <strong class="num">{{ point.relapse }}</strong> 次
                <span class="weak__dot">·</span>
                来自{{ WEAK_SOURCE_LABELS[point.source] }}
                <span class="weak__dot">·</span>
                {{ point.tags.join(' / ') }}
              </p>

              <div class="weak__meter">
                <div class="meter">
                  <div
                    class="meter__fill"
                    :class="point.resolved ? 'meter__fill--accent' : meterTone(point.mastery)"
                    :style="{ width: `${point.mastery}%` }"
                  />
                </div>
                <span class="weak__pct num">{{ point.mastery }}%</span>
              </div>
            </div>

            <el-button size="small" plain class="weak__cta" @click.stop="openPractice(point)">
              {{ point.resolved ? '复习' : '去练习' }}
            </el-button>
          </li>
        </ul>

        <p class="weak-note">
          掌握度由练习表现持续更新；标记已掌握后移出待攻克列表，再次复发会重新打开。
        </p>
      </SectionCard>

      <SectionCard
        class="span-4"
        title="推荐练习"
        :subtitle="selectedPoint ? `针对「${selectedPoint.topic}」` : '选择左侧薄弱点查看'"
      >
        <div v-if="selectedPoint" class="recommend">
          <div class="recommend__head">
            <span class="pill" :class="`pill--sev-${selectedPoint.severity}`">
              {{ SEVERITY_META[selectedPoint.severity].label }}
            </span>
            <span class="recommend__mastery">
              当前掌握度 <strong class="num">{{ selectedPoint.mastery }}%</strong>
            </span>
          </div>

          <ul class="exercise-list">
            <li
              v-for="(exercise, index) in recommendations"
              :key="exercise.title"
              class="exercise"
              @click="openPractice(selectedPoint)"
            >
              <span class="exercise__idx num">{{ String(index + 1).padStart(2, '0') }}</span>
              <div class="exercise__body">
                <p class="exercise__title">{{ exercise.title }}</p>
                <p class="exercise__meta">
                  <span>{{ exercise.type }}</span>
                  <span class="weak__dot">·</span>
                  <span>{{ exercise.minutes }} 分钟</span>
                </p>
                <div class="exercise__tags">
                  <span v-for="tag in exercise.tags" :key="tag" class="exercise__tag">{{ tag }}</span>
                </div>
              </div>
              <el-icon class="exercise__arrow"><ArrowRight /></el-icon>
            </li>
          </ul>

          <el-button type="primary" class="recommend__cta" @click="openPractice(selectedPoint)">
            打开练习视图
          </el-button>

          <p class="recommend__note">
            练习讲解带来源引用，便于核对依据；复述判卷只更新掌握度。
          </p>
        </div>

        <p v-else class="muted recommend__empty">暂无可推荐练习。</p>
      </SectionCard>
    </div>

    <!-- 练习视图 -->
    <el-drawer
      v-model="drawerOpen"
      size="520px"
      :with-header="false"
      class="practice-drawer"
      destroy-on-close
    >
      <div v-if="practiceFor" class="practice">
        <header class="practice__head">
          <button class="practice__close" type="button" aria-label="关闭练习视图" @click="drawerOpen = false">
            <svg viewBox="0 0 16 16" width="14" height="14" fill="none" aria-hidden="true">
              <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
            </svg>
          </button>
          <div class="practice__tags">
            <span class="pill pill--primary">练习视图</span>
            <span class="pill" :class="`pill--sev-${practiceFor.severity}`">
              {{ SEVERITY_META[practiceFor.severity].label }}
            </span>
          </div>
          <h2>{{ practiceFor.topic }}</h2>
          <div class="practice__progress">
            <span>掌握度</span>
            <div class="meter">
              <div
                class="meter__fill"
                :class="meterTone(practiceFor.mastery)"
                :style="{ width: `${practiceFor.mastery}%` }"
              />
            </div>
            <strong class="num">{{ practiceFor.mastery }}%</strong>
          </div>
        </header>

        <div class="practice__body">
          <section class="practice__section">
            <h3 class="practice__title">先讲清楚</h3>
            <p v-for="(para, index) in content.intro" :key="index" class="practice__para" v-html="para" />

            <div class="sources">
              <p class="sources__label">来源</p>
              <ul>
                <li v-for="source in content.sources" :key="source.idx">
                  <span class="sources__idx num">[{{ source.idx }}]</span>
                  <div>
                    <p class="sources__title">{{ source.title }}</p>
                    <p class="sources__meta">{{ source.meta }}</p>
                  </div>
                </li>
              </ul>
            </div>
          </section>

          <section class="practice__section">
            <h3 class="practice__title">复述一下</h3>
            <p class="practice__prompt">{{ content.question }}</p>
            <el-input
              v-model="practiceAnswer"
              type="textarea"
              :rows="4"
              maxlength="300"
              show-word-limit
              resize="none"
              placeholder="不用回看上文，用自己的话讲一遍…"
            />

            <div class="practice__actions">
              <span class="practice__hint">判卷结论复用面试的三档 verdict</span>
              <el-button size="small" type="primary" plain :loading="judging" @click="judgeAnswer">
                提交复述
              </el-button>
            </div>

            <transition name="fade">
              <div v-if="judgement" class="judge">
                <div class="judge__head">
                  <span class="pill pill--warn">基本到位</span>
                  <span class="judge__label">复述反馈</span>
                </div>
                <div class="judge__grid">
                  <div>
                    <p class="judge__title judge__title--hit">讲到了</p>
                    <ul>
                      <li v-for="hit in judgement.hits" :key="hit">{{ hit }}</li>
                    </ul>
                  </div>
                  <div>
                    <p class="judge__title judge__title--miss">还差</p>
                    <ul>
                      <li v-for="miss in judgement.misses" :key="miss">{{ miss }}</li>
                    </ul>
                  </div>
                </div>
              </div>
            </transition>
          </section>
        </div>

        <footer class="practice__foot">
          <span class="practice__foot-hint">掌握后可移出待攻克列表</span>
          <el-button type="primary" :icon="Check" @click="markMastered">标记已掌握</el-button>
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

.grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 18px;
  margin-top: 18px;
  align-items: start;
}

.span-8 {
  grid-column: span 8;
}

.span-4 {
  grid-column: span 4;
}

/* ---------------- 概览 ---------------- */
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

/* ---------------- 薄弱点列表 ---------------- */
.weak-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.weak {
  position: relative;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px 14px 18px;
  border-radius: 12px;
  border: 1px solid transparent;
  background: var(--surface-2);
  cursor: pointer;
  transition: border-color 0.16s ease, background-color 0.16s ease;
}

.weak:hover {
  border-color: var(--line-strong);
  background: #fff;
}

.weak.is-active {
  border-color: #d9d7f7;
  background: #fbfaff;
}

.weak.is-resolved {
  opacity: 0.62;
}

.weak__bar {
  position: absolute;
  left: 0;
  top: 14px;
  bottom: 14px;
  width: 3px;
  border-radius: 0 3px 3px 0;
}

.weak__bar--high {
  background: var(--danger);
}

.weak__bar--medium {
  background: #d8a12c;
}

.weak__bar--low {
  background: var(--accent);
}

.weak__bar--done {
  background: var(--line-strong);
}

.weak__body {
  flex: 1;
  min-width: 0;
}

.weak__top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.weak__topic {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
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

.weak__meta {
  margin-top: 4px;
  font-size: 11px;
  color: var(--ink-3);
}

.weak__meta strong {
  color: var(--ink-2);
  font-weight: 600;
}

.weak__dot {
  margin: 0 5px;
  color: var(--ink-4);
}

.weak__meter {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-top: 9px;
  max-width: 340px;
}

.weak__meter .meter {
  flex: 1;
}

.weak__pct {
  flex: none;
  width: 32px;
  text-align: right;
  font-size: 10.5px;
  color: var(--ink-3);
}

.weak__cta {
  flex: none;
}

.weak-note {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed var(--line);
  font-size: 11px;
  line-height: 1.65;
  color: var(--ink-3);
}

/* ---------------- 推荐练习 ---------------- */
.recommend__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.recommend__mastery {
  font-size: 11px;
  color: var(--ink-3);
}

.recommend__mastery strong {
  color: var(--ink-2);
}

.exercise-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.exercise {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 11px 12px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: var(--surface-2);
  cursor: pointer;
  transition: border-color 0.16s ease, background-color 0.16s ease;
}

.exercise:hover {
  border-color: #d9d7f7;
  background: #fff;
}

.exercise__idx {
  font-size: 10px;
  color: var(--ink-4);
  padding-top: 3px;
}

.exercise__body {
  flex: 1;
  min-width: 0;
}

.exercise__title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink);
  line-height: 1.5;
}

.exercise__meta {
  margin-top: 3px;
  font-size: 10.5px;
  color: var(--ink-3);
}

.exercise__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 7px;
}

.exercise__tag {
  padding: 1px 7px;
  border-radius: 5px;
  background: var(--surface-3);
  font-size: 10px;
  color: var(--ink-3);
}

.exercise__arrow {
  flex: none;
  font-size: 12px;
  color: var(--ink-4);
  margin-top: 4px;
}

.recommend__cta {
  width: 100%;
  margin-top: 14px;
}

.recommend__note {
  margin-top: 10px;
  font-size: 10.5px;
  line-height: 1.6;
  color: var(--ink-3);
}

.recommend__empty {
  font-size: 12.5px;
  padding: 20px 0;
}

/* ---------------- 练习抽屉 ---------------- */
.practice {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 100%;
}

.practice__head {
  position: relative;
  padding: 26px 60px 18px 26px;
  border-bottom: 1px solid var(--line);
  background: linear-gradient(180deg, #fbfaff, #fff);
}

.practice__close {
  position: absolute;
  top: 20px;
  right: 20px;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--ink-3);
  cursor: pointer;
  transition: color 0.16s ease, border-color 0.16s ease;
}

.practice__close:hover {
  color: var(--ink);
  border-color: var(--line-strong);
}

.practice__tags {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}

.practice__head h2 {
  font-size: 19px;
  letter-spacing: -0.025em;
  line-height: 1.4;
}

.practice__progress {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  font-size: 11px;
  color: var(--ink-3);
}

.practice__progress .meter {
  flex: 1;
  max-width: 220px;
}

.practice__progress strong {
  color: var(--ink-2);
  font-size: 11.5px;
}

.practice__body {
  flex: 1;
  overflow-y: auto;
  padding: 22px 26px 26px;
  display: flex;
  flex-direction: column;
  gap: 26px;
}

.practice__title {
  font-size: 13px;
  font-weight: 650;
  letter-spacing: 0.01em;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.practice__title::before {
  content: '';
  width: 3px;
  height: 12px;
  border-radius: 2px;
  background: var(--primary);
}

.practice__para {
  font-size: 13px;
  line-height: 1.9;
  color: var(--ink-2);
}

.practice__para + .practice__para {
  margin-top: 8px;
}

.practice__para :deep(.cite) {
  font-size: 9.5px;
  font-weight: 650;
  color: var(--primary);
  vertical-align: super;
  line-height: 0;
  margin-left: 1px;
}

.sources {
  margin-top: 16px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px dashed var(--line-strong);
  background: var(--surface-2);
}

.sources__label {
  font-size: 10px;
  font-weight: 650;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-4);
  margin-bottom: 8px;
}

.sources li {
  display: flex;
  gap: 8px;
  padding: 4px 0;
}

.sources__idx {
  flex: none;
  font-size: 10px;
  color: var(--primary);
  padding-top: 1px;
}

.sources__title {
  font-size: 11.5px;
  color: var(--ink-2);
}

.sources__meta {
  font-size: 10px;
  color: var(--ink-4);
  margin-top: 1px;
}

.practice__prompt {
  font-size: 12px;
  line-height: 1.7;
  color: var(--ink-2);
  padding: 10px 12px;
  border-radius: 9px;
  background: var(--primary-soft);
  margin-bottom: 12px;
}

.practice__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
}

.practice__hint {
  font-size: 10.5px;
  color: var(--ink-4);
}

.judge {
  margin-top: 14px;
  padding: 14px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: var(--surface-2);
}

.judge__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.judge__label {
  font-size: 10.5px;
  color: var(--ink-4);
}

.judge__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.judge__title {
  font-size: 10.5px;
  font-weight: 650;
  margin-bottom: 5px;
}

.judge__title--hit {
  color: #0b7269;
}

.judge__title--miss {
  color: #96600f;
}

.judge__grid li {
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--ink-2);
  padding-left: 9px;
  position: relative;
}

.judge__grid li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--ink-4);
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

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

@media (max-width: 1080px) {
  .span-8,
  .span-4 {
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

  .stat__value {
    font-size: 22px;
  }

  .stat__hint {
    display: none;
  }

  .weak {
    flex-wrap: wrap;
  }

  .weak__cta {
    width: 100%;
  }

  .practice__head {
    padding: 22px 56px 16px 18px;
  }

  .practice__body,
  .practice__foot {
    padding-left: 18px;
    padding-right: 18px;
  }

  .judge__grid {
    grid-template-columns: 1fr;
    gap: 10px;
  }
}
</style>
