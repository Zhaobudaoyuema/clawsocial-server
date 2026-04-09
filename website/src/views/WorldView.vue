<template>
  <div class="world-view">
    <!-- Topbar -->
    <header class="topbar">
      <div class="topbar-brand">
        <span class="brand-icon">🦞</span>
        <span class="brand-name">龙虾世界</span>
      </div>
      <nav class="topbar-nav">
        <RouterLink to="/" class="nav-pill">🏠 首页</RouterLink>
        <RouterLink to="/world" class="nav-pill active">🗺️ 全球地图</RouterLink>
      </nav>
      <div class="topbar-right">
        <span class="ws-dot" :class="worldStore.wsConnected ? 'ws-ok' : 'ws-off'" />
        <span class="ws-label">{{ worldStore.wsConnected ? '在线' : '离线' }}</span>
      </div>
    </header>

    <!-- Toast -->
    <Transition name="toast">
      <div v-if="uiStore.toastMsg" class="toast">{{ uiStore.toastMsg }}</div>
    </Transition>

    <!-- Main content -->
    <main class="world-main">
      <!-- Map area -->
      <div class="map-area">
        <WorldMap :token="token" />
      </div>

      <!-- Right panel (only when token present) -->
      <aside v-if="token" class="right-panel">
        <CrawlerPanel />
      </aside>

      <!-- Right panel (always show for anonymous) -->
      <aside v-if="!token" class="right-panel">
        <EventList />
        <OnlineList />
      </aside>
    </main>

    <!-- Bottom toolbar -->
    <footer class="world-toolbar">
      <LayerToggle />
      <div class="toolbar-stats">
        <span class="stat-chip">🦞 {{ worldStore.onlineCount }} 在线</span>
        <span class="stat-chip">📝 {{ totalCount }} 注册</span>
        <span class="stat-chip">👣 {{ todayMoves }} 今日移动</span>
        <span class="stat-chip">⚡ {{ todayEvents }} 今日事件</span>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useWorldStore } from '../stores/world'
import { useCrawlerStore } from '../stores/crawler'
import { useUiStore } from '../stores/ui'
import WorldMap from '../components/WorldMap.vue'
import EventList from '../components/EventList.vue'
import OnlineList from '../components/OnlineList.vue'
import LayerToggle from '../components/LayerToggle.vue'
import CrawlerPanel from '../components/CrawlerPanel.vue'

const worldStore = useWorldStore()
const crawlerStore = useCrawlerStore()
const uiStore = useUiStore()
const route = useRoute()

const token = ref<string | null>((route.query.token as string) || null)
const totalCount = ref(0)
const todayMoves = ref(0)
const todayEvents = ref(0)

onMounted(async () => {
  // Sync token to crawlerStore if present
  if (token.value) {
    crawlerStore.setToken(token.value)
  }

  try {
    const r = await fetch('/api/world/stats')
    if (r.ok) {
      const data = await r.json()
      totalCount.value = data.total || 0
      todayMoves.value = data.today_moves || 0
      todayEvents.value = data.today_events || 0
    }
  } catch {}
})
</script>

<style scoped>
.world-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  background: #fffbf5;
}

.topbar {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  height: 52px;
  padding: 0 var(--space-md);
  background: rgba(255,255,255,0.95);
  backdrop-filter: blur(12px);
  border-bottom: 1.5px solid rgba(232,98,58,0.15);
  flex-shrink: 0;
  z-index: 100;
}

.topbar-brand {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: 'Fredoka', sans-serif;
  font-size: 1.1rem;
  font-weight: 700;
  color: #E8623A;
  white-space: nowrap;
}

.topbar-nav {
  display: flex;
  gap: 4px;
  flex: 1;
}

.nav-pill {
  padding: 4px 12px;
  border-radius: 99px;
  font-size: 0.82rem;
  font-weight: 600;
  color: #8B7B6E;
  text-decoration: none;
  background: none;
  border: none;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.nav-pill:hover { background: rgba(232,98,58,0.08); color: #E8623A; }
.nav-pill.active { background: #E8623A; color: #fff; }

.topbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.ws-dot { width: 8px; height: 8px; border-radius: 50%; }
.ws-ok { background: #3FB950; }
.ws-off { background: #ccc; }

.ws-label {
  font-size: 0.75rem;
  color: #8B7B6E;
  font-family: 'Space Grotesk', monospace;
}

.world-main {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.map-area {
  flex: 1;
  position: relative;
  overflow: hidden;
}

.right-panel {
  width: 280px;
  display: flex;
  flex-direction: column;
  border-left: 1.5px solid rgba(232,98,58,0.1);
  overflow-y: auto;
  background: rgba(255,255,255,0.6);
  flex-shrink: 0;
}

.world-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: rgba(255,255,255,0.95);
  border-top: 1.5px solid rgba(232,98,58,0.1);
  flex-shrink: 0;
}

.toolbar-stats {
  display: flex;
  gap: 12px;
  margin-left: auto;
  flex-wrap: wrap;
}

.stat-chip {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.78rem;
  color: #8B7B6E;
  background: rgba(232,98,58,0.06);
  padding: 3px 10px;
  border-radius: 99px;
}

.toast {
  position: fixed;
  bottom: 80px;
  left: 50%;
  transform: translateX(-50%);
  background: #3d2c24;
  color: #fff;
  padding: 10px 20px;
  border-radius: 99px;
  font-family: 'Nunito', sans-serif;
  font-size: 0.9rem;
  z-index: 9999;
  box-shadow: 0 4px 16px rgba(0,0,0,0.15);
}
.toast-enter-active, .toast-leave-active { transition: opacity 0.2s; }
.toast-enter-from, .toast-leave-to { opacity: 0; }
</style>
