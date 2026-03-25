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
      <span class="time-label">{{ formatTs(rangeStart) }}</span>
      <input
        type="range"
        class="replay-slider"
        :min="rangeStart ? rangeStart.getTime() : 0"
        :max="rangeEnd ? rangeEnd.getTime() : 1"
        :value="currentTime ? currentTime.getTime() : 0"
        @input="onSliderInput"
      />
      <span class="time-label">{{ formatTs(rangeEnd) }}</span>
    </div>

    <!-- Playback controls -->
    <div class="playback-controls">
      <button class="play-btn" @click="togglePlay">
        {{ replaying ? '⏸' : '▶' }}
      </button>
    </div>

    <!-- Speed buttons -->
    <div class="speed-btns">
      <button v-for="s in speeds" :key="s"
        class="speed-btn" :class="{ active: playbackSpeed === s }"
        @click="setSpeed(s)">
        {{ s }}x
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useReplay } from '../composables/useReplay'

const {
  replaying, playbackSpeed, currentTime, rangeStart, rangeEnd,
  play, pause, seekTo, setSpeed, loadReplay
} = useReplay()

const emit = defineEmits<{ rangeSelected: [window: string] }>()

const timeRanges = [
  { key: '1h', label: '1h' },
  { key: '24h', label: '24h' },
  { key: '7d', label: '7d' },
]
const speeds = [1, 2, 5, 10]
const activeRange = ref('7d')

function togglePlay() {
  if (replaying.value) pause()
  else play()
}

function onSliderInput(e: Event) {
  const val = Number((e.target as HTMLInputElement).value)
  seekTo(new Date(val))
}

function selectRange(key: string) {
  activeRange.value = key
  emit('rangeSelected', key)
}

function formatTs(d: Date | null): string {
  if (!d) return '—'
  return `${d.getMonth()+1}/${d.getDate()} ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`
}

// Expose for parent
defineExpose({ loadReplay })
</script>

<style scoped>
.replay-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.97);
  border-top: 1.5px solid rgba(232, 98, 58, 0.12);
}
.time-btns { display: flex; gap: 4px; }
.time-btn {
  padding: 3px 10px;
  border-radius: 8px;
  border: 1.5px solid rgba(232, 98, 58, 0.2);
  background: none;
  color: #8B7B6E;
  font-family: 'Space Grotesk', monospace;
  font-size: 0.78rem;
  cursor: pointer;
  transition: all 0.15s;
}
.time-btn.active { background: #E8623A; color: #fff; border-color: #E8623A; }
.time-btn:hover:not(.active) { border-color: #E8623A; color: #E8623A; }

.slider-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
}
.replay-slider {
  flex: 1;
  -webkit-appearance: none;
  height: 4px;
  border-radius: 2px;
  background: rgba(232, 98, 58, 0.2);
  outline: none;
}
.replay-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #E8623A;
  cursor: pointer;
}
.time-label {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.7rem;
  color: #8B7B6E;
  white-space: nowrap;
}

.playback-controls { display: flex; }
.play-btn {
  width: 32px; height: 32px;
  border-radius: 50%;
  border: none;
  background: #E8623A;
  color: #fff;
  font-size: 0.85rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.1s;
}
.play-btn:hover { transform: scale(1.1); }

.speed-btns { display: flex; gap: 2px; }
.speed-btn {
  padding: 3px 8px;
  border-radius: 6px;
  border: 1px solid rgba(232, 98, 58, 0.2);
  background: none;
  color: #8B7B6E;
  font-family: 'Space Grotesk', monospace;
  font-size: 0.72rem;
  cursor: pointer;
  transition: all 0.15s;
}
.speed-btn.active { background: rgba(232, 98, 58, 0.12); color: #E8623A; border-color: #E8623A; }
</style>
