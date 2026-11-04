<script setup>
import { computed } from 'vue'
import { ElMessage } from 'element-plus'

import EmptyState from '@/components/EmptyState.vue'
import { ISSUE_TYPE_LABELS, SEVERITY_META } from '@/constants'

const props = defineProps({
  issues: { type: Array, default: () => [] },
})

const normalized = computed(() =>
  props.issues.map((issue, index) => {
    const severity = SEVERITY_META[issue.severity] ? issue.severity : 'low'
    return {
      ...issue,
      key: issue.id ?? `issue-${index}`,
      severity,
      severityLabel: SEVERITY_META[severity].label,
      severityTone: SEVERITY_META[severity].tone,
      typeLabel: ISSUE_TYPE_LABELS[issue.type] || issue.type || '待改进',
    }
  }),
)

async function copyText(text) {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制改写建议')
  } catch {
    ElMessage.warning('浏览器拒绝了复制，请手动选择文本')
  }
}
</script>

<template>
  <div v-if="normalized.length" class="issues">
    <article
      v-for="(issue, index) in normalized"
      :key="issue.key"
      class="issue"
      :class="`issue--${issue.severity}`"
    >
      <header class="issue__head">
        <span class="pill" :class="`pill--${issue.severityTone}`">{{ issue.severityLabel }}</span>
        <span class="issue__type">{{ issue.typeLabel }}</span>
        <span v-if="issue.dimension" class="issue__dim">{{ issue.dimension }}</span>
        <span class="issue__index num">#{{ String(index + 1).padStart(2, '0') }}</span>
      </header>

      <blockquote v-if="issue.quote" class="issue__quote">{{ issue.quote }}</blockquote>

      <div class="issue__row">
        <p class="issue__label">问题</p>
        <p class="issue__text">{{ issue.problem }}</p>
      </div>

      <div v-if="issue.rewritten" class="issue__row issue__row--fix">
        <p class="issue__label">改写</p>
        <p class="issue__text">{{ issue.rewritten }}</p>
        <button class="issue__copy" type="button" @click="copyText(issue.rewritten)">复制</button>
      </div>
    </article>
  </div>

  <EmptyState
    v-else
    title="本次诊断没有给出具体问题"
    description="可能是简历已比较完善，或者模型返回的 issues 为空。可以换一版简历或补充 JD 后再试。"
    compact
  />
</template>

<style scoped>
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

@media (max-width: 640px) {
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
