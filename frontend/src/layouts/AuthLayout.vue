<script setup>
import { USE_MOCK } from '@/api/auth'

const points = [
  { num: '01', title: '结构化诊断', desc: '逐条引用原文，给出可直接替换的改写建议。' },
  { num: '02', title: '追问树面试', desc: '预设追问链 + 逐轮判卷，像真实面试一样下钻。' },
  { num: '03', title: '成长闭环', desc: '薄弱点自动关联知识库，练到掌握为止。' },
]
</script>

<template>
  <div class="auth">
    <aside class="stage">
      <div class="stage__glow stage__glow--a" aria-hidden="true" />
      <div class="stage__glow stage__glow--b" aria-hidden="true" />
      <div class="stage__grid" aria-hidden="true" />

      <div class="stage__inner">
        <div class="logo">
          <span class="logo__mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" width="20" height="20" fill="none">
              <path d="M16 3.5 28 10v12L16 28.5 4 22V10z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
              <path d="M16 10 22 13.4v6.6L16 23.4 10 20v-6.6z" fill="currentColor" opacity="0.9" />
            </svg>
          </span>
          <span class="logo__text">IntelliCareer</span>
        </div>

        <div class="stage__copy">
          <p class="stage__eyebrow">AI 面试备战工作台</p>
          <h1>把每一次面试，<br />变成可复用的经验。</h1>
          <p class="stage__lede">
            简历诊断 → 模拟面试 → 薄弱点补强。三个页面，一条闭环，把「准备」变成可衡量的进步。
          </p>
        </div>

        <ul class="points">
          <li v-for="point in points" :key="point.num" class="point">
            <span class="point__num">{{ point.num }}</span>
            <div>
              <p class="point__title">{{ point.title }}</p>
              <p class="point__desc">{{ point.desc }}</p>
            </div>
          </li>
        </ul>

        <div class="preview" aria-hidden="true">
          <div class="preview__head">
            <span class="preview__label">简历诊断报告</span>
            <span class="preview__live"><span class="dot dot--live" />已生成</span>
          </div>
          <div class="preview__body">
            <div class="preview__score">
              <span class="preview__score-num">82</span>
              <span class="preview__score-cap">综合分</span>
            </div>
            <div class="preview__bars">
              <div v-for="bar in [
                { name: '项目深度', value: 78 },
                { name: '成果量化', value: 64 },
                { name: '岗位匹配', value: 88 },
              ]" :key="bar.name" class="preview__bar">
                <span class="preview__bar-name">{{ bar.name }}</span>
                <span class="preview__bar-track"><i :style="{ width: `${bar.value}%` }" /></span>
                <span class="preview__bar-value">{{ bar.value }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <p class="stage__foot">受控工作流 + 局部自主决策 · v1.2</p>
    </aside>

    <main class="pane">
      <div class="pane__inner">
        <div class="pane__brand">
          <span class="logo__mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" width="18" height="18" fill="none">
              <path d="M16 3.5 28 10v12L16 28.5 4 22V10z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
              <path d="M16 10 22 13.4v6.6L16 23.4 10 20v-6.6z" fill="currentColor" opacity="0.9" />
            </svg>
          </span>
          <span>IntelliCareer</span>
        </div>

        <router-view />

        <p class="pane__foot">
          <span>IntelliCareer · AI 面试备战工作台</span>
          <span v-if="USE_MOCK" class="pane__mode">演示模式 · 未连接后端</span>
        </p>
      </div>
    </main>
  </div>
</template>

<style scoped>
.auth {
  display: grid;
  grid-template-columns: minmax(0, 1.06fr) minmax(440px, 0.94fr);
  min-height: 100vh;
  background: var(--surface);
}

/* ---------------- 左侧品牌舞台 ---------------- */
.stage {
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 40px clamp(32px, 5vw, 72px) 28px;
  background: radial-gradient(120% 90% at 12% 0%, #232a5e 0%, transparent 55%),
    linear-gradient(160deg, #10142e 0%, #0b0e20 55%, #080a17 100%);
  color: #eef0ff;
}

.stage__glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(60px);
  pointer-events: none;
}

.stage__glow--a {
  width: 460px;
  height: 460px;
  top: -140px;
  right: -120px;
  background: rgba(96, 92, 235, 0.34);
}

.stage__glow--b {
  width: 380px;
  height: 380px;
  bottom: -160px;
  left: -80px;
  background: rgba(18, 150, 138, 0.18);
}

.stage__grid {
  position: absolute;
  inset: 0;
  background-image: linear-gradient(rgba(255, 255, 255, 0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.045) 1px, transparent 1px);
  background-size: 64px 64px;
  mask-image: radial-gradient(80% 60% at 30% 20%, #000 20%, transparent 85%);
  pointer-events: none;
}

.stage__inner {
  position: relative;
  z-index: 1;
  flex: 1;
  display: flex;
  flex-direction: column;
  max-width: 520px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 15px;
  font-weight: 650;
  letter-spacing: -0.01em;
  color: #f3f4ff;
}

.logo__mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.14);
  color: #a9a7ff;
}

.stage__copy {
  margin-top: clamp(40px, 8vh, 84px);
}

.stage__eyebrow {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #9a97d8;
  margin-bottom: 18px;
}

.stage__copy h1 {
  font-size: clamp(30px, 3.2vw, 42px);
  line-height: 1.24;
  letter-spacing: -0.035em;
  font-weight: 650;
  color: #f7f7ff;
}

.stage__lede {
  margin-top: 18px;
  max-width: 420px;
  font-size: 13.5px;
  line-height: 1.85;
  color: rgba(232, 234, 255, 0.63);
}

.points {
  margin-top: clamp(28px, 4vh, 44px);
  display: flex;
  flex-direction: column;
  gap: 2px;
  border-top: 1px solid rgba(255, 255, 255, 0.09);
}

.point {
  display: flex;
  gap: 16px;
  padding: 14px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.09);
}

