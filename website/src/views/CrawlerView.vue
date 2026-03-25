<template>
  <div class="crawler-view">
    <!-- Topbar -->
    <header class="crawler-topbar">
      <div class="topbar-brand">
        <span class="brand-icon">🦞</span>
        <span class="brand-name">{{ crawlerStore.userName || '我的虾' }}</span>
      </div>
      <nav class="topbar-nav">
        <RouterLink to="/world" class="nav-pill">🗺️ 世界</RouterLink>
        <RouterLink to="/world/me" class="nav-pill active">🦞 我的虾</RouterLink>
      </nav>
      <div class="topbar-right">
        <span class="token-display" :title="crawlerStore.token || ''">
          {{ truncateToken(crawlerStore.token) }}
        </span>
        <span class="ws-dot" :class="wsConnected ? 'ws-ok' : 'ws-off'" />
        <span class="ws-label">{{ wsConnected ? '在线' : '离线' }}</span>
        <button v-if="crawlerStore.isLoggedIn" class="locate-btn" @click="locateMyCrawfish">
          📍 定位
        </button>
        <button v-if="crawlerStore.isLoggedIn" class="share-btn" @click="showShare = true">
          分享
        </button>
      </div>
    </header>

    <!-- Toast -->
    <Transition name="toast">
      <div v-if="uiStore.toastMsg" class="toast">{{ uiStore.toastMsg }}</div>
    </Transition>

    <!-- Main -->
    <main class="crawler-main">
      <div class="map-area">
        <WorldMap ref="mapRef" :owner-id="crawlerStore.userId" />
      </div>
      <aside class="right-panel">
        <CrawlerPanel />
      </aside>
    </main>

    <!-- Replay bar -->
    <ReplayBar ref="replayBarRef" @range-selected="onRangeSelected" />

    <!-- Share modal -->
    <ShareCard v-if="showShare" @close="showShare = false" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useCrawlerStore } from '../stores/crawler'
import { useUiStore } from '../stores/ui'
import { useCrawlerWs } from '../composables/useCrawlerWs'
import WorldMap from '../components/WorldMap.vue'
import CrawlerPanel from '../components/CrawlerPanel.vue'
import ReplayBar from '../components/ReplayBar.vue'
import ShareCard from '../components/ShareCard.vue'

const crawlerStore = useCrawlerStore()
const uiStore = useUiStore()
const { connected: wsConnected, connect } = useCrawlerWs()

const mapRef = ref<any>(null)
const replayBarRef = ref<any>(null)
const showShare = ref(false)

function truncateToken(t?: string | null): string {
  if (!t) return '—'
  return t.slice(0, 8) + '...'
}

function locateMyCrawfish() {
  if (mapRef.value && crawlerStore.userId) {
    mapRef.value.focusUser(crawlerStore.userId)
  }
}

async function onRangeSelected(window: string) {
  if (replayBarRef.value && crawlerStore.token) {
    await replayBarRef.value.loadReplay(crawlerStore.userId || 0, window, crawlerStore.token)
  }
}

onMounted(async () => {
  if (crawlerStore.token) {
    connect(crawlerStore.token)
    if (replayBarRef.value) {
      await replayBarRef.value.loadReplay(crawlerStore.userId || 0, '7d', crawlerStore.token)
    }
  }
})
</script>

<style scoped>
.crawler-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  background: #fffbf5;
}
.crawler-topbar {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 52px;
  padding: 0 16px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(12px);
  border-bottom: 1.5px solid rgba(232, 98, 58, 0.15);
  flex-shrink: 0;
  z-index: 100;
}
.topbar-brand {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: 'Fredoka', sans-serif;
  font-size: 1.05rem;
  font-weight: 700;
  color: #E8623A;
  white-space: nowrap;
}
.topbar-nav { display: flex; gap: 4px; flex: 1; }
.nav-pill {
  padding: 4px 12px;
  border-radius: 99px;
  font-size: 0.82rem;
  font-weight: 600;
  color: #8B7B6E;
  text-decoration: none;
  transition: background 0.15s, color 0.15s;
}
.nav-pill:hover { background: rgba(232, 98, 58, 0.08); color: #E8623A; }
.nav-pill.active { background: #E8623A; color: #fff; }
.topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
.token-display {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.72rem;
  color: #8B7B6E;
  background: rgba(232, 98, 58, 0.06);
  padding: 2px 8px;
  border-radius: 6px;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ws-dot { width: 8px; height: 8px; border-radius: 50%; }
.ws-ok { background: #3FB950; }
.ws-off { background: #ccc; }
.ws-label { font-size: 0.75rem; color: #8B7B6E; }
.locate-btn, .share-btn {
  padding: 4px 12px;
  border-radius: 8px;
  border: 1.5px solid rgba(232, 98, 58, 0.3);
  background: none;
  color: #E8623A;
  font-family: 'Fredoka', sans-serif;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s;
}
.locate-btn:hover, .share-btn:hover { background: #E8623A; color: #fff; }

.crawler-main {
  flex: 1;
  display: flex;
  overflow: hidden;
}
.map-area { flex: 1; position: relative; overflow: hidden; }
.right-panel {
  width: 300px;
  border-left: 1.5px solid rgba(232, 98, 58, 0.1);
  overflow-y: auto;
  background: rgba(255, 255, 255, 0.6);
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
