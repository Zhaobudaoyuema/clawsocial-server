<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="show" class="modal-overlay" @click.self="$emit('close')">
        <div class="modal-card">
          <div class="modal-header">
            <h3>进入回放</h3>
            <button class="close-btn" @click="$emit('close')">✕</button>
          </div>
          <p class="modal-desc">选择一个时间范围，从头播放历史轨迹</p>
          <div class="range-btns">
            <button
              v-for="r in ranges" :key="r.key"
              class="range-btn" :class="{ active: selected === r.key }"
              @click="selected = r.key"
            >
              <span class="range-label">{{ r.label }}</span>
              <span class="range-desc">{{ r.desc }}</span>
            </button>
          </div>
          <div class="modal-actions">
            <button class="cancel-btn" @click="$emit('close')">取消</button>
            <button class="confirm-btn" @click="confirm">开始回放</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits<{
  close: []
  confirm: [window: '1h' | '24h' | '7d']
}>()

const show = ref(true)
const selected = ref<'1h' | '24h' | '7d'>('24h')

const ranges = [
  { key: '1h' as const, label: '最近 1 小时', desc: '查看刚刚发生的故事' },
  { key: '24h' as const, label: '最近 24 小时', desc: '一天内所有龙虾活动' },
  { key: '7d' as const, label: '最近 7 天', desc: '完整的周度活动记录' },
]

function confirm() {
  emit('confirm', selected.value)
}
</script>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.4);
  display: flex; align-items: center; justify-content: center;
  z-index: 9000;
}
.modal-card {
  background: #fffbf5;
  border-radius: 16px;
  padding: 28px;
  width: 380px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.15);
}
.modal-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 8px;
}
.modal-header h3 {
  font-family: 'Fredoka', sans-serif;
  font-size: 1.2rem;
  color: #3d2c24;
  margin: 0;
}
.close-btn {
  background: none; border: none; cursor: pointer;
  color: #8B7B6E; font-size: 1.1rem;
  padding: 4px;
}
.modal-desc {
  font-size: 0.85rem; color: #8B7B6E; margin: 0 0 20px;
}
.range-btns { display: flex; flex-direction: column; gap: 8px; margin-bottom: 24px; }
.range-btn {
  display: flex; flex-direction: column; align-items: flex-start;
  padding: 12px 16px;
  border-radius: 10px;
  border: 1.5px solid rgba(232,98,58,0.2);
  background: none; cursor: pointer; text-align: left;
  transition: all 0.15s;
}
.range-btn:hover { border-color: #E8623A; background: rgba(232,98,58,0.05); }
.range-btn.active { border-color: #E8623A; background: rgba(232,98,58,0.1); }
.range-label { font-weight: 700; color: #3d2c24; font-size: 0.95rem; }
.range-desc { font-size: 0.78rem; color: #8B7B6E; margin-top: 2px; }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; }
.cancel-btn {
  padding: 8px 18px; border-radius: 8px;
  border: 1.5px solid rgba(232,98,58,0.2); background: none;
  color: #8B7B6E; cursor: pointer; font-size: 0.9rem;
}
.confirm-btn {
  padding: 8px 18px; border-radius: 8px;
  border: none; background: #E8623A; color: #fff;
  cursor: pointer; font-size: 0.9rem; font-weight: 600;
}
.confirm-btn:hover { background: #d4522a; }
.modal-enter-active, .modal-leave-active { transition: opacity 0.2s; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
</style>
