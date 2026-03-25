import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUiStore = defineStore('ui', () => {
  // Panel collapse state
  const eventPanelOpen = ref(true)
  const friendPanelOpen = ref(false)
  const encounterPanelOpen = ref(false)

  // Current layer mode
  const layerMode = ref<'crawfish' | 'heatmap' | 'trail' | 'both'>('both')

  // Toast notification
  const toastMsg = ref<string | null>(null)
  let toastTimer: ReturnType<typeof setTimeout> | null = null

  function toggleEventPanel() { eventPanelOpen.value = !eventPanelOpen.value }
  function toggleFriendPanel() { friendPanelOpen.value = !friendPanelOpen.value }
  function toggleEncounterPanel() { encounterPanelOpen.value = !encounterPanelOpen.value }
  function setLayerMode(mode: typeof layerMode.value) { layerMode.value = mode }

  function showToast(msg: string) {
    toastMsg.value = msg
    if (toastTimer) clearTimeout(toastTimer)
    toastTimer = setTimeout(() => { toastMsg.value = null }, 3000)
  }

  return {
    eventPanelOpen,
    friendPanelOpen,
    encounterPanelOpen,
    layerMode,
    toastMsg,
    toggleEventPanel,
    toggleFriendPanel,
    toggleEncounterPanel,
    setLayerMode,
    showToast,
  }
})
