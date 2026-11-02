<script setup>
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'

import EmptyState from '@/components/EmptyState.vue'
import PageHeader from '@/components/PageHeader.vue'
import SectionCard from '@/components/SectionCard.vue'
import { RETRIEVAL_PARAMS, SEARCH_MODES } from '@/constants'

/* ---------------- 演示数据 ---------------- */

const VECTOR_HITS = [
  { title: '联合索引的最左前缀与回表成本', doc: 'MySQL 索引原理 · §3.2', score: 0.91 },
  { title: '为什么 MySQL 会选错索引', doc: '慢查询治理 · §1.4', score: 0.87 },
  { title: 'B+ 树与哈希索引的适用边界', doc: 'MySQL 索引原理 · §1.1', score: 0.83 },
  { title: '覆盖索引能省掉哪一次 IO', doc: 'MySQL 索引原理 · §3.5', score: 0.79 },
  { title: 'Redis 缓存穿透的三种解法', doc: 'Redis 实战 · §4.1', score: 0.71 },
]

const BM25_HITS = [
  { title: '覆盖索引能省掉哪一次 IO', doc: 'MySQL 索引原理 · §3.5', score: 11.3 },
  { title: '慢查询日志与执行计划', doc: '慢查询治理 · §2.2', score: 9.8 },
  { title: '联合索引的最左前缀与回表成本', doc: 'MySQL 索引原理 · §3.2', score: 8.42 },
  { title: '为什么 MySQL 会选错索引', doc: '慢查询治理 · §1.4', score: 8.1 },
  { title: 'Redis 缓存穿透的三种解法', doc: 'Redis 实战 · §4.1', score: 7.9 },
]

const FUSED = [
  { title: '联合索引的最左前缀与回表成本', v: 1, b: 3, rrf: 0.0308, final: 1, delta: 'up' },
  { title: '为什么 MySQL 会选错索引', v: 2, b: 4, rrf: 0.0301, final: 2, delta: 'up' },
  { title: '覆盖索引能省掉哪一次 IO', v: 4, b: 1, rrf: 0.0296, final: 3, delta: 'up' },
  { title: 'Redis 缓存穿透的三种解法', v: 5, b: 5, rrf: 0.0221, final: 4, delta: 'down' },
  { title: 'B+ 树与哈希索引的适用边界', v: 3, b: 7, rrf: 0.0212, final: 5, delta: 'same' },
  { title: '慢查询日志与执行计划', v: 9, b: 2, rrf: 0.0198, final: 6, delta: 'down' },
]

const ABLATION = [
  { label: '纯向量', value: 0.62, tone: 'vector' },
  { label: '纯 BM25', value: 0.55, tone: 'bm25' },
  { label: '混合 + RRF + Rerank', value: 0.78, tone: 'hybrid' },
]

const EXAMPLES = ['MySQL 联合索引最左前缀', 'Redis 缓存穿透怎么处理', 'TCP 三次握手为什么不是两次']

/* ---------------- 状态 ---------------- */

const mode = ref('hybrid')
const query = ref('')
const loading = ref(false)
const searched = ref(false)

const elapsed = reactive({ vector: 18, bm25: 6, fusion: 2, rerank: 96, total: 128 })

const vectorActive = computed(() => mode.value !== 'bm25')
const bm25Active = computed(() => mode.value !== 'vector')

const maxVector = Math.max(...VECTOR_HITS.map((item) => item.score))
const maxBm25 = Math.max(...BM25_HITS.map((item) => item.score))

const modeLabel = computed(
  () => SEARCH_MODES.find((item) => item.value === mode.value)?.label || mode.value,
)

function barWidth(value, max) {
  return `${Math.round((value / max) * 100)}%`
}

function useExample(text) {
  query.value = text
  runSearch()
}

function runSearch() {
  if (!query.value.trim()) {
    ElMessage.warning('请输入一个查询问题')
    return
  }
  loading.value = true
  setTimeout(() => {
    loading.value = false
    searched.value = true
  }, 620)
}

function deltaLabel(delta) {
  return { up: '上升', down: '下降', same: '持平' }[delta]
}
</script>

