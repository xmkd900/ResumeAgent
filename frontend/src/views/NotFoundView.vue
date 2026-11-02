<script setup>
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

function goHome() {
  router.replace(auth.isAuthed ? '/resume' : '/welcome')
}
</script>

<template>
  <div class="notfound">
    <div class="notfound__code num">404</div>
    <h1>这个页面不存在</h1>
    <p>链接可能已失效，或者该页面只对开发者开放。</p>
    <el-button type="primary" @click="goHome">
      {{ auth.isAuthed ? '回到简历诊断' : '返回首页' }}
    </el-button>
  </div>
</template>

<style scoped>
.notfound {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 32px;
  text-align: center;
  background: radial-gradient(70% 50% at 50% 20%, #f0effd 0%, transparent 70%), var(--bg);
}

.notfound__code {
  font-size: 72px;
  font-weight: 700;
  letter-spacing: -0.06em;
  line-height: 1;
  color: var(--primary);
  opacity: 0.18;
}

.notfound h1 {
  font-size: 20px;
  letter-spacing: -0.02em;
}

.notfound p {
  font-size: 13px;
  color: var(--ink-3);
  margin-bottom: 8px;
}
</style>
