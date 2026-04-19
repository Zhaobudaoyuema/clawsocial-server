<template>
  <div class="replay-bar">
    <!-- Time range buttons -->
    <div class="time-btns">
      <button v-for="t in timeRanges" :key="t.key"
        class="time-btn" :class="{ active: activeRange === t.key }"
        @click="selectRange(t.key)">
        {{ t.label }}
      </button>
    </div>

    <!-- Slider -->
    <div class="slider-wrap">
      <span class="time-label">{{ fmtTime(store.rangeStart) }}</span>
      <input
        type="range"
        class="replay-slider"
        :min="sliderMin"
        :max="sliderMax"
        :value="sliderValue"
        @input="onSliderInput"
      />
      <span class="time-label">{{ fmtTime(store.rangeEnd) }}</span>
    </div>

    <!-- Current time display -->
    <div class="current-time">{{ fmtTime(store.currentTime) }}</div>

    <!-- Playback controls -->
    <div class="playback-controls">
      <button class="ctrl-btn" @click="store.reset()" title="重置到开始">⏮</button>
      <button class="play-btn" @click="togglePlay">
        {{ store.replaying ? '⏸' : '▶' }}
      </button>
    </div>

    <!-- Speed buttons -->
    <div class="speed-btns">
      <button v-for="s in speeds" :key="s"
        class="speed-btn" :class="{ active: store.playbackSpeed === s }"
        @click="store.setSpeed(s)">
        {{ s }}x
      </button>
    </div>

    <!-- Exit replay -->
    <button class="exit-replay-btn" @click="emit('exit-replay')" title="退出回放">
      ✕ 退出回放
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useReplayStore } from '../stores/replay'

const store = useReplayStore()

const emit = defineEmits<{
  rangeSelected: [window: string]
  'exit-replay': []
}>()

const sliderMin = computed<number>(() => store.rangeStart ? store.rangeStart.getTime() : 0)
const sliderMax = computed<number>(() => store.rangeEnd ? store.rangeEnd.getTime() : 1)
const sliderValue = computed<number>(() => store.currentTime ? store.currentTime.getTime() : 0)

const timeRanges = [
  { key: '1h', label: '1h' },
  { key: '24h', label: '24h' },
  { key: '7d', label: '7d' },
]
const speeds = [1, 2, 5, 10]
const activeRange = ref('24h')

function togglePlay() {
  if (store.replaying) store.pause()
  else store.play()
}

function onSliderInput(e: Event) {
  const val = Number((e.target as HTMLInputElement).value)
  store.seekTo(new Date(val))
}

function selectRange(key: string) {
  activeRange.value = key
  emit('rangeSelected', key)
}

function fmtTime(d: Date | null | undefined): string {
  if (!d) return '—'
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getMonth()+1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
</script>

<style scoped>
.replay-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: rgba(255,255,255,0.97);
  border-top: 1.5px solid rgba(232,98,58,0.12);
}
.time-btns { display: flex; gap: 4px; }
.time-btn {
  padding: 3px 10px; border-radius: 8px;
  border: 1.5px solid rgba(232,98,58,0.2); background: none;
  color: #8B7B6E; font-family: 'Space Grotesk', monospace;
  font-size: 0.78rem; cursor: pointer; transition: all 0.15s;
}
.time-btn.active { background: #E8623A; color: #fff; border-color: #E8623A; }
.time-btn:hover:not(.active) { border-color: #E8623A; color: #E8623A; }

.slider-wrap { flex: 1; display: flex; align-items: center; gap: 8px; }
.replay-slider {
  flex: 1; -webkit-appearance: none; height: 4px;
  border-radius: 2px; background: rgba(232,98,58,0.2); outline: none;
}
.replay-slider::-webkit-slider-thumb {
  -webkit-appearance: none; width: 14px; height: 14px;
  border-radius: 50%; background: #E8623A; cursor: pointer;
}
.time-label {
  font-family: 'Space Grotesk', monospace; font-size: 0.7rem;
  color: #8B7B6E; white-space: nowrap;
}

.playback-controls { display: flex; gap: 4px; }
.ctrl-btn {
  width: 28px; height: 28px; border-radius: 50%; border: 1.5px solid rgba(232,98,58,0.3);
  background: rgba(255,255,255,0.9); color: #E8623A; font-size: 0.75rem;
  cursor: pointer; display: flex; align-items: center;
  justify-content: center; transition: all 0.1s;
}
.ctrl-btn:hover { background: rgba(232,98,58,0.1); }
.play-btn {
  width: 32px; height: 32px; border-radius: 50%; border: none;
  background: #E8623A; color: #fff; font-size: 0.85rem;
  cursor: pointer; display: flex; align-items: center;
  justify-content: center; transition: transform 0.1s;
}
.play-btn:hover { transform: scale(1.1); }

.speed-btns { display: flex; gap: 2px; }
.speed-btn {
  padding: 3px 8px; border-radius: 6px;
  border: 1px solid rgba(232,98,58,0.2); background: none;
  color: #8B7B6E; font-family: 'Space Grotesk', monospace;
  font-size: 0.72rem; cursor: pointer; transition: all 0.15s;
}
.speed-btn.active { background: rgba(232,98,58,0.12); color: #E8623A; border-color: #E8623A; }

.exit-replay-btn {
  margin-left: 4px;
  padding: 4px 12px;
  border-radius: 99px;
  border: 1.5px solid rgba(230,81,0,0.3);
  background: #fff3e0;
  color: #e65100;
  font-family: 'Fredoka', sans-serif;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}
.exit-replay-btn:hover { background: #ffe0b2; }

.current-time {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.72rem;
  color: #e65100;
  background: rgba(255,243,224,0.9);
  padding: 3px 10px;
  border-radius: 6px;
  border: 1px solid rgba(230,81,0,0.15);
  white-space: nowrap;
  min-width: 120px;
  text-align: center;
}
</style>
