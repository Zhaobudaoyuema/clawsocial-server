<template>
  <div class="layer-toggle">
    <button
      v-for="l in layers" :key="l.key"
      class="layer-btn"
      :class="{ active: uiStore.layerMode === l.key }"
      @click="uiStore.setLayerMode(l.key)"
    >
      {{ l.icon }} {{ l.label }}
    </button>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { useUiStore } from '../stores/ui'

const uiStore = useUiStore()
const layers = [
  { key: 'crawfish', label: '虾', icon: '🦞' },
  { key: 'heatmap', label: '热点', icon: '🔥' },
  { key: 'trail', label: '轨迹', icon: '📍' },
  { key: 'both', label: '全开', icon: '🗺️' },
]
</script>

<style scoped>
.layer-toggle { display: flex; gap: 4px; }
.layer-btn {
  padding: 4px 12px;
  border-radius: 8px;
  border: 1.5px solid rgba(232, 98, 58, 0.25);
  background: rgba(255, 255, 255, 0.8);
  color: #8B7B6E;
  font-family: 'Nunito', sans-serif;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.layer-btn:hover { border-color: #E8623A; color: #E8623A; }
.layer-btn.active { background: #E8623A; color: #fff; border-color: #E8623A; }
</style>
