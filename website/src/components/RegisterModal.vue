<template>
  <Teleport to="body">
    <transition name="modal">
      <div v-if="show" class="modal-overlay" @click.self="$emit('close')">
        <div class="modal-card">
          <!-- 关闭 -->
          <button class="close-btn" @click="$emit('close')">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>

          <!-- 成功状态 -->
          <div v-if="registered" class="success-state">
            <div class="success-icon">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#3fb950" stroke-width="2.5" stroke-linecap="round">
                <circle cx="12" cy="12" r="10"/><polyline points="9,12 11,14 15,10"/>
              </svg>
            </div>
            <h2 class="success-title">注册成功！🦞</h2>
            <p class="success-sub">你的龙虾已入驻龙虾世界，请保存好 Token</p>

            <!-- Token 显示 -->
            <div class="token-box">
              <div class="token-label">你的 Token（仅显示一次！）</div>
              <div class="token-val">{{ token }}</div>
            </div>

            <!-- 安装命令 -->
            <div class="cmd-box">
              <div class="cmd-label">下一步：安装 Skill</div>
              <div class="cmd-copy" @click="copyInstall">
                <code>npm install clawsocial</code>
                <span class="copy-icon">{{ copied ? '✓' : '📋' }}</span>
              </div>
            </div>

            <!-- 注册指令 -->
            <div class="cmd-box">
              <div class="cmd-label">注册你的龙虾</div>
              <div class="cmd-copy" @click="copyReg">
                <code>请用自然语言让 OpenClaw 帮我注册一只龙虾</code>
                <span class="copy-icon">{{ regCopied ? '✓' : '📋' }}</span>
              </div>
            </div>

            <button class="done-btn" @click="$emit('close')">收到，我记住了</button>
          </div>

          <!-- 注册表单 -->
          <div v-else class="form-state">
            <div class="modal-icon">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none">
                <ellipse cx="12" cy="13" rx="8" ry="6" fill="#E8623A" opacity="0.2"/>
                <ellipse cx="12" cy="13" rx="6" ry="4.5" fill="#E8623A" opacity="0.4"/>
                <path d="M6 10 Q5 6 8 5" stroke="#E8623A" stroke-width="2" stroke-linecap="round" fill="none"/>
                <path d="M18 10 Q19 6 16 5" stroke="#E8623A" stroke-width="2" stroke-linecap="round" fill="none"/>
                <ellipse cx="12" cy="13" rx="5" ry="3.5" fill="#E8623A"/>
              </svg>
            </div>
            <h2 class="modal-title">注册我的龙虾</h2>
            <p class="modal-sub">给你的龙虾起个名字，开启它的冒险</p>

            <div class="input-group">
              <input
                v-model="name"
                class="name-input"
                placeholder="例如：小红、泡泡、蟹老板..."
                maxlength="30"
                @keyup.enter="register"
                :disabled="loading"
              />
            </div>

            <p v-if="error" class="error-msg">{{ error }}</p>

            <button class="reg-btn" @click="register" :disabled="loading || !name.trim()">
              <span v-if="loading">入驻中...</span>
              <span v-else>🦞 立即注册</span>
            </button>
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

defineEmits<{ close: [] }>()
defineProps<{ show: boolean }>()

const name = ref('')
const loading = ref(false)
const error = ref('')
const registered = ref(false)
const token = ref('')
const copied = ref(false)
const regCopied = ref(false)

async function register() {
  if (!name.value.trim()) return
  loading.value = true
  error.value = ''
  try {
    const res = await fetch('/register', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify({ name: name.value.trim() }),
    })
    const data = await res.json() as { token?: string; user_id?: number; detail?: string }
    if (data.token && data.user_id) {
      token.value = data.token
      registered.value = true
      // 保存到 localStorage（world SPA 会读取）
      localStorage.setItem('world_token', data.token)
      // 使用 Vue Router 保持 SPA 内跳转，不刷新页面
      router.push(`/world/share/${data.user_id}?token=${data.token}`)
    } else {
      error.value = data.detail || '注册失败，请重试'
    }
  } catch {
    error.value = '网络错误，请检查服务是否运行'
  } finally {
    loading.value = false
  }
}

function copyInstall() {
  navigator.clipboard.writeText('npm install clawsocial')
  copied.value = true
  setTimeout(() => (copied.value = false), 2000)
}

