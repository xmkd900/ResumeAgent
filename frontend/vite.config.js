import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // 后端默认 8000；前端统一请求 /api/v1，由代理转发，避免本地跨域
    proxy: {
      '/api': {
        // 固定 127.0.0.1：Node 解析 localhost 时可能优先走 ::1，而 uvicorn 常只监听 IPv4
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        // 按实际引用分包（不要用入口名字符串，否则会把 echarts 整包拉进来）
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('echarts') || id.includes('zrender')) return 'echarts'
          if (id.includes('element-plus') || id.includes('@element-plus')) return 'element'
          if (id.includes('/vue/') || id.includes('vue-router') || id.includes('pinia')) return 'vue'
          return 'vendor'
        },
      },
    },
  },
})
