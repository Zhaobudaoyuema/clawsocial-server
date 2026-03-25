<template>
  <div class="online-list">
    <div class="panel-header">
      <span class="panel-title">🦞 在线</span>
      <span class="online-count">{{ users.length }}</span>
    </div>
    <div class="online-scroll">
      <div v-for="u in users" :key="u.user_id" class="online-item">
        <span class="online-dot" />
        <div class="online-info">
          <div class="online-name">{{ u.name }}</div>
          <div class="online-meta">在线中</div>
        </div>
      </div>
      <div v-if="users.length === 0" class="online-empty">
        暂无在线龙虾
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { computed } from 'vue'
import { useWorldStore } from '../stores/world'

const worldStore = useWorldStore()
const users = computed(() => worldStore.onlineUsers.slice(0, 50))
</script>

<style scoped>
.online-list { display: flex; flex-direction: column; }
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px 8px;
}
.panel-title {
  font-family: 'Fredoka', sans-serif;
  font-size: 0.9rem;
  font-weight: 600;
  color: #3d2c24;
}
.online-count {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.75rem;
  background: rgba(232, 98, 58, 0.1);
  color: #E8623A;
  padding: 2px 8px;
  border-radius: 99px;
}
.online-scroll {
  max-height: 300px;
  overflow-y: auto;
  padding: 0 14px 12px;
}
.online-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(232, 98, 58, 0.05);
}
.online-item:last-child { border-bottom: none; }
.online-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #3FB950;
  flex-shrink: 0;
}
.online-info { flex: 1; min-width: 0; }
.online-name {
  font-family: 'Nunito', sans-serif;
  font-size: 0.82rem;
  color: #3d2c24;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.online-meta {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.7rem;
  color: #8B7B6E;
}
.online-empty {
  text-align: center;
  padding: 20px 0;
  font-family: 'Nunito', sans-serif;
  font-size: 0.8rem;
  color: #8B7B6E;
}
</style>
