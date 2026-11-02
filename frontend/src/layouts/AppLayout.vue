<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowDown,
  DataAnalysis,
  Document,
  Link,
  Microphone,
  Switch,
  SwitchButton,
  TrendCharts,
  User,
} from '@element-plus/icons-vue'

import { DEBUG_ENABLED } from '@/constants'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const drawerOpen = ref(false)
const accountOpen = ref(false)

const navGroups = computed(() => {
  const groups = [
    {
      label: '工作台',
      items: [
        { to: '/resume', title: '简历诊断', desc: '逐条改写建议', icon: Document },
        { to: '/interview', title: '模拟面试', desc: '追问树 + 逐轮判卷', icon: Microphone },
        { to: '/growth', title: '成长闭环', desc: '薄弱点与练习', icon: TrendCharts },
      ],
    },
  ]
  if (DEBUG_ENABLED) {
    groups.push({
      label: '工具',
      items: [{ to: '/debug', title: '检索调试台', desc: '双路召回与融合', icon: DataAnalysis }],
    })
  }
  return groups
})

const createdLabel = computed(() => {
  const raw = auth.user?.created_at
  if (!raw) return '—'
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return '—'
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
})

function handleCommand(command) {
  if (command === 'switch') {
    auth.logout()
    ElMessage.success('已退出当前账号，请重新登录')
    router.replace({ name: 'login' })
  }
  if (command === 'logout') {
    auth.logout()
    ElMessage.success('已安全退出')
    router.replace({ name: 'welcome' })
  }
  if (command === 'account') accountOpen.value = true
  if (command === 'docs') window.open('/docs', '_blank', 'noopener')
}
</script>

<template>
  <div class="shell">
    <aside class="sidebar" :class="{ 'is-open': drawerOpen }">
      <router-link to="/resume" class="brand" @click="drawerOpen = false">
        <span class="brand__mark" aria-hidden="true">
          <svg viewBox="0 0 32 32" width="20" height="20" fill="none">
            <path d="M16 3.5 28 10v12L16 28.5 4 22V10z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
            <path d="M16 10 22 13.4v6.6L16 23.4 10 20v-6.6z" fill="currentColor" opacity="0.9" />
          </svg>
        </span>
        <span class="brand__meta">
          <strong>IntelliCareer</strong>
          <em>面试备战工作台</em>
        </span>
      </router-link>

      <nav class="nav" aria-label="主导航">
        <div v-for="group in navGroups" :key="group.label" class="nav__group">
          <p class="nav__label">{{ group.label }}</p>
          <router-link
            v-for="item in group.items"
            :key="item.to"
            :to="item.to"
            class="nav__item"
            @click="drawerOpen = false"
          >
            <el-icon class="nav__icon"><component :is="item.icon" /></el-icon>
            <span class="nav__text">
              <span class="nav__title">{{ item.title }}</span>
              <span class="nav__desc">{{ item.desc }}</span>
            </span>
            <span class="nav__arrow" aria-hidden="true">
              <svg viewBox="0 0 16 16" width="12" height="12" fill="none">
                <path d="M6 3.5 10.5 8 6 12.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </span>
          </router-link>
        </div>
      </nav>

      <div class="sidebar__foot">
        <div class="mode-card">
          <span class="dot dot--live" />
          <div class="mode-card__text">
            <p>前端原型</p>
            <small>业务数据为示例内容</small>
          </div>
        </div>
      </div>
    </aside>

    <transition name="fade">
      <div v-if="drawerOpen" class="scrim" @click="drawerOpen = false" />
    </transition>

    <div class="main">
      <header class="topbar">
        <button class="icon-btn topbar__menu" aria-label="打开导航菜单" @click="drawerOpen = true">
          <svg viewBox="0 0 18 18" width="16" height="16" fill="none" aria-hidden="true">
            <path d="M3 5.5h12M3 9h12M3 12.5h8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
          </svg>
        </button>

        <div class="crumbs">
          <span class="crumbs__group">{{ route.meta.group || '工作台' }}</span>
          <span class="crumbs__sep">/</span>
          <span class="crumbs__current">{{ route.meta.title }}</span>
        </div>

        <div class="topbar__right">
          <el-dropdown trigger="click" @command="handleCommand">
            <button class="user-btn" type="button">
              <span class="avatar">{{ auth.initial }}</span>
              <span class="user-btn__name">{{ auth.username || '未登录' }}</span>
              <el-icon class="user-btn__caret"><ArrowDown /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="account">
                  <el-icon><User /></el-icon>账号信息
                </el-dropdown-item>
                <el-dropdown-item v-if="DEBUG_ENABLED" command="docs" divided>
                  <el-icon><Link /></el-icon>接口文档
                </el-dropdown-item>
                <el-dropdown-item command="switch" divided>
                  <el-icon><Switch /></el-icon>切换账号
                </el-dropdown-item>
                <el-dropdown-item command="logout">
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <main class="content">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>

    <el-dialog v-model="accountOpen" title="账号信息" width="380px" align-center>
      <div class="account">
        <span class="account__avatar">{{ auth.initial }}</span>
        <div>
          <p class="account__name">{{ auth.username }}</p>
          <p class="account__meta">用户 ID · {{ auth.user?.id ?? '—' }}</p>
        </div>
      </div>
      <dl class="account__list">
        <div><dt>注册时间</dt><dd>{{ createdLabel }}</dd></div>
        <div><dt>鉴权方式</dt><dd>JWT · Bearer</dd></div>
        <div><dt>数据范围</dt><dd>仅本人</dd></div>
      </dl>
      <template #footer>
        <el-button @click="accountOpen = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  min-height: 100vh;
  background: var(--bg);
}

