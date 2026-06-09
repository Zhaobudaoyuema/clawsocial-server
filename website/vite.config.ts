import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const proxyTarget = env.VITE_DEV_PROXY_TARGET || 'http://localhost:8000'
  const wsTarget = proxyTarget.replace(/^http/i, 'ws')

  return {
    plugins: [vue()],
    // 输出到 FastAPI 静态文件目录，官网和 /world/ 共用一个服务
    // 注意：base 必须是 '/'，否则 Vue 资源会挂到 /world/ 下，与世界地图路由冲突
    base: '/',
    build: {
      outDir: resolve(__dirname, '../app/static'),
      emptyOutDir: true,
    },
    server: {
      // 开发时代理 API 请求到 FastAPI 服务
      // 设置 VITE_DEV_PROXY_TARGET=https://clawsocial.world 可只调试前端、API 走生产
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
          secure: true,
        },
        '/ws': {
          target: wsTarget,
          ws: true,
          changeOrigin: true,
          secure: true,
        },
      },
    },
  }
})
