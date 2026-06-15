<template>
  <div class="drop-page">
    <div class="drop-container">
      <h1 class="drop-title">🦞 文件投递</h1>
      <p class="drop-subtitle">拖放文件上传，获得在线链接</p>

      <!-- 口令输入 -->
      <div class="passcode-row">
        <input
          v-model="passcode"
          type="password"
          placeholder="输入口令"
          class="passcode-input"
          @keyup.enter="savePasscode"
        />
        <label class="remember-label">
          <input type="checkbox" v-model="rememberPasscode" @change="savePasscode" />
          记住口令
        </label>
      </div>

      <!-- 拖放上传区 -->
      <div
        class="dropzone"
        :class="{ 'dropzone--active': isDragging, 'dropzone--uploading': isUploading }"
        @dragover.prevent="isDragging = true"
        @dragleave.prevent="isDragging = false"
        @drop.prevent="handleDrop"
        @click="triggerFileInput"
      >
        <input
          ref="fileInput"
          type="file"
          multiple
          class="hidden-input"
          @change="handleFileSelect"
        />
        <div v-if="isUploading" class="dropzone-uploading">
          <div class="spinner"></div>
          <span>上传中…</span>
        </div>
        <div v-else class="dropzone-content">
          <span class="dropzone-icon">📎</span>
          <span>拖放文件到此处</span>
          <span class="dropzone-hint">或点击选择文件</span>
        </div>
      </div>

      <!-- 上传结果 -->
      <div v-if="lastUpload" class="upload-result">
        <span class="result-label">✅ 上传成功</span>
        <code class="result-url">{{ lastUpload.url }}</code>
        <button class="copy-btn" @click="copyUrl(lastUpload.url)">📋 复制链接</button>
      </div>

      <!-- 错误提示 -->
      <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>

      <!-- 文件列表 -->
      <div class="file-list-section">
        <h2 class="section-title">已上传文件</h2>
        <div v-if="files.length === 0" class="empty-state">暂无文件</div>
        <table v-else class="file-table">
          <thead>
            <tr>
              <th>文件名</th>
              <th>大小</th>
              <th>来源</th>
              <th>时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="f in files" :key="f.id">
              <td class="filename-cell" :title="f.filename">{{ f.filename }}</td>
              <td>{{ formatSize(f.size) }}</td>
              <td>
                <span class="source-badge" :class="'source-' + f.source">{{ f.source }}</span>
              </td>
              <td class="time-cell">{{ formatTime(f.created_at) }}</td>
              <td>
                <button class="copy-btn-sm" @click="copyUrl(f.url)">📋</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="total > files.length" class="pagination">
          显示 {{ files.length }} / 共 {{ total }} 个文件
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const API_BASE = ''  // same origin

const passcode = ref('')
const rememberPasscode = ref(true)
const isDragging = ref(false)
const isUploading = ref(false)
const lastUpload = ref<{ url: string; filename: string } | null>(null)
const errorMsg = ref('')
const files = ref<any[]>([])
const total = ref(0)
const fileInput = ref<HTMLInputElement | null>(null)

onMounted(() => {
  // restore passcode
  const saved = localStorage.getItem('drop_passcode')
  if (saved) {
    passcode.value = saved
    rememberPasscode.value = true
  }
  fetchFiles()
})

function savePasscode() {
  if (rememberPasscode.value && passcode.value) {
    localStorage.setItem('drop_passcode', passcode.value)
  } else {
    localStorage.removeItem('drop_passcode')
  }
}

function triggerFileInput() {
  fileInput.value?.click()
}

function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) {
    for (const f of input.files) {
      uploadFile(f)
    }
    input.value = ''
  }
}

function handleDrop(e: DragEvent) {
  isDragging.value = false
  if (e.dataTransfer?.files) {
    for (const f of e.dataTransfer.files) {
      uploadFile(f)
    }
  }
}

async function uploadFile(file: File) {
  if (!passcode.value) {
    errorMsg.value = '请先输入口令'
    return
  }
  errorMsg.value = ''
  isUploading.value = true

  try {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('source', 'web')

    const res = await fetch(`${API_BASE}/api/drop/upload`, {
      method: 'POST',
      headers: { 'X-Drop-Passcode': passcode.value },
      body: formData,
    })

    const data = await res.json()

    if (!res.ok) {
      errorMsg.value = data.error || '上传失败'
      return
    }

    lastUpload.value = { url: data.url, filename: data.filename }
    savePasscode()
    fetchFiles()
  } catch (err: any) {
    errorMsg.value = '网络错误：' + (err.message || '未知')
  } finally {
    isUploading.value = false
  }
}

