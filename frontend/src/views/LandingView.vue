<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { USE_MOCK } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const isAuthed = computed(() => auth.isAuthed)

function goLogin() {
  router.push({ name: 'login' })
}

function goRegister() {
  router.push({ name: 'register' })
}

function goWorkspace() {
  router.push({ name: 'diagnosis' })
}

function switchAccount() {
  auth.logout()
  ElMessage.success('已退出当前账号')
  router.push({ name: 'login' })
}

const steps = [
  { num: '01', title: '简历诊断', desc: '引用原文逐条挑问题，给出可直接替换的改写。' },
  { num: '02', title: '模拟面试', desc: '按岗位出题，沿追问链下钻，逐轮给出判卷反馈。' },
  { num: '03', title: '成长闭环', desc: '薄弱点自动关联知识库，练到掌握为止。' },
]
</script>

<template>
  <div class="landing">
    <div class="landing__glow landing__glow--a" aria-hidden="true" />
    <div class="landing__glow landing__glow--b" aria-hidden="true" />

    <header class="nav">
      <router-link to="/welcome" class="logo">
        <span class="logo__mark" aria-hidden="true">
          <svg viewBox="0 0 32 32" width="19" height="19" fill="none">
            <path d="M16 3.5 28 10v12L16 28.5 4 22V10z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
            <path d="M16 10 22 13.4v6.6L16 23.4 10 20v-6.6z" fill="currentColor" opacity="0.9" />
          </svg>
        </span>
        <span class="logo__text">
          <strong>IntelliCareer</strong>
          <em>AI 面试备战工作台</em>
        </span>
      </router-link>

      <nav class="nav__actions">
        <template v-if="isAuthed">
          <span class="nav__user">{{ auth.username }}</span>
          <el-button type="primary" @click="goWorkspace">进入工作台</el-button>
        </template>
        <template v-else>
          <el-button text class="nav__login" @click="goLogin">登录</el-button>
          <el-button plain @click="goRegister">注册</el-button>
        </template>
      </nav>
    </header>

    <main class="hero">
      <section class="hero__copy">
        <p class="hero__eyebrow">
          <span class="dot dot--live" />
          Resume · Interview · Growth
        </p>
        <h1>每一次面试，<br />都有据可依。</h1>
        <p class="hero__lede">
          简历诊断告诉你哪里该改，模拟面试追问到答不上来为止，成长闭环把薄弱点一条条补掉。
          三个页面，一条可衡量的准备路径。
        </p>

        <div class="hero__ctas">
          <template v-if="isAuthed">
            <el-button type="primary" size="large" @click="goWorkspace">进入工作台</el-button>
            <el-button size="large" @click="switchAccount">切换账号</el-button>
          </template>
          <template v-else>
            <el-button type="primary" size="large" @click="goLogin">登录</el-button>
            <el-button size="large" @click="goRegister">注册新账号</el-button>
          </template>
        </div>

        <p v-if="USE_MOCK && !isAuthed" class="hero__hint">
          演示模式 · 可直接用 <code>demo</code> / <code>demo1234</code> 登录，或注册一个新账号
        </p>
        <p v-else-if="!isAuthed" class="hero__hint">登录后可查看自己的诊断记录、面试复盘与薄弱点</p>

        <ul class="hero__points">
          <li><span class="tick">✓</span>诊断建议逐条引用原文</li>
          <li><span class="tick">✓</span>面试复盘按人沉淀</li>
          <li><span class="tick">✓</span>薄弱点可量化掌握度</li>
        </ul>
      </section>

      <section class="preview" aria-label="产品预览">
        <div class="panel">
          <div class="panel__grid" aria-hidden="true" />
          <div class="panel__head">
            <span class="panel__title">模拟面试</span>
            <span class="panel__meta">第 3 / 共 8 题</span>
          </div>
          <div class="panel__progress"><i /></div>

          <p class="panel__who">面试官</p>
          <p class="panel__q">如果这个查询还要按金额排序，你的索引会怎么调整？代价是什么？</p>

          <div class="panel__judge">
            <span class="panel__tag">回答扎实</span>
            <span class="panel__judge-meta">命中 2 个要点 · 待补 1 个</span>
          </div>
          <ul class="panel__list">
            <li><span class="panel__dot panel__dot--hit">✓</span>说明了联合索引的列顺序取舍</li>
            <li><span class="panel__dot panel__dot--miss">–</span>没有量化排序带来的写入代价</li>
          </ul>

          <div class="panel__divider" />

          <div class="panel__score-head">
            <span class="panel__title">简历诊断</span>
            <span class="panel__meta">维度得分</span>
          </div>
          <div class="panel__bars">
            <div class="panel__bar">
              <span>项目深度</span>
              <span class="panel__track"><i style="width: 78%" /></span>
              <span class="panel__num">78</span>
            </div>
            <div class="panel__bar">
              <span>成果量化</span>
              <span class="panel__track"><i class="is-warn" style="width: 62%" /></span>
              <span class="panel__num">62</span>
            </div>
            <div class="panel__bar">
              <span>岗位匹配</span>
              <span class="panel__track"><i style="width: 81%" /></span>
              <span class="panel__num">81</span>
            </div>
          </div>
        </div>

        <div class="float float--score">
          <span class="float__label">综合分</span>
          <strong class="num">82</strong>
          <small>/ 100</small>
        </div>

        <div class="float float--weak">
          <span class="dot dot--live" />
          <span>薄弱点已同步到成长闭环</span>
        </div>
      </section>
    </main>

    <footer class="steps">
      <div v-for="step in steps" :key="step.num" class="step">
        <span class="step__num">{{ step.num }}</span>
        <div>
          <p class="step__title">{{ step.title }}</p>
          <p class="step__desc">{{ step.desc }}</p>
        </div>
      </div>
    </footer>

    <p class="landing__foot">
      受控工作流 + 局部自主决策 · 简历诊断 / 模拟面试 / 成长闭环 / 检索调试台
    </p>
  </div>
