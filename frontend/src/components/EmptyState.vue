<script setup>
defineProps({
  title: { type: String, default: '这里还是空的' },
  description: { type: String, default: '' },
  compact: { type: Boolean, default: false },
})
</script>

<template>
  <div class="empty" :class="{ 'empty--compact': compact }">
    <div class="empty__art" aria-hidden="true">
      <slot name="icon">
        <svg viewBox="0 0 48 48" width="34" height="34" fill="none">
          <rect x="7" y="9" width="34" height="26" rx="6" stroke="currentColor" stroke-width="2" opacity="0.55" />
          <path d="M15 18h12M15 24h18M15 30h8" stroke="currentColor" stroke-width="2" stroke-linecap="round" opacity="0.8" />
          <circle cx="34" cy="35" r="6" fill="var(--surface)" stroke="currentColor" stroke-width="2" opacity="0.55" />
          <path d="M38.5 39.5 42 43" stroke="currentColor" stroke-width="2" stroke-linecap="round" opacity="0.55" />
        </svg>
      </slot>
    </div>
    <p class="empty__title">{{ title }}</p>
    <p v-if="description" class="empty__desc">{{ description }}</p>
    <div v-if="$slots.default" class="empty__action">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 46px 24px;
  color: var(--ink-3);
}

.empty--compact {
  padding: 28px 16px;
}

.empty__art {
  display: grid;
  place-items: center;
  width: 64px;
  height: 64px;
  border-radius: 20px;
  background: var(--surface-3);
  color: var(--primary);
  margin-bottom: 14px;
}

.empty__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-2);
}

.empty__desc {
  margin-top: 6px;
  max-width: 340px;
  font-size: 12.5px;
  line-height: 1.65;
}

.empty__action {
  margin-top: 16px;
}
</style>