async function fetchFiles() {
  try {
    const res = await fetch(`${API_BASE}/api/drop/files?limit=100`)
    const data = await res.json()
    files.value = data.files || []
    total.value = data.total || 0
  } catch {
    // silent fail
  }
}

function copyUrl(url: string) {
  navigator.clipboard.writeText(url).catch(() => {
    // fallback: select text
  })
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function formatTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.drop-page {
  min-height: 100vh;
  background: #fffbf5;
  padding: 40px 20px;
  font-family: 'Nunito', sans-serif;
  color: #3d2c24;
}

.drop-container {
  max-width: 720px;
  margin: 0 auto;
}

.drop-title {
  font-size: 28px;
  font-weight: 700;
  margin: 0 0 4px;
}

.drop-subtitle {
  font-size: 15px;
  color: #8b7b6e;
  margin: 0 0 24px;
}

/* 口令输入 */
.passcode-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.passcode-input {
  padding: 8px 14px;
  border: 2px solid #f0e6d8;
  border-radius: 8px;
  font-size: 14px;
  font-family: inherit;
  background: #fff;
  width: 200px;
  outline: none;
  transition: border-color 0.2s;
}

.passcode-input:focus {
  border-color: #E8623A;
}

.remember-label {
  font-size: 13px;
  color: #8b7b6e;
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}

/* 拖放区 */
.dropzone {
  border: 2px dashed #ddd0c3;
  border-radius: 12px;
  padding: 48px 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  background: #fff;
  margin-bottom: 16px;
}

.dropzone:hover {
  border-color: #E8623A;
  background: #fff8f5;
}

.dropzone--active {
  border-color: #E8623A;
  background: #fff0e8;
  transform: scale(1.01);
}

.dropzone--uploading {
  border-color: #E8623A;
  pointer-events: none;
  opacity: 0.8;
}

.dropzone-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  font-size: 16px;
}

.dropzone-icon {
  font-size: 32px;
}

.dropzone-hint {
  font-size: 13px;
  color: #8b7b6e;
}

.dropzone-uploading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  font-size: 15px;
  color: #E8623A;
}

.hidden-input {
  display: none;
}

/* Spinner */
.spinner {
  width: 20px;
  height: 20px;
  border: 3px solid #f0e6d8;
  border-top-color: #E8623A;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 上传结果 */
.upload-result {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #f0fff4;
  border: 1px solid #c6f6d5;
  border-radius: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.result-label {
  font-weight: 600;
  color: #276749;
  font-size: 14px;
}

.result-url {
  flex: 1;
  font-size: 13px;
  background: #edf2f7;
  padding: 4px 8px;
  border-radius: 4px;
  word-break: break-all;
  min-width: 200px;
}

.copy-btn {
  padding: 6px 12px;
  border: 1px solid #ddd0c3;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
  font-family: inherit;
  transition: all 0.15s;
}

.copy-btn:hover {
  background: #fff0e8;
  border-color: #E8623A;
}

/* 错误 */
.error-msg {
  color: #c53030;
  font-size: 14px;
  padding: 10px 14px;
  background: #fff5f5;
  border-radius: 8px;
  margin-bottom: 16px;
}

/* 文件列表 */
.file-list-section {
  margin-top: 32px;
}

.section-title {
  font-size: 18px;
  font-weight: 700;
  margin: 0 0 12px;
}

.empty-state {
  text-align: center;
  color: #8b7b6e;
  padding: 24px;
  font-size: 14px;
}

.file-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.file-table th {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 2px solid #f0e6d8;
  font-weight: 600;
  color: #8b7b6e;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.file-table td {
  padding: 10px;
  border-bottom: 1px solid #f5efe8;
}

.file-table tr:hover td {
  background: #fffbf5;
}

.filename-cell {
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.time-cell {
  color: #8b7b6e;
  font-size: 13px;
  white-space: nowrap;
}

.source-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}

.source-web {
  background: #f0e6d8;
  color: #6b5c50;
}

.source-agent {
  background: rgba(232, 98, 58, 0.08);
  color: #E8623A;
  border: 1px solid rgba(232, 98, 58, 0.2);
}

.copy-btn-sm {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 16px;
  padding: 2px 6px;
  border-radius: 4px;
  transition: background 0.15s;
}

.copy-btn-sm:hover {
  background: #f0e6d8;
}

.pagination {
  text-align: center;
  color: #8b7b6e;
  font-size: 13px;
  margin-top: 12px;
}
</style>
