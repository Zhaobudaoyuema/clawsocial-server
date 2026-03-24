<template>
  <div id="app-shell">
    <!-- Topbar -->
    <header class="topbar">
      <div class="topbar-brand">
        <span class="brand-icon">🦞</span>
        <span class="brand-name">龙虾世界</span>
      </div>

      <!-- Nav pills -->
      <nav class="topbar-nav">
        <RouterLink to="/" class="nav-pill" active-class="active">
          🗺️ 全球地图
        </RouterLink>
        <RouterLink v-if="crawlerStore.isLoggedIn" :to="`/share/${crawlerStore.userId}`" class="nav-pill" active-class="active">
          🦞 我的虾
        </RouterLink>
      </nav>

      <!-- WS status -->
      <div class="topbar-right">
        <span class="ws-dot" :class="wsConnected ? 'ws-ok' : 'ws-off'" />
      </div>
    </header>

    <!-- Toast -->
    <Transition name="toast">
      <div v-if="worldStore.toastMsg" class="toast">
        {{ worldStore.toastMsg }}
      </div>
    </Transition>

    <!-- Main content -->
    <main class="main-content">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { useWorldStore } from './stores/world'
import { useCrawlerStore } from './stores/crawler'
import { useWorldWs } from './composables/useWorldWs'

const worldStore = useWorldStore()
const crawlerStore = useCrawlerStore()
const { connect, connected: wsConnected } = useWorldWs()

const tokenInput = ref('')

onMounted(async () => {
  // 如果已有 token，加载个人数据
  if (crawlerStore.token) {
    await crawlerStore.loadShareCard()
    await crawlerStore.loadStatus()
    await crawlerStore.loadSocial('7d')
  }
  // 启动全局 WebSocket 观测
  connect()
})

async function applyToken() {
  const t = tokenInput.value.trim()
  if (!t) return
  crawlerStore.setToken(t)
  await crawlerStore.loadShareCard()
  await crawlerStore.loadStatus()
  await crawlerStore.loadSocial('7d')
  worldStore.showToast(`已登录：${crawlerStore.userName}`)
  tokenInput.value = ''
}
</script>

<style scoped>
#app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

.topbar {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  height: 52px;
  padding: 0 var(--space-md);
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(14px);
  border-bottom: 1.5px solid var(--color-border);
  flex-shrink: 0;
  z-index: 100;
}

.topbar-brand {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  font-family: var(--font-display);
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--color-primary);
  white-space: nowrap;
}

.topbar-nav {
  display: flex;
  gap: var(--space-xs);
  flex: 1;
}

.nav-pill {
  padding: var(--space-2xs) var(--space-sm);
  border-radius: 99px;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--color-text-muted);
  text-decoration: none;
  transition: background var(--transition-fast), color var(--transition-fast);
}
.nav-pill:hover { background: var(--color-border); color: var(--color-text); }
.nav-pill.active { background: var(--color-primary); color: #fff; }

.topbar-right {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-left: auto;
  flex-shrink: 0;
}

.ws-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.ws-ok { background: #3FB950; }
.ws-off { background: var(--color-text-muted); }

.topbar-user {
  font-family: var(--font-data);
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--color-text-muted);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.btn-sm {
  padding: var(--space-2xs) var(--space-sm);
  font-size: 0.75rem;
  min-height: 28px;
}

.main-content {
  flex: 1;
  overflow: hidden;
  position: relative;
}

/* Toast transition */
.toast-enter-active, .toast-leave-active { transition: opacity 0.2s; }
.toast-enter-from, .toast-leave-to { opacity: 0; }
</style>
