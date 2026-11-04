<script setup>
import { computed } from 'vue'

import ChartBox from '@/components/ChartBox.vue'
import EmptyState from '@/components/EmptyState.vue'

const props = defineProps({
  dimensions: { type: Array, default: () => [] },
})

const normalized = computed(() =>
  props.dimensions
    .filter((item) => item && item.name !== undefined)
    .map((item) => {
      const score = Number(item.score)
      return {
        name: String(item.name),
        score: Number.isFinite(score) ? Math.max(0, Math.min(100, Math.round(score))) : 0,
      }
    }),
)

const canRadar = computed(() => normalized.value.length >= 3)

const radarOption = computed(() => ({
  tooltip: { trigger: 'item' },
  radar: {
    indicator: normalized.value.map((item) => ({ name: item.name, max: 100 })),
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
      data: [{ value: normalized.value.map((item) => item.score), name: '本次诊断' }],
    },
  ],
}))
</script>

<template>
  <div class="radar">
    <template v-if="canRadar">
      <ChartBox :option="radarOption" height="228px" />
    </template>
    <EmptyState
      v-else-if="normalized.length === 0"
      title="报告未返回维度得分"
      description="维度雷达依赖 dimension_scores，请检查后端诊断结果的结构化输出。"
      compact
    />
    <div v-else class="radar__fallback">
      <p>维度不足 3 个，无法绘制雷达图，改用分数条展示。</p>
    </div>

    <ul v-if="normalized.length" class="dims">
      <li v-for="dim in normalized" :key="dim.name" class="dims__item">
        <span class="dims__name" :title="dim.name">{{ dim.name }}</span>
        <span class="dims__track">
          <i :style="{ width: `${dim.score}%` }" :class="{ 'is-low': dim.score < 70 }" />
        </span>
        <span class="dims__value num">{{ dim.score }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.radar {
  display: flex;
  flex-direction: column;
}

.radar__fallback {
  padding: 18px 0;
}

.radar__fallback p {
  font-size: 11.5px;
  color: var(--ink-3);
  line-height: 1.65;
}

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
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

@media (max-width: 1080px) {
  .dims {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px 22px;
  }
}

@media (max-width: 640px) {
  .dims {
    grid-template-columns: 1fr;
  }
}
</style>
