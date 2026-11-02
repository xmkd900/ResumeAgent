import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { ElMessage } from 'element-plus'

import 'element-plus/dist/index.css'
import '@/styles/tokens.css'
import '@/styles/base.css'
import '@/styles/element.css'

import App from './App.vue'
import router from './router'
import { pinia } from './stores'
import { useAuthStore } from './stores/auth'

const app = createApp(App)

app.use(pinia)
app.use(router)
app.use(ElementPlus, { locale: zhCn })

// token 被后端拒绝（401）时统一登出并带回跳地址
const auth = useAuthStore(pinia)
window.addEventListener('auth:unauthorized', () => {
  if (!auth.handleUnauthorized()) return
  ElMessage.warning('登录状态已失效，请重新登录')
  const current = router.currentRoute.value
  const redirect = current.meta?.requiresAuth ? current.fullPath : undefined
  router.replace({ name: 'login', query: redirect ? { redirect } : {} })
})

app.mount('#app')
