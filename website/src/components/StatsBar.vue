<template>
  <div class="stats-bar">
    <div class="stat-item">
      <span class="stat-dot online"></span>
      <span class="stat-val">{{ online }}</span>
      <span class="stat-lbl">在线</span>
    </div>
    <div class="stat-sep"></div>
    <div class="stat-item">
      <span class="stat-dot today"></span>
      <span class="stat-val">{{ today }}</span>
      <span class="stat-lbl">今日注册</span>
    </div>
    <div class="stat-sep"></div>
    <div class="stat-item">
      <span class="stat-dot total"></span>
      <span class="stat-val">{{ total }}</span>
      <span class="stat-lbl">总用户</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const online = ref(0)
const today = ref(0)
const total = ref(0)

async function fetchStats() {
  try {
    const res = await fetch('/api/world/stats')
    const data = await res.json()
    total.value = data.total || 0
    today.value = data.today_new || 0
  } catch {}
}

async function fetchOnline() {
  try {
    const res = await fetch('/api/world/online')
    const data = await res.json()
    online.value = data.count || 0
  } catch {}
}

onMounted(async () => {
  await fetchStats()
  await fetchOnline()
  // 每 30 秒刷新一次
  setInterval(async () => {
    await fetchStats()
    await fetchOnline()
  }, 30000)
})
</script>

<style scoped>
.stats-bar {
  display: flex;
  align-items: center;
  gap: 0;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(14px);
  border: 1.5px solid #f0e6d8;
  border-radius: 40px;
  padding: 8px 20px;
  font-family: 'Nunito', sans-serif;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 12px;
}

.stat-item:first-child {
  padding-left: 0;
}
.stat-item:last-child {
  padding-right: 0;
}

.stat-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.stat-dot.online { background: #3fb950; }
.stat-dot.today { background: #e8623a; }
.stat-dot.total { background: #f4a261; }

.stat-val {
  font-family: 'Space Grotesk', monospace;
  font-weight: 700;
  font-size: 0.95rem;
  color: #3d2c24;
}

.stat-lbl {
  font-size: 0.78rem;
  color: #8b7b6e;
  font-weight: 500;
}

.stat-sep {
  width: 1px;
  height: 16px;
  background: #f0e6d8;
}

@media (max-width: 500px) {
  .stats-bar {
    padding: 6px 12px;
  }
  .stat-lbl {
    display: none;
  }
}
</style>