/* ---------------- 侧边栏 ---------------- */
.sidebar {
  position: fixed;
  inset: 0 auto 0 0;
  z-index: 40;
  width: var(--shell-sidebar);
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border-right: 1px solid var(--line);
  padding: 22px 16px 16px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 8px 22px;
  color: inherit;
}

.brand__mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: linear-gradient(145deg, #1c1f42, #0d1024);
  color: #a9a7ff;
  box-shadow: 0 6px 16px -10px rgba(13, 16, 36, 0.9);
}

.brand__meta {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}

.brand__meta strong {
  font-size: 14.5px;
  font-weight: 680;
  letter-spacing: -0.01em;
}

.brand__meta em {
  font-style: normal;
  font-size: 11px;
  color: var(--ink-3);
  letter-spacing: 0.02em;
}

.nav {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 22px;
  padding-bottom: 12px;
}

.nav__label {
  padding: 0 10px;
  margin-bottom: 8px;
  font-size: 10.5px;
  font-weight: 650;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-4);
}

.nav__item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border-radius: 10px;
  color: var(--ink-2);
  text-decoration: none;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.nav__item + .nav__item {
  margin-top: 2px;
}

.nav__item:hover {
  background: var(--surface-3);
  color: var(--ink);
}

.nav__item.router-link-active {
  background: var(--primary-soft);
  color: var(--primary-strong);
}

.nav__item.router-link-active::before {
  content: '';
  position: absolute;
  left: -16px;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 20px;
  border-radius: 0 3px 3px 0;
  background: var(--primary);
}

.nav__icon {
  font-size: 16px;
  flex: none;
}

.nav__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.3;
}

.nav__title {
  font-size: 13.5px;
  font-weight: 550;
}

.nav__desc {
  margin-top: 3px;
  font-size: 10.5px;
  color: var(--ink-3);
  letter-spacing: 0.01em;
}

.nav__item.router-link-active .nav__desc {
  color: #7b79c9;
}

.nav__arrow {
  margin-left: auto;
  opacity: 0;
  transform: translateX(-3px);
  transition: opacity 0.16s ease, transform 0.16s ease;
  color: currentColor;
}

.nav__item:hover .nav__arrow,
.nav__item.router-link-active .nav__arrow {
  opacity: 0.6;
  transform: translateX(0);
}

