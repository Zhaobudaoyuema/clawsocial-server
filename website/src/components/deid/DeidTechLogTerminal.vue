<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps<{
  logs: string[]
  streamTail?: string
  /** compact=内嵌预览；full=弹框全屏 */
  mode?: 'compact' | 'full'
  live?: boolean
  logTitle?: string
  streamPrompt?: string
}>()

const emit = defineEmits<{ click: [] }>()

const bodyRef = ref<HTMLElement | null>(null)

const prompt = computed(() =>
  props.streamPrompt
    ? props.streamPrompt
    : props.live
      ? 'root@deid-worker:~$ scan --stream'
      : 'root@deid-worker:~$ scan --log',
)

const title = computed(() => props.logTitle || 'deid-scan.log')

watch(
  () => [props.logs.length, props.streamTail, props.mode],
  async () => {
    await nextTick()
    const el = bodyRef.value
    if (el) el.scrollTop = el.scrollHeight
  },
)

function lineClass(line: string) {
  if (line.startsWith('发现实体') || line.startsWith('发现语义风险')) return 'term-line--entity'
  if (line.startsWith('错误')) return 'term-line--err'
  if (line.startsWith('——') || line.includes('段')) return 'term-line--chunk'
  if (line.includes('再识别') || line.includes('词库') || line.includes('语义')) return 'term-line--sys'
  if (line.includes('deep_detect') || line.includes('解析')) return 'term-line--sys'
  return 'term-line--default'
}

function onClick() {
  if (props.mode === 'compact') emit('click')
}
</script>

<template>
  <div
    class="term"
    :class="{
      'term--compact': mode === 'compact',
      'term--full': mode === 'full',
      'term--clickable': mode === 'compact',
      'term--live': live,
    }"
    :role="mode === 'compact' ? 'button' : undefined"
    :tabindex="mode === 'compact' ? 0 : undefined"
    :aria-label="mode === 'compact' ? '打开技术日志终端' : undefined"
    @click="onClick"
    @keydown.enter="onClick"
    @keydown.space.prevent="onClick"
  >
    <div class="term__chrome">
      <span class="term__dots" aria-hidden="true">
        <i /><i /><i />
      </span>
      <span class="term__title">{{ title }}</span>
      <span v-if="live" class="term__badge">LIVE</span>
      <span v-if="mode === 'compact'" class="term__expand">⤢ 展开 · Worker 调用</span>
    </div>
    <div ref="bodyRef" class="term__body">
      <div class="term__prompt">{{ prompt }}</div>
      <p v-if="logs.length === 0 && !streamTail" class="term-line term-line--dim">
        <span class="term-cursor" aria-hidden="true" />等待 Worker 输出…
      </p>
      <div v-for="(line, i) in logs" :key="i" class="term-line" :class="lineClass(line)">
        <span class="term-prefix">&gt;</span>{{ line }}
      </div>
      <div v-if="streamTail" class="term-line term-line--stream">
        <span class="term-prefix">&gt;</span>{{ streamTail }}<span class="term-cursor" aria-hidden="true" />
      </div>
    </div>
    <div v-if="mode === 'compact'" class="term__fade" aria-hidden="true" />
    <div class="term__scanlines" aria-hidden="true" />
  </div>
</template>

