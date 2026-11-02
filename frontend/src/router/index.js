import { createRouter, createWebHistory } from 'vue-router'

import { getToken } from '@/api/client'
import { DEBUG_ENABLED } from '@/constants'
import { useAuthStore } from '@/stores/auth'
import { pinia } from '@/stores'
import { safeRedirect } from '@/utils/redirect'

const AppLayout = () => import('@/layouts/AppLayout.vue')
const AuthLayout = () => import('@/layouts/AuthLayout.vue')

const routes = [
  {
    path: '/welcome',
    name: 'welcome',
    component: () => import('@/views/LandingView.vue'),
    meta: { title: '开始使用' },
  },
  {
    // 用唯一父路径承载鉴权页；子路由用绝对路径，URL 保持干净的 /login、/register
    // （此前父路径写 '/' 会与应用外壳的 '/' 冲突，导致根路径匹配不到内容）
    path: '/auth',
    component: AuthLayout,
    children: [
      {
        path: '/login',
        name: 'login',
        component: () => import('@/views/auth/LoginView.vue'),
        meta: { title: '登录', guestOnly: true },
      },
      {
        path: '/register',
        name: 'register',
        component: () => import('@/views/auth/RegisterView.vue'),
        meta: { title: '注册', guestOnly: true },
      },
    ],
  },
  {
    path: '/',
    component: AppLayout,
    meta: { requiresAuth: true },
    children: [
      // 未登录访问站点根路径时，先落到公开入口页，而不是直接跳登录表单
      {
        path: '',
        redirect: () => (getToken() ? { name: 'diagnosis' } : { name: 'welcome' }),
      },
      {
        path: 'resume',
        name: 'diagnosis',
        component: () => import('@/views/diagnosis/DiagnosisView.vue'),
        meta: { title: '简历诊断', group: '工作台', requiresAuth: true },
      },
      {
        path: 'interview',
        name: 'interview',
        component: () => import('@/views/interview/InterviewView.vue'),
        meta: { title: '模拟面试', group: '工作台', requiresAuth: true },
      },
      {
        path: 'growth',
        name: 'growth',
        component: () => import('@/views/growth/GrowthView.vue'),
        meta: { title: '成长闭环', group: '工作台', requiresAuth: true },
      },
      {
        path: 'debug',
        name: 'debug',
        component: () => import('@/views/debug/DebugView.vue'),
        meta: { title: '检索调试台', group: '工具', requiresAuth: true, requiresDev: true },
      },
    ],
  },
  {
    path: '/404',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: '页面不存在' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/404' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const auth = useAuthStore(pinia)

  // 首次进入先做一次鉴权自检（有 token → /auth/me）
  if (!auth.bootstrapped) await auth.bootstrap()

  if (to.meta.requiresDev && !DEBUG_ENABLED) return { name: 'not-found' }

  if (to.meta.guestOnly && auth.isAuthed) {
    return safeRedirect(to.query.redirect) || { name: 'diagnosis' }
  }

  if (to.meta.requiresAuth && !auth.isAuthed) {
    const redirect = to.fullPath && to.fullPath !== '/' ? to.fullPath : undefined
    return { name: 'login', query: redirect ? { redirect } : {} }
  }

  return true
})

router.afterEach((to) => {
  document.title = to.meta.title
    ? `${to.meta.title} · IntelliCareer`
    : 'IntelliCareer · AI 面试备战工作台'
})

export default router