.sidebar__foot {
  padding-top: 12px;
  border-top: 1px solid var(--line);
}

.mode-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 10px;
  border-radius: 10px;
  background: var(--surface-2);
  border: 1px solid var(--line);
}

.mode-card__text p {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-2);
  line-height: 1.3;
}

.mode-card__text small {
  font-size: 10.5px;
  color: var(--ink-3);
}

/* ---------------- 主区域 ---------------- */
.main {
  flex: 1;
  min-width: 0;
  margin-left: var(--shell-sidebar);
  display: flex;
  flex-direction: column;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 30;
  display: flex;
  align-items: center;
  gap: 14px;
  height: 60px;
  padding: 0 32px;
  background: rgba(244, 245, 249, 0.86);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid rgba(232, 234, 242, 0.8);
}

.crumbs {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  color: var(--ink-3);
  min-width: 0;
}

.crumbs__group {
  white-space: nowrap;
}

.crumbs__sep {
  color: var(--ink-4);
}

.crumbs__current {
  color: var(--ink);
  font-weight: 550;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topbar__right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}

.topbar__menu {
  flex: none;
}

.icon-btn {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: 9px;
  color: var(--ink-2);
  cursor: pointer;
}

.icon-btn:hover {
  border-color: var(--line-strong);
  color: var(--ink);
}

/* 移动端才出现的菜单按钮：写在 .icon-btn 之后，避免被 display:grid 覆盖 */
.topbar__menu {
  display: none;
}

.user-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 38px;
  padding: 0 10px 0 5px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface);
  color: var(--ink-2);
  cursor: pointer;
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}

.user-btn:hover {
  border-color: var(--line-strong);
  box-shadow: var(--shadow-xs);
}

.avatar {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: linear-gradient(145deg, #6c6ae4, #4340b5);
  color: #fff;
  font-size: 12px;
  font-weight: 650;
  letter-spacing: 0.02em;
}

.user-btn__name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12.5px;
  font-weight: 550;
}

.user-btn__caret {
  font-size: 11px;
  color: var(--ink-3);
}

.content {
  flex: 1;
  width: 100%;
  max-width: 1320px;
  margin: 0 auto;
  padding: 26px 32px 56px;
}

/* ---------------- 弹窗内容 ---------------- */
.account {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border-radius: 12px;
  background: var(--surface-2);
  border: 1px solid var(--line);
}

.account__avatar {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: linear-gradient(145deg, #6c6ae4, #4340b5);
  color: #fff;
  font-weight: 650;
}

.account__name {
  font-size: 15px;
  font-weight: 600;
}

.account__meta {
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--ink-3);
}

.account__list {
  margin: 14px 0 0;
  display: flex;
  flex-direction: column;
}

.account__list > div {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 9px 2px;
  border-bottom: 1px dashed var(--line);
  font-size: 12.5px;
}

.account__list > div:last-child {
  border-bottom: 0;
}

.account__list dt {
  color: var(--ink-3);
}

.account__list dd {
  margin: 0;
  color: var(--ink-2);
  font-variant-numeric: tabular-nums;
}

.scrim {
  position: fixed;
  inset: 0;
  z-index: 35;
  background: rgba(11, 14, 32, 0.42);
  backdrop-filter: blur(2px);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

@media (max-width: 960px) {
  .sidebar {
    transform: translateX(-100%);
    transition: transform 0.24s cubic-bezier(0.22, 0.61, 0.36, 1);
    box-shadow: var(--shadow-pop);
  }

  .sidebar.is-open {
    transform: translateX(0);
  }

  .main {
    margin-left: 0;
  }

  .topbar {
    padding: 0 18px;
  }

  .topbar__menu {
    display: grid;
  }

  .content {
    padding: 20px 18px 44px;
  }
}

@media (max-width: 480px) {
  .crumbs__group,
  .crumbs__sep {
    display: none;
  }

  .user-btn__name {
    display: none;
  }

  .user-btn {
    padding: 0 6px;
  }
}
</style>