<style scoped>
.term {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  background: #070b10;
  border: 1px solid #1a3d2e;
  box-shadow:
    0 0 0 1px rgba(0, 255, 136, 0.06),
    0 4px 24px rgba(0, 0, 0, 0.45),
    inset 0 1px 0 rgba(0, 255, 136, 0.08);
  font-family: var(--deid-font-mono, 'IBM Plex Mono', 'Cascadia Code', Consolas, monospace);
}
.term--clickable {
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.15s;
}
.term--clickable:hover {
  border-color: #2dd4a0;
  box-shadow:
    0 0 0 1px rgba(0, 255, 136, 0.15),
    0 0 20px rgba(0, 255, 136, 0.12),
    0 6px 28px rgba(0, 0, 0, 0.5);
  transform: translateY(-1px);
}
.term--clickable:focus-visible {
  outline: 2px solid #00ff88;
  outline-offset: 2px;
}
.term--live {
  animation: term-glow 2.4s ease-in-out infinite;
}
@keyframes term-glow {
  0%,
  100% {
    box-shadow:
      0 0 0 1px rgba(0, 255, 136, 0.08),
      0 4px 24px rgba(0, 0, 0, 0.45);
  }
  50% {
    box-shadow:
      0 0 0 1px rgba(0, 255, 136, 0.18),
      0 0 16px rgba(0, 255, 136, 0.1),
      0 4px 24px rgba(0, 0, 0, 0.45);
  }
}
.term__chrome {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.45rem 0.65rem;
  background: linear-gradient(180deg, #0f151c 0%, #0a0f14 100%);
  border-bottom: 1px solid #1a2f24;
}
.term__dots {
  display: flex;
  gap: 0.3rem;
}
.term__dots i {
  display: block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #2a3a32;
}
.term__dots i:nth-child(1) {
  background: #ff5f57;
}
.term__dots i:nth-child(2) {
  background: #febc2e;
}
.term__dots i:nth-child(3) {
  background: #28c840;
}
.term__title {
  flex: 1;
  font-size: 0.6875rem;
  letter-spacing: 0.06em;
  color: #5a8f72;
  text-transform: uppercase;
}
.term__badge {
  font-size: 0.625rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: #00ff88;
  padding: 0.1rem 0.35rem;
  border: 1px solid rgba(0, 255, 136, 0.45);
  border-radius: 3px;
  animation: term-blink 1.4s step-end infinite;
}
@keyframes term-blink {
  50% {
    opacity: 0.35;
  }
}
.term__expand {
  font-size: 0.6875rem;
  color: #6ee7b7;
  opacity: 0.85;
}
.term__body {
  position: relative;
  z-index: 1;
  padding: 0.65rem 0.75rem;
  overflow-y: auto;
  font-size: 0.6875rem;
  line-height: 1.55;
}
.term--compact .term__body {
  max-height: 108px;
}
.term--full .term__body {
  max-height: min(62vh, 520px);
  font-size: 0.75rem;
}
.term__prompt {
  color: #4ade80;
  opacity: 0.55;
  margin-bottom: 0.35rem;
  font-size: 0.625rem;
}
.term--full .term__prompt {
  font-size: 0.6875rem;
}
.term-line {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0 0 0.15rem;
}
.term-prefix {
  color: #166534;
  margin-right: 0.35rem;
  user-select: none;
}
.term-line--default {
  color: #86efac;
}
.term-line--entity {
  color: #00ff88;
  text-shadow: 0 0 8px rgba(0, 255, 136, 0.35);
}
.term-line--err {
  color: #f87171;
  text-shadow: 0 0 6px rgba(248, 113, 113, 0.35);
}
.term-line--chunk {
  color: #67e8f9;
}
.term-line--sys {
  color: #a78bfa;
}
.term-line--stream {
  color: #bbf7d0;
  opacity: 0.92;
}
.term-line--dim {
  color: #4b7c5f;
  font-style: italic;
}
.term-cursor {
  display: inline-block;
  width: 0.45em;
  height: 1em;
  margin-left: 1px;
  vertical-align: text-bottom;
  background: #00ff88;
  animation: term-cursor 1s step-end infinite;
}
@keyframes term-cursor {
  50% {
    opacity: 0;
  }
}
.term__fade {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 2rem;
  background: linear-gradient(transparent, #070b10);
  pointer-events: none;
  z-index: 2;
}
.term__scanlines {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 3;
  background: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 2px,
    rgba(0, 0, 0, 0.12) 2px,
    rgba(0, 0, 0, 0.12) 4px
  );
  opacity: 0.35;
}
</style>
