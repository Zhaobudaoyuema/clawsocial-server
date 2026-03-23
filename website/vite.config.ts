import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  // 输出到 FastAPI 静态文件目录，官网和 /world/ 共用一个服务
  base: '/',
  build: {
    outDir: resolve(__dirname, '../app/static'),
    emptyOutDir: true,
  },
  server: {
    // 开发时代理 API 请求到 FastAPI 服务
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
