<script setup>
defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  padded: { type: Boolean, default: true },
  tone: { type: String, default: 'default' }, // default | flat
})
</script>

<template>
  <section class="card" :class="[`card--${tone}`, { 'card--padded': padded }]">
    <header v-if="title || $slots.extra" class="card__head">
      <div class="card__heading">
        <h2 class="card__title">{{ title }}</h2>
        <p v-if="subtitle" class="card__subtitle">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.extra" class="card__extra">
        <slot name="extra" />
      </div>
    </header>
    <div class="card__body" :class="{ 'card__body--flush': !padded }">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  min-width: 0;
}

.card--flat {
  box-shadow: none;
  background: var(--surface-2);
}

.card--padded {
  padding: 20px 22px;
}

.card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 16px;
}

.card__title {
  font-size: 15px;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.card__subtitle {
  margin-top: 5px;
  font-size: 12.5px;
  color: var(--ink-3);
  line-height: 1.55;
}

.card__extra {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

.card__body--flush {
  margin: 0 -22px -20px;
}

@media (max-width: 640px) {
  .card--padded {
    padding: 16px;
  }

  .card__body--flush {
    margin: 0 -16px -16px;
  }
}
</style>