</template>

<style scoped>
.landing {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  padding: 0 clamp(20px, 5vw, 56px);
  display: flex;
  flex-direction: column;
  background: radial-gradient(90% 70% at 8% 0%, #f0efff 0%, transparent 55%),
    radial-gradient(70% 60% at 96% 12%, #e9f7f5 0%, transparent 60%), var(--bg);
}

.landing__glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  pointer-events: none;
}

.landing__glow--a {
  width: 420px;
  height: 420px;
  top: -180px;
  right: 4%;
  background: rgba(91, 91, 214, 0.12);
}

.landing__glow--b {
  width: 360px;
  height: 360px;
  bottom: -160px;
  left: -80px;
  background: rgba(18, 150, 138, 0.1);
}

/* ---------------- 顶部 ---------------- */
.nav {
  position: relative;
  z-index: 2;
  width: 100%;
  max-width: 1180px;
  margin: 0 auto;
  padding: 24px 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  color: inherit;
}

.logo__mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: linear-gradient(145deg, #1c1f42, #0d1024);
  color: #a9a7ff;
  box-shadow: 0 8px 18px -12px rgba(13, 16, 36, 0.8);
}

.logo__text {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}

.logo__text strong {
  font-size: 14.5px;
  font-weight: 680;
  letter-spacing: -0.01em;
}

.logo__text em {
  font-style: normal;
  font-size: 10.5px;
  color: var(--ink-3);
}

.nav__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.nav__login {
  color: var(--ink-2);
  font-weight: 550;
}

.nav__user {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--ink-3);
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--surface-3);
}

/* ---------------- Hero ---------------- */
.hero {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 1180px;
  margin: 0 auto;
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 1.02fr) minmax(0, 0.98fr);
  align-items: center;
  gap: clamp(28px, 5vw, 64px);
  padding: clamp(20px, 5vh, 56px) 0;
}

.hero__copy {
  min-width: 0;
}

.hero__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 10.5px;
  font-weight: 650;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--primary-strong);
  padding: 5px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid #e4e2f8;
}

.hero h1 {
  margin-top: 20px;
  font-size: clamp(36px, 4.4vw, 56px);
  line-height: 1.16;
  letter-spacing: -0.045em;
  font-weight: 680;
  color: var(--ink);
}

.hero__lede {
  margin-top: 18px;
  max-width: 480px;
  font-size: 14px;
  line-height: 1.9;
  color: var(--ink-2);
}

.hero__ctas {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 28px;
}

.hero__hint {
  margin-top: 14px;
  font-size: 11.5px;
  color: var(--ink-3);
}

.hero__hint code {
  font-family: var(--font-mono);
  font-size: 11px;
  padding: 1px 5px;
  border-radius: 4px;
  background: #fff;
  border: 1px solid var(--line);
  color: var(--ink-2);
}

.hero__points {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  margin-top: 26px;
  padding-top: 18px;
  border-top: 1px solid rgba(20, 23, 38, 0.07);
}

.hero__points li {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--ink-3);
}

.tick {
  display: inline-grid;
  place-items: center;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--accent-soft);
  color: #0b7269;
  font-size: 9px;
}

/* ---------------- 产品预览 ---------------- */
.preview {
  position: relative;
  min-width: 0;
  padding: 10px 0 26px;
}