<template>
  <div class="page">
    <PageHeader
      eyebrow="Retrieval Lab"
      title="检索调试台"
      subtitle="真实用户不可见的工具页：双路召回、RRF 融合与消融数字，用来回答「混合检索为什么存在」。"
    >
      <template #actions>
        <span class="pill pill--outline">仅开发者可见</span>
      </template>
    </PageHeader>

    <SectionCard class="query-card">
      <div class="query">
        <el-input
          v-model="query"
          size="large"
          placeholder="输入一个面试问题，例如：MySQL 联合索引为什么要遵循最左前缀？"
          clearable
          @keyup.enter="runSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button type="primary" size="large" :loading="loading" @click="runSearch">检索</el-button>
      </div>

      <div class="query__row">
        <el-radio-group v-model="mode" size="small" class="modes">
          <el-radio-button v-for="item in SEARCH_MODES" :key="item.value" :value="item.value">
            {{ item.label }}
          </el-radio-button>
        </el-radio-group>

        <div class="params">
          <span v-for="param in RETRIEVAL_PARAMS" :key="param.key" class="param">
            <span class="param__key">{{ param.key }}</span>
            <span class="param__value num">{{ param.value }}</span>
          </span>
        </div>
      </div>
    </SectionCard>

    <SectionCard v-if="!searched" class="empty-card">
      <EmptyState
        title="输入问题，查看两路召回如何互补"
        description="建议从示例问题开始：观察同一份文档在向量与 BM25 下的名次差异，以及 RRF 融合后的排序变化。"
      >
        <div class="examples">
          <button v-for="text in EXAMPLES" :key="text" class="example" type="button" @click="useExample(text)">
            {{ text }}
          </button>
        </div>
      </EmptyState>
    </SectionCard>

    <template v-else>
      <div class="stats">
        <div class="stat">
          <span class="stat__label">总耗时</span>
          <span class="stat__value num">{{ elapsed.total }}<small>ms</small></span>
        </div>
        <div class="stat">
          <span class="stat__label">召回规模</span>
          <span class="stat__value num">50<small>× 2</small></span>
        </div>
        <div class="stat">
          <span class="stat__label">精排</span>
          <span class="stat__value num">Top 10</span>
        </div>
        <div class="stat">
          <span class="stat__label">当前模式</span>
          <span class="stat__value stat__value--text">{{ modeLabel }}</span>
        </div>
      </div>

      <div class="grid">
        <SectionCard
          class="span-6"
          title="向量召回"
          subtitle="Qdrant · bge-m3 · Top 5"
          :class="{ 'is-muted': !vectorActive }"
        >
          <template #extra>
            <span class="timing num">{{ elapsed.vector }} ms</span>
          </template>
          <p v-if="!vectorActive" class="disabled-note">当前模式未启用向量召回</p>
          <ul class="hits">
            <li v-for="(hit, index) in VECTOR_HITS" :key="hit.title" class="hit">
              <span class="hit__rank num">{{ index + 1 }}</span>
              <div class="hit__body">
                <p class="hit__title">{{ hit.title }}</p>
                <p class="hit__doc">{{ hit.doc }}</p>
                <div class="hit__bar">
                  <span :style="{ width: barWidth(hit.score, maxVector) }" />
                </div>
              </div>
              <span class="hit__score num">{{ hit.score.toFixed(2) }}</span>
            </li>
          </ul>
        </SectionCard>

        <SectionCard
          class="span-6"
          title="BM25 召回"
          subtitle="进程内 BM25 · jieba · Top 5"
          :class="{ 'is-muted': !bm25Active }"
        >
          <template #extra>
            <span class="timing num">{{ elapsed.bm25 }} ms</span>
          </template>
          <p v-if="!bm25Active" class="disabled-note">当前模式未启用稀疏召回</p>
          <ul class="hits">
            <li v-for="(hit, index) in BM25_HITS" :key="hit.title" class="hit">
              <span class="hit__rank num">{{ index + 1 }}</span>
              <div class="hit__body">
                <p class="hit__title">{{ hit.title }}</p>
                <p class="hit__doc">{{ hit.doc }}</p>
                <div class="hit__bar hit__bar--alt">
                  <span :style="{ width: barWidth(hit.score, maxBm25) }" />
                </div>
              </div>
              <span class="hit__score num">{{ hit.score.toFixed(1) }}</span>
            </li>
          </ul>
        </SectionCard>
      </div>

      <SectionCard
        class="fusion"
        title="RRF 融合"
        subtitle="名次取倒数加权，再用 reranker 精排前 10 条"
      >
        <template #extra>
          <span class="pill pill--soft">RRF_K = 60</span>
        </template>

        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th class="col-doc">文档</th>
                <th>向量名次</th>
                <th>BM25 名次</th>
                <th>融合分</th>
                <th>精排名次</th>
                <th>名次变化</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in FUSED" :key="row.title" :class="{ 'is-top': row.final <= 3 }">
                <td class="col-doc">
                  <span class="table__rank num">{{ row.final }}</span>
                  <span class="table__title">{{ row.title }}</span>
                </td>
                <td class="num" :class="{ 'is-off': !vectorActive }">{{ vectorActive ? `#${row.v}` : '—' }}</td>
                <td class="num" :class="{ 'is-off': !bm25Active }">{{ bm25Active ? `#${row.b}` : '—' }}</td>
                <td class="num">{{ row.rrf.toFixed(4) }}</td>
                <td class="num">#{{ row.final }}</td>
                <td>
                  <span class="delta" :class="`delta--${row.delta}`">
                    {{ row.delta === 'up' ? '↑' : row.delta === 'down' ? '↓' : '·' }}
                    {{ deltaLabel(row.delta) }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="fusion__foot">
          <span>总耗时 <strong class="num">{{ elapsed.total }}</strong> ms</span>
          <span class="fusion__sep" />
          <span>融合 <strong class="num">{{ elapsed.fusion }}</strong> ms</span>
          <span class="fusion__sep" />
          <span>精排 <strong class="num">{{ elapsed.rerank }}</strong> ms</span>
          <span class="fusion__note">精排只处理融合后的前 10 条，控制成本</span>
        </div>
      </SectionCard>

      <SectionCard class="ablation" title="检索消融" subtitle="Recall@5 · 标注问题集 · 来自评估流水线">
        <template #extra>
          <span class="pill pill--accent">混合最优</span>
        </template>

        <ul class="bars">
          <li v-for="item in ABLATION" :key="item.label" class="bar-row">
            <span class="bar-row__label">{{ item.label }}</span>
            <span class="bar-row__track">
              <i :class="`bar-row__fill--${item.tone}`" :style="{ width: `${item.value * 100}%` }" />
            </span>
            <span class="bar-row__value num">{{ item.value.toFixed(2) }}</span>
          </li>
        </ul>

        <p class="ablation__note">
          混合检索较纯向量提升 16 个百分点：BM25 补住了专有名词与代码符号的精确匹配，向量补住了同义改写。
        </p>
      </SectionCard>
    </template>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.query-card {
  position: relative;
}

.query {
  display: flex;
  gap: 12px;
}

.query__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.modes :deep(.el-radio-button__inner) {
  font-size: 12px;
  padding: 7px 14px;
}

.params {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.param {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  border-radius: 6px;
  background: var(--surface-2);
  border: 1px solid var(--line);
  font-size: 10px;
}

.param__key {
  font-family: var(--font-mono);
  color: var(--ink-3);
  letter-spacing: 0.01em;
}

.param__value {
  color: var(--ink-2);
  font-weight: 650;
}

.empty-card {
  min-height: 300px;
}

.examples {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

.example {
  border: 1px solid var(--line-strong);
  background: var(--surface);
  color: var(--ink-2);
  font-size: 11.5px;
  padding: 6px 12px;
  border-radius: 999px;
  cursor: pointer;
  transition: border-color 0.16s ease, color 0.16s ease, background-color 0.16s ease;
}

.example:hover {
  border-color: #b9b7ea;
  color: var(--primary-strong);
  background: var(--primary-soft);
}

/* ---------------- 概览 ---------------- */
.stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 13px 18px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow-card);
}

.stat__label {
  font-size: 10.5px;
  color: var(--ink-3);
}

.stat__value {
  font-size: 22px;
  font-weight: 650;
  letter-spacing: -0.03em;
  color: var(--ink);
}

.stat__value small {
  margin-left: 2px;
  font-size: 10.5px;
  font-weight: 500;
  color: var(--ink-3);
}

.stat__value--text {
  font-size: 16px;
  padding-top: 4px;
}

/* ---------------- 双路召回 ---------------- */
.grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 18px;
}

