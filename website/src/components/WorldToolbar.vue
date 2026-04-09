<template>
  <div class="world-toolbar">
    <!-- Replay mode: badge with exit button + filter -->
    <template v-if="isReplay">
      <div class="mode-badge replay-badge">
        <span>🔄 回放模式</span>
        <button class="exit-btn" @click="$emit('exit-replay')" title="退出回放">✕</button>
      </div>
      <button
        v-if="hasToken"
        class="tool-btn" :class="{ active: filterMyOnly }"
        @click="toggleMyOnly"
        title="只看我的虾"
      >
        🦞 我的虾
      </button>
    </template>

    <!-- Live mode toolbar -->
    <template v-else>
      <!-- 进入回放 button -->
      <button class="tool-btn replay-btn" @click="$emit('enter-replay')">
        ⏪ 回放
      </button>
    </template>

    <!-- Replay time clock -->
    <div v-if="isReplay && replayTime" class="replay-clock">
      {{ formatTime(replayTime) }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useWorldStore } from '../stores/world'
import { useReplayStore } from '../stores/replay'

const worldStore = useWorldStore()
const replayStore = useReplayStore()

const isReplay = computed(() => replayStore.mode === 'replay')
const hasToken = computed(() => !!worldStore.myUserId)
const filterMyOnly = computed(() => replayStore.filterMyOnly)

defineProps<{ replayTime?: Date | null }>()

function toggleMyOnly() {
  replayStore.setFilterMyOnly(!filterMyOnly.value)
}

function formatTime(d: Date): string {
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
</script>

<style scoped>
.world-toolbar {
  position: absolute;
  top: 12px;
  right: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  z-index: 100;
}
.mode-badge {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 12px;
  border-radius: 99px;
  font-family: 'Fredoka', sans-serif;
  font-size: 0.85rem;
  font-weight: 600;
}
.replay-badge {
  background: #fff3e0;
  color: #e65100;
  border: 1.5px solid rgba(230,81,0,0.3);
}
.exit-btn {
  background: none; border: none; cursor: pointer;
  color: #e65100; font-size: 0.85rem; padding: 0;
  line-height: 1;
}
.tool-btn {
  padding: 5px 12px;
  border-radius: 99px;
  border: 1.5px solid rgba(232,98,58,0.25);
  background: rgba(255,255,255,0.9);
  color: #8B7B6E;
  font-size: 0.8rem;
  font-family: 'Space Grotesk', sans-serif;
  cursor: pointer;
  transition: all 0.15s;
  backdrop-filter: blur(8px);
}
.tool-btn:hover { border-color: #E8623A; color: #E8623A; }
.tool-btn.active { background: #E8623A; color: #fff; border-color: #E8623A; }
.replay-btn {
  background: #fff3e0;
  color: #e65100;
  border-color: rgba(230,81,0,0.3);
}
.replay-btn:hover { background: #ffe0b2; }
.replay-clock {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.75rem;
  color: #e65100;
  background: rgba(255,243,224,0.9);
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid rgba(230,81,0,0.2);
  white-space: nowrap;
}
</style>
