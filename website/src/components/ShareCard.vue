<template>
  <div class="share-overlay" @click.self="$emit('close')">
    <div class="share-card">
      <div class="card-icon">🔗</div>
      <h2 class="card-title">分享你的虾</h2>

      <!-- 已存在分享链接 -->
      <div v-if="existingShare" class="share-link-box">
        <div class="share-url">{{ existingShare.url }}</div>
        <div class="share-meta">
          <span v-if="existingShare.expires_at">到期: {{ formatDate(existingShare.expires_at) }}</span>
          <span v-else>永不过期</span>
          <span>· {{ existingShare.speed }}x 倍速</span>
        </div>
      </div>

      <!-- 创建新分享 -->
      <div v-else class="share-form">
        <div class="form-group">
          <label>过期时间</label>
          <div class="radio-group">
            <label v-for="e in expiryOptions" :key="e.value" class="radio-label">
              <input type="radio" v-model="expiresDays" :value="e.value" />
              {{ e.label }}
            </label>
          </div>
        </div>

        <div class="form-group">
          <label>回放倍速</label>
          <div class="speed-group">
            <button v-for="s in speeds" :key="s"
              class="speed-btn" :class="{ active: speed === s }"
              @click="speed = s">
              {{ s }}x
            </button>
          </div>
        </div>

        <button class="create-btn" @click="createShare" :disabled="creating">
          {{ creating ? '生成中...' : '生成分享链接' }}
        </button>
      </div>

      <!-- 操作按钮 -->
      <div class="card-actions">
        <button v-if="existingShare" class="copy-btn" @click="copyLink">
          📋 复制链接
        </button>
        <button v-if="existingShare" class="revoke-btn" @click="revokeShare">
          撤销
        </button>
        <button class="close-btn" @click="$emit('close')">关闭</button>
      </div>

      <div v-if="copied" class="copied-msg">✅ 链接已复制</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useCrawlerStore } from '../stores/crawler'

const emit = defineEmits<{ close: [] }>()
const crawlerStore = useCrawlerStore()

const existingShare = ref<any>(null)
const expiresDays = ref('never')
const speed = ref(1)
const creating = ref(false)
const copied = ref(false)

const expiryOptions = [
  { value: '7', label: '7天' },
  { value: '30', label: '30天' },
  { value: 'never', label: '永久' },
]
const speeds = [1, 2, 5, 10]

function formatDate(iso: string) {
  const d = new Date(iso)
  return `${d.getFullYear()}-${(d.getMonth()+1).toString().padStart(2,'0')}-${d.getDate().toString().padStart(2,'0')}`
}

async function loadStatus() {
  if (!crawlerStore.token) return
  try {
    const r = await fetch('/api/share/status', { headers: { 'X-Token': crawlerStore.token } })
    if (r.ok) {
      const data = await r.json()
      if (data.has_token) existingShare.value = data
    }
  } catch {}
}

async function createShare() {
  if (!crawlerStore.token) return
  creating.value = true
  try {
    const r = await fetch('/api/share/create', {
      method: 'POST',
      headers: {
        'X-Token': crawlerStore.token,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ speed: speed.value, expires_days: expiresDays.value }),
    })
    if (r.ok) {
      existingShare.value = await r.json()
    }
  } catch {}
  creating.value = false
}

async function revokeShare() {
  if (!crawlerStore.token) return
  try {
    await fetch('/api/share/revoke', {
      method: 'POST',
      headers: { 'X-Token': crawlerStore.token },
    })
    existingShare.value = null
  } catch {}
}

async function copyLink() {
  if (!existingShare.value?.url) return
  try {
    await navigator.clipboard.writeText(existingShare.value.url)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {}
}

onMounted(() => loadStatus())
</script>

<style scoped>
.share-overlay {
  position: fixed;
  inset: 0;
  background: rgba(61, 44, 36, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}
.share-card {
  background: #fffbf5;
  border-radius: 22px;
  padding: 32px;
  max-width: 420px;
  width: 90%;
  text-align: center;
  box-shadow: 0 8px 32px rgba(232, 98, 58, 0.15);
}
.card-icon { font-size: 2.5rem; margin-bottom: 8px; }
.card-title {
  font-family: 'Fredoka', sans-serif;
  font-size: 1.3rem;
  color: #3d2c24;
  margin: 0 0 20px;
}
.share-link-box {
  background: rgba(232, 98, 58, 0.06);
  border-radius: 10px;
  padding: 14px;
  margin-bottom: 16px;
  word-break: break-all;
  text-align: left;
}
.share-url {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.8rem;
  color: #3d2c24;
  word-break: break-all;
  margin-bottom: 6px;
}
.share-meta {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.72rem;
  color: #8B7B6E;
}
.share-form { margin-bottom: 16px; }
.form-group { margin-bottom: 16px; text-align: left; }
.form-group label {
  display: block;
  font-family: 'Nunito', sans-serif;
  font-size: 0.85rem;
  font-weight: 600;
  color: #3d2c24;
  margin-bottom: 8px;
}
.radio-group { display: flex; gap: 8px; }
.radio-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-family: 'Nunito', sans-serif;
  font-size: 0.82rem;
  color: #3d2c24;
  cursor: pointer;
}
.speed-group { display: flex; gap: 6px; }
.speed-btn {
  padding: 6px 14px;
  border-radius: 8px;
  border: 1.5px solid rgba(232, 98, 58, 0.2);
  background: none;
  color: #8B7B6E;
  font-family: 'Space Grotesk', monospace;
  font-size: 0.82rem;
  cursor: pointer;
  transition: all 0.15s;
}
.speed-btn.active { background: #E8623A; color: #fff; border-color: #E8623A; }
.create-btn {
  width: 100%;
  padding: 12px;
  border-radius: 10px;
  border: none;
  background: #E8623A;
  color: #fff;
  font-family: 'Fredoka', sans-serif;
  font-size: 0.95rem;
  cursor: pointer;
  transition: background 0.15s;
}
.create-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.create-btn:hover:not(:disabled) { background: #D4542B; }
.card-actions { display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; }
.copy-btn {
  padding: 8px 18px;
  border-radius: 10px;
  border: none;
  background: #E8623A;
  color: #fff;
  font-family: 'Fredoka', sans-serif;
  font-size: 0.85rem;
  cursor: pointer;
}
.revoke-btn {
  padding: 8px 18px;
  border-radius: 10px;
  border: 1.5px solid rgba(232, 98, 58, 0.3);
  background: none;
  color: #E8623A;
  font-family: 'Fredoka', sans-serif;
  font-size: 0.85rem;
  cursor: pointer;
}
.close-btn {
  padding: 8px 18px;
  border-radius: 10px;
  border: none;
  background: none;
  color: #8B7B6E;
  font-family: 'Nunito', sans-serif;
  font-size: 0.85rem;
  cursor: pointer;
}
.copied-msg {
  margin-top: 10px;
  font-family: 'Nunito', sans-serif;
  font-size: 0.85rem;
  color: #3FB950;
}
</style>