.span-6 {
  grid-column: span 6;
}

.is-muted :deep(.hits) {
  opacity: 0.4;
}

.timing {
  font-size: 10.5px;
  color: var(--ink-3);
  padding: 2px 7px;
  border-radius: 5px;
  background: var(--surface-3);
}

.disabled-note {
  font-size: 11px;
  color: var(--warn);
  background: var(--warn-soft);
  border-radius: 7px;
  padding: 6px 10px;
  margin-bottom: 10px;
}

.hits {
  display: flex;
  flex-direction: column;
}

.hit {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  padding: 10px 0;
}

.hit + .hit {
  border-top: 1px dashed var(--line);
}

.hit__rank {
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  flex: none;
  border-radius: 6px;
  background: var(--surface-3);
  font-size: 10px;
  color: var(--ink-2);
  margin-top: 1px;
}

.hit__body {
  flex: 1;
  min-width: 0;
}

.hit__title {
  font-size: 12.5px;
  font-weight: 550;
  color: var(--ink);
  line-height: 1.45;
}

.hit__doc {
  margin-top: 2px;
  font-size: 10px;
  color: var(--ink-4);
}

.hit__bar {
  height: 3px;
  border-radius: 3px;
  background: var(--surface-3);
  margin-top: 7px;
  overflow: hidden;
}