.panel {
  position: relative;
  overflow: hidden;
  border-radius: 20px;
  padding: 22px 22px 20px;
  color: #e9eaff;
  background: radial-gradient(110% 80% at 85% 0%, #262a5c 0%, transparent 60%),
    linear-gradient(160deg, #14172f 0%, #0c0f21 100%);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 40px 80px -50px rgba(13, 16, 36, 0.85);
  transform: perspective(1200px) rotateY(-3deg) rotateX(1.5deg);
}

.panel__grid {
  position: absolute;
  inset: 0;
  background-image: linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(80% 70% at 30% 0%, #000 10%, transparent 80%);
  pointer-events: none;
}

.panel__head,
.panel__score-head {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel__title {
  font-size: 11.5px;
  font-weight: 600;
  color: #eef0ff;
}

.panel__meta {
  font-size: 10px;
  color: rgba(233, 234, 255, 0.5);
  font-variant-numeric: tabular-nums;
}

.panel__progress {
  position: relative;
  height: 3px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.09);
  margin: 10px 0 18px;
  overflow: hidden;
}

.panel__progress i {
  display: block;
  width: 38%;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #8b89f2, #5b5bd6);
}

.panel__who {
  position: relative;
  font-size: 9.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(233, 234, 255, 0.38);
  margin-bottom: 6px;
}

.panel__q {
  position: relative;
  font-size: 12.5px;
  line-height: 1.75;
  color: rgba(240, 241, 255, 0.9);
  padding-left: 12px;
  border-left: 2px solid rgba(139, 137, 242, 0.55);
}

.panel__judge {
  position: relative;
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 16px 0 9px;
}

.panel__tag {
  padding: 2px 9px;
  border-radius: 999px;
  background: rgba(18, 200, 185, 0.15);
  color: #7fe3d7;
  font-size: 10px;
  font-weight: 600;
}

.panel__judge-meta {
  font-size: 9.5px;
  color: rgba(233, 234, 255, 0.4);
}

.panel__list {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.panel__list li {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  font-size: 10.5px;
  line-height: 1.6;
  color: rgba(233, 234, 255, 0.62);
}

.panel__dot {
  flex: none;
  display: inline-grid;
  place-items: center;
  width: 13px;
  height: 13px;
  border-radius: 50%;
  font-size: 8px;
  margin-top: 2px;
}

.panel__dot--hit {
  background: rgba(18, 200, 185, 0.16);
  color: #7fe3d7;
}

.panel__dot--miss {
  background: rgba(224, 166, 62, 0.16);
  color: #e7bd77;
}

.panel__divider {
  height: 1px;
  background: rgba(255, 255, 255, 0.08);
  margin: 16px 0 14px;
}

.panel__bars {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.panel__bar {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 10px;
  color: rgba(233, 234, 255, 0.5);
}

.panel__bar > span:first-child {
  width: 46px;
  flex: none;
}

.panel__track {
  flex: 1;
  height: 4px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.09);
  overflow: hidden;
}

.panel__track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #8b89f2, #5b5bd6);
}

.panel__track i.is-warn {
  background: linear-gradient(90deg, #e8b25f, #c67c12);
}

.panel__num {
  width: 18px;
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: rgba(233, 234, 255, 0.72);
}

.float {
  position: absolute;
  display: flex;
  align-items: center;
  gap: 6px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 12px;
  box-shadow: 0 18px 40px -28px rgba(20, 23, 38, 0.55);
  font-size: 10.5px;
  color: var(--ink-2);
}

.float--score {
  right: -14px;
  top: -6px;
  padding: 8px 12px;
}

.float__label {
  color: var(--ink-3);
  font-size: 10px;
}

.float--score strong {
  font-size: 18px;
  font-weight: 680;
  color: var(--ink);
  letter-spacing: -0.03em;
}

.float--score small {
  font-size: 9.5px;
  color: var(--ink-4);
}

.float--weak {
  left: -18px;
  bottom: 4px;
  padding: 8px 12px;
}

/* ---------------- 三步 ---------------- */
.steps {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 1180px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0;
  border-top: 1px solid rgba(20, 23, 38, 0.08);
}

.step {
  display: flex;
  gap: 12px;
  padding: 20px 24px 22px 0;
}

.step + .step {
  padding-left: 24px;
  border-left: 1px solid rgba(20, 23, 38, 0.08);
}

.step__num {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--ink-4);
  padding-top: 2px;
}

.step__title {
  font-size: 12.5px;
  font-weight: 650;
  color: var(--ink);
}

.step__desc {
  margin-top: 4px;
  font-size: 11px;
  line-height: 1.65;
  color: var(--ink-3);
}

.landing__foot {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 1180px;
  margin: 0 auto;
  padding: 12px 0 20px;
  font-size: 10px;
  letter-spacing: 0.03em;
  color: var(--ink-4);
}

@media (max-width: 1020px) {
  .hero {
    grid-template-columns: 1fr;
    gap: 30px;
    padding-top: 14px;
  }

  .panel {
    transform: none;
    max-width: 480px;
  }

  .preview {
    padding-bottom: 20px;
  }

  .float--score {
    right: auto;
    left: 74%;
  }
}

@media (max-width: 720px) {
  .landing {
    overflow: visible;
  }

  .nav {
    padding: 18px 0;
  }

  .logo__text em {
    display: none;
  }

  .hero h1 {
    font-size: 34px;
  }

  .hero__ctas :deep(.el-button) {
    flex: 1;
  }

  .hero__points {
    gap: 8px 14px;
  }

  .preview {
    display: none;
  }

  .steps {
    grid-template-columns: 1fr;
  }

  .step {
    padding: 14px 0;
  }

  .step + .step {
    padding-left: 0;
    border-left: 0;
    border-top: 1px dashed rgba(20, 23, 38, 0.1);
  }
}
</style>
