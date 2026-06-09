<script setup lang="ts">
import { inject } from 'vue'
import { useDeidStore } from '../../stores/deid'

const store = useDeidStore()
const closeRail = inject<(() => void) | undefined>('closeDeidRail', undefined)

function openEntities() {
  closeRail?.()
  store.openEntitiesPanel()
}
</script>

<template>
  <div class="worker-banner" role="status">
    <span class="msg">
      智能扫描暂不可用：将自动匹配「我的实体」中已记住的名称
    </span>
    <button type="button" class="link" @click="openEntities">
      管理实体
    </button>
  </div>
</template>

<style scoped>
.worker-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  padding: 0.85rem 1.1rem;
  margin-bottom: 1.25rem;
  background: var(--deid-warning-bg);
  border: 1px solid var(--deid-warning-border);
  border-radius: var(--deid-radius);
  font-size: 0.9375rem;
  color: var(--deid-warning);
}
.msg {
  flex: 1;
  min-width: 200px;
}
.link {
  border: none;
  background: none;
  color: var(--deid-primary);
  font-weight: 600;
  cursor: pointer;
  font-size: 0.9375rem;
  font-family: inherit;
  white-space: nowrap;
}
.link:hover {
  text-decoration: underline;
}
</style>
