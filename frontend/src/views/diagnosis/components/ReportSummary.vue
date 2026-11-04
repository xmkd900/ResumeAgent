<script setup>
import { computed } from 'vue'

import ScoreRing from '@/components/ScoreRing.vue'
import { formatDateTime, formatScore } from '@/utils/format'

const props = defineProps({
  report: { type: Object, required: true },
  resume: { type: Object, default: null },
})

const issues = computed(() => (Array.isArray(props.report.issues) ? props.report.issues : []))
const dimensions = computed(() =>
  Array.isArray(props.report.dimension_scores) ? props.report.dimension_scores : [],
)

const score = computed(() => formatScore(props.report.overall_score) ?? 0)

const level = computed(() => {
  if (score.value >= 85) return { text: '表现优秀', type: 'primary' }
  if (score.value >= 75) return { text: '可投递', type: 'primary' }
  if (score.value >= 60) return { text: '待改进', type: 'soft' }
  return { text: '需重写', type: 'soft' }
})

const severityCounts = computed(() => {
  const counts = { high: 0, medium: 0, low: 0 }
  issues.value.forEach((issue) => {
    if (counts[issue.severity] !== undefined) counts[issue.severity] += 1
  })
  return counts
})

const hasJd = computed(() =>
  typeof props.report.has_jd === 'boolean' ? props.report.has_jd : props.report.jd_id != null,
)
</script>

<template>
  <div class="summary">
    <div class="summary__head">
      <ScoreRing :score="score" />
      <div class="summary__copy">
        <div class="summary__tags">
          <span class="pill" :class="level.type === 'primary' ? 'pill--primary' : 'pill--soft'">
            {{ level.text }}
          </span>
          <span class="pill pill--soft">{{ severityCounts.high }} 个高优先级</span>
          <span class="pill pill--soft">{{ dimensions.length }} 个维度</span>
        </div>
        <p class="summary__text">{{ report.summary || '本次诊断未返回整体评价。' }}</p>
        <dl class="summary__meta">
          <div>
            <dt>诊断时间</dt>
            <dd>{{ formatDateTime(report.created_at) }}</dd>
          </div>
          <div>
            <dt>JD 对照</dt>
            <dd>{{ hasJd ? '已关联' : '未关联' }}</dd>
          </div>
          <div>
            <dt>简历文件</dt>
            <dd class="truncate">{{ resume?.filename || '—' }}</dd>
          </div>
        </dl>
      </div>
    </div>

    <div class="summary__foot">
      <span class="summary__foot-item">
        <strong class="num">{{ severityCounts.high }}</strong> 高优先级
      </span>
      <span class="summary__foot-sep" />
      <span class="summary__foot-item">
        <strong class="num">{{ severityCounts.medium }}</strong> 中优先级
      </span>
      <span class="summary__foot-sep" />
      <span class="summary__foot-item">
        <strong class="num">{{ severityCounts.low }}</strong> 低优先级
      </span>
      <span class="summary__foot-sep" />
      <span class="summary__foot-item">
        共 <strong class="num">{{ issues.length }}</strong> 条改写建议
      </span>
    </div>
  </div>
</template>

<style scoped>
.summary {
  display: flex;
  flex-direction: column;
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

.summary__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.summary__text {
  font-size: 13px;
  line-height: 1.75;
  color: var(--ink-2);
}

.summary__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 26px;
  margin: 16px 0 0;
}

.summary__meta > div {
  min-width: 0;
}

.summary__meta dt {
  font-size: 10.5px;
  color: var(--ink-3);
  letter-spacing: 0.02em;
}

.summary__meta dd {
  margin: 3px 0 0;
  font-size: 12px;
  font-weight: 550;
  color: var(--ink-2);
  max-width: 220px;
}

.summary__foot {
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

.summary__foot-item strong {
  color: var(--ink);
  font-weight: 650;
}

.summary__foot-sep {
  width: 1px;
  height: 12px;
  background: var(--line-strong);
}

@media (max-width: 640px) {
  .summary__head {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
  }

  .summary__foot {
    gap: 8px;
  }
}
</style>