.point__num {
  font-family: var(--font-mono);
  font-size: 11px;
  color: #6f6cb8;
  padding-top: 3px;
  letter-spacing: 0.04em;
}

.point__title {
  font-size: 13px;
  font-weight: 600;
  color: #e9eaff;
}

.point__desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.7;
  color: rgba(232, 234, 255, 0.52);
}

.preview {
  margin-top: auto;
  margin-bottom: 22px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.13);
  background: linear-gradient(150deg, rgba(255, 255, 255, 0.09), rgba(255, 255, 255, 0.03));
  backdrop-filter: blur(8px);
  padding: 16px 18px 18px;
  box-shadow: 0 30px 60px -40px rgba(0, 0, 0, 0.9);
}

.preview__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
  color: rgba(232, 234, 255, 0.6);
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.preview__label {
  letter-spacing: 0.02em;
}

.preview__live {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #8fe3d8;
}

.preview__body {
  display: flex;
  align-items: center;
  gap: 22px;
  padding-top: 14px;
}

.preview__score {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding-right: 20px;
  border-right: 1px solid rgba(255, 255, 255, 0.09);
}

.preview__score-num {
  font-size: 34px;
  font-weight: 650;
  letter-spacing: -0.04em;
  line-height: 1;
  color: #f5f5ff;
  font-variant-numeric: tabular-nums;
}

.preview__score-cap {
  font-size: 10px;
  color: rgba(232, 234, 255, 0.45);
}

.preview__bars {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.preview__bar {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 10.5px;
  color: rgba(232, 234, 255, 0.55);
}

.preview__bar-name {
  width: 50px;
  flex: none;
}

.preview__bar-track {
  flex: 1;
  height: 4px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.1);
  overflow: hidden;
}

.preview__bar-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #8b89f2, #5b5bd6);
}

.preview__bar-value {
  width: 20px;
  text-align: right;
  color: rgba(232, 234, 255, 0.75);
  font-variant-numeric: tabular-nums;
}

.stage__foot {
  position: relative;
  z-index: 1;
  font-size: 10.5px;
  letter-spacing: 0.04em;
  color: rgba(232, 234, 255, 0.3);
}

/* ---------------- 右侧表单区 ---------------- */
.pane {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px clamp(24px, 5vw, 64px);
  background: var(--surface);
}

.pane__inner {
  width: 100%;
  max-width: 384px;
  display: flex;
  flex-direction: column;
}

.pane__brand {
  display: none;
  align-items: center;
  gap: 9px;
  margin-bottom: 30px;
  font-size: 14px;
  font-weight: 650;
}

.pane__brand .logo__mark {
  background: linear-gradient(145deg, #1c1f42, #0d1024);
  border-color: transparent;
}

.pane__foot {
  margin-top: auto;
  padding-top: 28px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  font-size: 10.5px;
  color: var(--ink-4);
}

.pane__mode {
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--surface-3);
  color: var(--ink-3);
}

@media (max-width: 1024px) {
  .auth {
    grid-template-columns: 1fr;
    background: var(--surface);
  }

  .stage {
    display: none;
  }

  .pane {
    align-items: flex-start;
    min-height: 100vh;
  }

  .pane__brand {
    display: flex;
  }
}

@media (max-width: 480px) {
  .pane {
    padding: 26px 20px 28px;
  }
}
</style>
