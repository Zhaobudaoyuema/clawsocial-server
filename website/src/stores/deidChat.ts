import { defineStore } from 'pinia'
import { ref } from 'vue'

const API = '/api/deid/chat'

export type ChatMessage = {
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
}

async function readJson<T = unknown>(r: Response): Promise<T> {
  const text = await r.text()
  if (!r.ok) throw new Error(text || r.statusText || '请求失败')
  return JSON.parse(text) as T
}

export const useDeidChatStore = defineStore('deidChat', () => {
  const sessionId = ref<string | null>(null)
  const docLabel = ref<string | null>(null)
  const messages = ref<ChatMessage[]>([])
  const sending = ref(false)
  const error = ref<string | null>(null)
  const chatJobs = ref<Record<string, unknown>[]>([])

  async function fetchChatJobs() {
    chatJobs.value = await readJson(await fetch(`${API}/jobs`))
  }

  async function startSession(mode: 'none' | 'job' | 'upload', opts?: { jobId?: number; file?: File }) {
    error.value = null
    messages.value = []
    const fd = new FormData()
    fd.append('mode', mode)
    if (mode === 'job' && opts?.jobId) {
      fd.append('job_id', String(opts.jobId))
    }
    if (mode === 'upload' && opts?.file) {
      fd.append('file', opts.file)
    }
    const data = await readJson<{ session_id: string; doc_label?: string | null }>(
      await fetch(`${API}/sessions`, { method: 'POST', body: fd }),
    )
    sessionId.value = data.session_id
    docLabel.value = data.doc_label ?? null
    return data
  }

  async function sendMessage(content: string) {
    if (!sessionId.value || !content.trim()) return
    sending.value = true
    error.value = null
    const userText = content.trim()
    messages.value.push({ role: 'user', content: userText })
    const assistantIdx = messages.value.length
    messages.value.push({ role: 'assistant', content: '', streaming: true })

    try {
      const r = await fetch(`${API}/sessions/${sessionId.value}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: userText }),
      })
      if (!r.ok || !r.body) {
        throw new Error(await r.text())
      }
      const reader = r.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''
        for (const block of parts) {
          const line = block.split('\n').find((l) => l.startsWith('data:'))
          if (!line) continue
          const payload = JSON.parse(line.slice(5).trim()) as {
            type: string
            content?: string
            message?: string
          }
          if (payload.type === 'token' && payload.content) {
            messages.value[assistantIdx].content += payload.content
          } else if (payload.type === 'error') {
            throw new Error(payload.message || 'worker_error')
          }
        }
      }
      messages.value[assistantIdx].streaming = false
      if (!messages.value[assistantIdx].content) {
        messages.value[assistantIdx].content = '（无回复）'
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : '发送失败'
      messages.value[assistantIdx].content = `错误：${error.value}`
      messages.value[assistantIdx].streaming = false
    } finally {
      sending.value = false
    }
  }

  function resetLocal() {
    sessionId.value = null
    docLabel.value = null
    messages.value = []
    error.value = null
  }

  return {
    sessionId,
    docLabel,
    messages,
    sending,
    error,
    chatJobs,
    fetchChatJobs,
    startSession,
    sendMessage,
    resetLocal,
  }
})