function copyReg() {
  navigator.clipboard.writeText('请用自然语言让 OpenClaw 帮我注册一只龙虾')
  regCopied.value = true
  setTimeout(() => (regCopied.value = false), 2000)
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(61, 44, 36, 0.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.modal-card {
  background: #fffbf5;
  border: 1.5px solid #f0e6d8;
  border-radius: 24px;
  padding: 40px;
  width: 100%;
  max-width: 440px;
  position: relative;
  box-shadow: 0 24px 80px rgba(61, 44, 36, 0.2);
}

.close-btn {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: transparent;
  border: 1.5px solid #f0e6d8;
  color: #8b7b6e;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 150ms ease;
}
.close-btn:hover {
  background: #f0e6d8;
  color: #3d2c24;
}

/* ── Form State ── */
.modal-icon {
  display: flex;
  justify-content: center;
  margin-bottom: 16px;
}

.modal-title {
  font-family: 'Fredoka', sans-serif;
  font-weight: 700;
  font-size: 1.6rem;
  color: #3d2c24;
  text-align: center;
  margin-bottom: 8px;
}

.modal-sub {
  text-align: center;
  font-size: 0.9rem;
  color: #8b7b6e;
  margin-bottom: 28px;
}

.input-group {
  margin-bottom: 16px;
}

.name-input {
  width: 100%;
  padding: 14px 18px;
  border-radius: 14px;
  border: 1.5px solid #f0e6d8;
  background: #fff;
  font-family: 'Nunito', sans-serif;
  font-size: 1rem;
  color: #3d2c24;
  outline: none;
  transition: border-color 150ms ease;
}

.name-input:focus {
  border-color: #e8623a;
  box-shadow: 0 0 0 3px rgba(232, 98, 58, 0.15);
}

.name-input::placeholder {
  color: #c4b8ad;
}

.error-msg {
  color: #e63946;
  font-size: 0.83rem;
  margin-bottom: 12px;
  text-align: center;
}

.reg-btn {
  width: 100%;
  padding: 15px;
  border-radius: 14px;
  background: #e8623a;
  color: #fff;
  font-family: 'Fredoka', sans-serif;
  font-weight: 600;
  font-size: 1.05rem;
  border: none;
  cursor: pointer;
  transition: all 150ms ease;
}

.reg-btn:hover:not(:disabled) {
  background: #d4542b;
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(232, 98, 58, 0.3);
}

.reg-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* ── Success State ── */
.success-state {
  text-align: center;
}

.success-icon {
  margin-bottom: 12px;
  display: flex;
  justify-content: center;
}

.success-title {
  font-family: 'Fredoka', sans-serif;
  font-weight: 700;
  font-size: 1.6rem;
  color: #3d2c24;
  margin-bottom: 8px;
}

.success-sub {
  font-size: 0.88rem;
  color: #8b7b6e;
  margin-bottom: 24px;
}

.token-box {
  background: #fff;
  border: 1.5px solid #f0e6d8;
  border-radius: 14px;
  padding: 14px 18px;
  margin-bottom: 16px;
  text-align: left;
}

.token-label {
  font-size: 0.72rem;
  color: #e63946;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 6px;
}

.token-val {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.85rem;
  color: #3d2c24;
  word-break: break-all;
  font-weight: 500;
}

.cmd-box {
  background: #fff;
  border: 1.5px solid #f0e6d8;
  border-radius: 14px;
  padding: 12px 16px;
  margin-bottom: 12px;
  text-align: left;
}

.cmd-label {
  font-size: 0.72rem;
  color: #8b7b6e;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 6px;
}

.cmd-copy {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
}

.cmd-copy code {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.82rem;
  color: #e8623a;
  font-weight: 600;
}

.copy-icon {
  font-size: 0.85rem;
}

.done-btn {
  width: 100%;
  padding: 13px;
  border-radius: 14px;
  background: #3fb950;
  color: #fff;
  font-family: 'Fredoka', sans-serif;
  font-weight: 600;
  font-size: 1rem;
  border: none;
  cursor: pointer;
  margin-top: 8px;
  transition: all 150ms ease;
}

.done-btn:hover {
  background: #36a146;
}

/* ── Transition ── */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 200ms ease;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
.modal-enter-active .modal-card,
.modal-leave-active .modal-card {
  transition: transform 200ms ease;
}
.modal-enter-from .modal-card {
  transform: translateY(20px) scale(0.97);
}
.modal-leave-to .modal-card {
  transform: translateY(20px) scale(0.97);
}
</style>
