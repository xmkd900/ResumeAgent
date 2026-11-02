<script setup>
import { computed, useId } from 'vue'

const props = defineProps({
  score: { type: Number, default: 0 },
  size: { type: Number, default: 132 },
  stroke: { type: Number, default: 10 },
  label: { type: String, default: '综合得分' },
  suffix: { type: String, default: '/ 100' },
})

const uid = useId()
const gradientId = computed(() => `score-grad-${uid}`)

const radius = computed(() => (props.size - props.stroke) / 2)
const circumference = computed(() => 2 * Math.PI * radius.value)
const offset = computed(() => {
  const ratio = Math.max(0, Math.min(100, props.score)) / 100
  return circumference.value * (1 - ratio)
})

const level = computed(() => {
  if (props.score >= 85) return { text: '优秀', tone: 'excellent' }
  if (props.score >= 75) return { text: '良好', tone: 'good' }
  if (props.score >= 60) return { text: '待改进', tone: 'fair' }
  return { text: '需重写', tone: 'weak' }
})
</script>

<template>
  <div class="ring" :style="{ width: `${size}px`, height: `${size}px` }">
    <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`" role="img" :aria-label="`${label} ${score} 分`">
      <defs>
        <linearGradient :id="gradientId" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#7d7cf0" />
          <stop offset="100%" stop-color="#4a48c9" />
        </linearGradient>
      </defs>
      <circle
        :cx="size / 2"
        :cy="size / 2"
        :r="radius"
        fill="none"
        stroke="var(--surface-3)"
        :stroke-width="stroke"
      />
      <circle
        class="ring__value"
        :cx="size / 2"
        :cy="size / 2"
        :r="radius"
        fill="none"
        :stroke="`url(#${gradientId})`"
        :stroke-width="stroke"
        stroke-linecap="round"
        :stroke-dasharray="circumference"
        :stroke-dashoffset="offset"
        :transform="`rotate(-90 ${size / 2} ${size / 2})`"
      />
    </svg>
    <div class="ring__center">
      <span class="ring__score num">{{ score }}</span>
      <span class="ring__suffix">{{ suffix }}</span>
      <span class="ring__level" :class="`ring__level--${level.tone}`">{{ level.text }}</span>
    </div>
  </div>
</template>

<style scoped>
.ring {
  position: relative;
  flex: none;
}

.ring__value {
  transition: stroke-dashoffset 0.9s cubic-bezier(0.22, 0.61, 0.36, 1);
}

.ring__center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
}

.ring__score {
  font-size: 32px;
  font-weight: 680;
  letter-spacing: -0.04em;
  line-height: 1;
  color: var(--ink);
}

.ring__suffix {
  font-size: 10.5px;
  color: var(--ink-3);
}

.ring__level {
  margin-top: 5px;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  padding: 1px 7px;
  border-radius: 999px;
}

.ring__level--excellent {
  color: #0b7269;
  background: var(--accent-soft);
}

.ring__level--good {
  color: var(--primary-strong);
  background: var(--primary-soft);
}

.ring__level--fair {
  color: #96600f;
  background: var(--warn-soft);
}

.ring__level--weak {
  color: #b03e3d;
  background: var(--danger-soft);
}

@media (max-width: 640px) {
  .ring__score {
    font-size: 26px;
  }
}
</style>
