<script setup>
defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  eyebrow: { type: String, default: '' },
})
</script>

<template>
  <header class="page-header">
    <div class="page-header__text">
      <p v-if="eyebrow" class="eyebrow page-header__eyebrow">{{ eyebrow }}</p>
      <h1 class="page-header__title">{{ title }}</h1>
      <p v-if="subtitle" class="page-header__subtitle">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.actions" class="page-header__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
  margin-bottom: 22px;
}

.page-header__eyebrow {
  margin-bottom: 8px;
  color: var(--primary);
  opacity: 0.85;
}

.page-header__title {
  font-size: 24px;
  letter-spacing: -0.03em;
}

.page-header__subtitle {
  margin-top: 7px;
  max-width: 620px;
  color: var(--ink-2);
  font-size: 13.5px;
}

.page-header__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

@media (max-width: 640px) {
  .page-header {
    margin-bottom: 18px;
  }

  .page-header__title {
    font-size: 21px;
  }

  .page-header__actions {
    width: 100%;
  }
}
</style>
