<script setup lang="ts">
import { onMounted, provide, ref, watch } from 'vue'
import { useDeidStore } from '../stores/deid'
import DeidTopBar from '../components/deid/DeidTopBar.vue'
import DeidLeftRail from '../components/deid/DeidLeftRail.vue'
import DeidMainStage from '../components/deid/DeidMainStage.vue'
import '../styles/deid-tokens.css'

const store = useDeidStore()
const activeJobId = ref<number | null>(null)
const railOpen = ref(false)

onMounted(async () => {
  await store.fetchJobs()
  await store.fetchEntityTypes()
  await store.fetchWorkerStatus()
  await store.fetchQueueStatus()
  await store.restoreCurrentJob()
  const cur = store.currentJob as { id?: number } | null
  if (cur?.id) activeJobId.value = cur.id
})

watch(
  () => [store.showEntitiesPanel, store.showConclusionView, store.showRehydratePanel] as const,
  ([entities, conclusion, rehydrate]) => {
    if (entities || conclusion || rehydrate) closeRail()
  },
)

async function onSelectJob(job: Record<string, unknown>) {
  activeJobId.value = job.id as number
  store.closeEntitiesPanel()
  store.closeConclusionView()
  store.closeRehydratePanel()
  closeRail()
  await store.selectJob(job)
}

function onNewTask() {
  activeJobId.value = null
  store.closeEntitiesPanel()
  store.closeConclusionView()
  store.closeRehydratePanel()
  closeRail()
  store.newTask()
}

function onOpenEntities() {
  activeJobId.value = null
  closeRail()
  store.openEntitiesPanel()
}

function onOpenRehydrate() {
  activeJobId.value = null
  closeRail()
  store.openRehydratePanel()
}

function toggleRail() {
  railOpen.value = !railOpen.value
}

function closeRail() {
  railOpen.value = false
}

provide('closeDeidRail', closeRail)

function onJobDeleted(jobId: number) {
  if (activeJobId.value === jobId) {
    activeJobId.value = null
  }
  closeRail()
}
</script>

<template>
  <div class="deid-app">
    <DeidTopBar :menu-open="railOpen" @toggle-menu="toggleRail" />
    <div
      v-if="railOpen"
      class="drawer-backdrop"
      aria-hidden="true"
      @click="closeRail"
    />
    <div class="shell">
      <DeidLeftRail
        :active-job-id="activeJobId"
        :entities-active="store.showEntitiesPanel"
        :rehydrate-active="store.showRehydratePanel"
        :drawer-open="railOpen"
        @select="onSelectJob"
        @new-task="onNewTask"
        @open-entities="onOpenEntities"
        @open-rehydrate="onOpenRehydrate"
        @close-drawer="closeRail"
        @deleted="onJobDeleted"
      />
      <DeidMainStage />
    </div>
  </div>
</template>

<style scoped>
.deid-app {
  min-height: 100vh;
}
.shell {
  display: flex;
  min-height: calc(100vh - var(--deid-topbar-height));
  position: relative;
}
@media (min-width: 769px) {
  .deid-app {
    height: 100vh;
    min-height: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .shell {
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }
}
.drawer-backdrop {
  display: none;
}
@media (max-width: 768px) {
  .drawer-backdrop {
    display: block;
    position: fixed;
    top: var(--deid-topbar-height);
    left: min(300px, 88vw);
    right: 0;
    bottom: 0;
    z-index: calc(var(--deid-drawer-z-index) - 1);
    background: rgba(15, 15, 15, 0.35);
  }
}
</style>
