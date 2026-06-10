<script setup lang="ts">
import { ref } from 'vue'
import { setDeidAccessToken, verifyDeidDayCode } from '../../utils/deidAccess'

const emit = defineEmits<{ unlocked: [] }>()

const token = ref('')
const error = ref<string | null>(null)
const loading = ref(false)

async function submit() {
  const value = token.value.trim()
  if (!value) {
    error.value = '请输入口令'
    return
  }
  loading.value = true
  error.value = null
  try {
    const session = await verifyDeidDayCode(value)
    if (!session) {
      error.value = '口令不正确'
      return
    }
    setDeidAccessToken(session)
    emit('unlocked')
  } catch {
    error.value = '验证失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="gate">
    <div class="gate-card deid-panel">
      <h1 class="gate-title">文档脱敏</h1>
      <p class="gate-sub">请输入今日访问口令以继续</p>
      <form class="gate-form" @submit.prevent="submit">
        <input
          v-model="token"
          class="deid-input gate-input"
          type="text"
          inputmode="numeric"
          autocomplete="off"
          placeholder="访问口令"
          :disabled="loading"
        />
        <p v-if="error" class="gate-error" role="alert">{{ error }}</p>
        <button type="submit" class="deid-btn deid-btn--primary deid-btn--lg" :disabled="loading">
          {{ loading ? '验证中…' : '进入' }}
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.gate {
  min-height: calc(100vh - var(--deid-topbar-height));
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem 1.25rem;
  background: var(--deid-bg);
}
.gate-card {
  width: 100%;
  max-width: 400px;
  padding: 2rem 1.75rem;
  text-align: center;
}
.gate-title {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--deid-ink);
}
.gate-sub {
  margin: 0.5rem 0 1.5rem;
  font-size: 0.9375rem;
  color: var(--deid-ink-muted);
}
.gate-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.gate-input {
  text-align: center;
  font-size: 1.125rem;
  letter-spacing: 0.05em;
}
.gate-error {
  margin: 0;
  font-size: 0.875rem;
  color: var(--deid-danger);
}
</style>