.hit__bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #9d9bf5, #5b5bd6);
}

.hit__bar--alt span {
  background: linear-gradient(90deg, #63c9bd, #12968a);
}

.hit__score {
  flex: none;
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-2);
  padding-top: 2px;
}

/* ---------------- 融合表 ---------------- */
.table-wrap {
  overflow-x: auto;
  margin: 0 -4px;
}

.table {
  width: 100%;
  min-width: 620px;
  border-collapse: collapse;
  font-size: 12px;
}

.table th {
  text-align: left;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.03em;
  color: var(--ink-3);
  padding: 0 10px 9px;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}

.table td {
  padding: 10px;
  border-bottom: 1px dashed var(--line);
  color: var(--ink-2);
  white-space: nowrap;
}

.table tbody tr:last-child td {
  border-bottom: 0;
}

.table tbody tr.is-top td {
  background: #fbfaff;
}

.col-doc {
  width: 46%;
  white-space: normal;
}

.table__rank {
  display: inline-grid;
  place-items: center;
  width: 18px;
  height: 18px;
  margin-right: 8px;
  border-radius: 5px;
  background: var(--surface-3);
  font-size: 9.5px;
  color: var(--ink-3);
  vertical-align: 1px;
}

.is-top .table__rank {
  background: var(--primary);
  color: #fff;
}

.table__title {
  color: var(--ink);
  font-weight: 550;
}

.table td.is-off {
  color: var(--ink-4);
}

.delta {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10.5px;
  padding: 1px 7px;
  border-radius: 999px;
}

.delta--up {
  background: var(--accent-soft);
  color: #0b7269;
}

.delta--down {
  background: var(--danger-soft);
  color: #b03e3d;
}

.delta--same {
  background: var(--surface-3);
  color: var(--ink-3);
}

.fusion__foot {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed var(--line);
  font-size: 11px;
  color: var(--ink-3);
}

.fusion__foot strong {
  color: var(--ink-2);
}

.fusion__sep {
  width: 1px;
  height: 10px;
  background: var(--line-strong);
}

.fusion__note {
  margin-left: auto;
  color: var(--ink-4);
}

/* ---------------- 消融 ---------------- */
.bars {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.bar-row {
  display: flex;
  align-items: center;
  gap: 14px;
}

.bar-row__label {
  width: 150px;
  flex: none;
  font-size: 12px;
  color: var(--ink-2);
}

.bar-row__track {
  flex: 1;
  height: 10px;
  border-radius: 5px;
  background: var(--surface-3);
  overflow: hidden;
}

.bar-row__track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  transition: width 0.6s ease;
}

.bar-row__fill--vector {
  background: linear-gradient(90deg, #a9a7f5, #7c7ae8);
}

.bar-row__fill--bm25 {
  background: linear-gradient(90deg, #c6c9d8, #a4a9bd);
}

.bar-row__fill--hybrid {
  background: linear-gradient(90deg, #6fd0c4, #12968a);
}

.bar-row__value {
  width: 42px;
  text-align: right;
  font-size: 12px;
  font-weight: 650;
  color: var(--ink);
}

.ablation__note {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed var(--line);
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--ink-3);
}

@media (max-width: 1024px) {
  .span-6 {
    grid-column: span 12;
  }

  .stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .query {
    flex-direction: column;
  }

  .stats {
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }

  .bar-row__label {
    width: 104px;
    font-size: 11px;
  }

  .fusion__note {
    margin-left: 0;
  }
}
</style>
