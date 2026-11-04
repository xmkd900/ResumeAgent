<script setup>
import { computed } from 'vue'

import EmptyState from '@/components/EmptyState.vue'
import SectionCard from '@/components/SectionCard.vue'
import { formatScore, formatShortDateTime } from '@/utils/format'

const props = defineProps({
  resumes: { type: Array, default: () => [] },
  activeId: { type: [Number, String], default: null },
  loading: { type: Boolean, default: false },
  total: { type: Number, default: 0 },
})

const emit = defineEmits(['select'])

const STATUS_LABEL = {
  pending: '解析中',
  failed: '解析失败',
  done: '未诊断',
}

const items = computed(() =>
  props.resumes.map((resume) => ({
    ...resume,
    score: formatScore(resume.latest_report?.overall_score),
    statusLabel: STATUS_LABEL[resume.parse_status] || resume.parse_status,
    statusTone:
      resume.parse_status === 'pending'
        ? 'dot--pending'
        : resume.parse_status === 'failed'
          ? 'dot--failed'
          : resume.latest_report
            ? 'dot--live'
            : 'dot',
  })),
)
</script>

<template>
  <SectionCard id="history-card" title="历史诊断" subtitle="按上传时间倒序，点击查看对应报告">
    <template #extra>
      <span class="muted num">{{ total || resumes.length }} 份</span>
    </template>

    <div v-if="loading" class="skeleton" aria-hidden="true">
      <div v-for="n in 3" :key="n" class="skeleton__row">
        <span class="skeleton__badge" />
        <span class="skeleton__lines">
          <i />
          <i />
        </span>
      </div>
    </div>

    <EmptyState
      v-else-if="!items.length"
      title="还没有诊断记录"
      description="上传第一份简历后，解析状态与诊断分数会出现在这里。"
      compact
    />

    <ul v-else class="history">
      <li v-for="item in items" :key="item.id">
        <button
          type="button"
          class="history__item"
          :class="{ 'is-current': String(item.id) === String(activeId) }"
          @click="emit('select', item.id)"
        >
          <span class="history__score num" :class="{ 'is-text': item.score == null }">
            {{ item.score ?? '—' }}
          </span>
          <span class="history__meta">
            <span class="history__file truncate" :title="item.filename">{{ item.filename }}</span>
            <span class="history__date">
              <span class="dot" :class="item.statusTone" />
              {{ formatShortDateTime(item.created_at) }}
              <span class="history__status">{{ item.latest_report ? '最新分' : item.statusLabel }}</span>
            </span>
          </span>
          <span class="history__arrow" aria-hidden="true">
            <svg viewBox="0 0 16 16" width="12" height="12" fill="none">
              <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </span>
        </button>
      </li>
    </ul>

    <p class="history__note">报告随时间累积，便于对比修改前后的变化。</p>
  </SectionCard>
</template>

<style scoped>
.history {
  display: flex;
  flex-direction: column;
}

.history__item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 10px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.16s ease;
}

.history li + li .history__item {
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

.history__score.is-text {
  font-size: 12px;
  color: var(--ink-4);
}

.history__item.is-current .history__score {
  border-color: transparent;
  background: #fff;
  color: var(--primary-strong);
}

.history__meta {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.history__file {
  font-size: 12px;
  font-weight: 550;
  color: var(--ink-2);
}

.history__date {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 3px;
  font-size: 10.5px;
  color: var(--ink-3);
}

.history__status {
  padding-left: 5px;
  border-left: 1px solid var(--line-strong);
  color: var(--ink-4);
}

.history__arrow {
  flex: none;
  color: var(--ink-4);
  opacity: 0.6;
}

.history__item.is-current .history__arrow {
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

.skeleton {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.skeleton__row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.skeleton__badge {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--surface-3);
  animation: pulse 1.4s ease-in-out infinite;
}

.skeleton__lines {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.skeleton__lines i {
  height: 9px;
  border-radius: 4px;
  background: var(--surface-3);
  animation: pulse 1.4s ease-in-out infinite;
}

.skeleton__lines i:last-child {
  width: 55%;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.55;
  }
}
</style>
