<script setup lang="ts">
import { computed, ref } from 'vue'
import MarkdownIt from 'markdown-it'
import type { SourceMarkdownPayload } from '../../utils/deidFormats'

const props = defineProps<{
  payload: SourceMarkdownPayload
  loading?: boolean
  workerOnline?: boolean
}>()

const emit = defineEmits<{ proceed: [] }>()

const viewMode = ref<'rendered' | 'source'>('rendered')

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
})

const renderedHtml = computed(() => md.render(props.payload.content || ''))

const stats = computed(() => props.payload.stats)
</script>

<template>
  <div class="markdown-stage">
    <div class="markdown-head">
      <h2 class="deid-page-title">{{ payload.original_filename }}</h2>
      <p class="deid-page-sub">文档已转换为 Markdown，请确认内容后继续实体扫描</p>
    </div>

    <div class="convert-banner deid-panel">
      <div class="convert-flow">
        <span class="format-badge format-badge--source">{{ payload.source_format_label }}</span>
        <span class="convert-arrow" aria-hidden="true">→</span>
        <span class="format-badge format-badge--md">Markdown</span>
      </div>
      <div class="convert-stats">
        <span>{{ stats.char_count.toLocaleString() }} 字符</span>
        <span>{{ stats.line_count.toLocaleString() }} 行</span>
        <span>{{ stats.paragraph_count.toLocaleString() }} 段</span>
        <span v-if="stats.table_count">{{ stats.table_count }} 表格</span>
      </div>
    </div>

    <div class="preview-toolbar">
      <div class="view-toggle" role="tablist" aria-label="Markdown 预览模式">
        <button
          type="button"
          role="tab"
          :aria-selected="viewMode === 'rendered'"
          class="toggle-btn"
          :class="{ active: viewMode === 'rendered' }"
          @click="viewMode = 'rendered'"
        >
          渲染预览
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="viewMode === 'source'"
          class="toggle-btn"
          :class="{ active: viewMode === 'source' }"
          @click="viewMode = 'source'"
        >
          源码
        </button>
      </div>
      <p v-if="payload.truncated" class="truncate-hint">预览已截断，完整内容将在扫描时使用</p>
    </div>

    <div class="preview-panel deid-panel">
      <article
        v-if="viewMode === 'rendered'"
        class="md-render"
        v-html="renderedHtml"
      />
      <pre v-else class="md-source deid-mono">{{ payload.content }}</pre>
    </div>

    <div class="cta">
      <button
        type="button"
        class="deid-btn deid-btn--primary deid-btn--lg"
        :disabled="loading"
        @click="emit('proceed')"
      >
        {{ workerOnline ? '确认并开始实体扫描' : '确认并匹配词库实体' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.markdown-stage {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.markdown-head {
  margin-bottom: 0.25rem;
}
.convert-banner {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem 1.25rem;
  padding: 0.875rem 1rem;
}
.convert-flow {
  display: flex;
  align-items: center;
  gap: 0.65rem;
}
.format-badge {
  display: inline-flex;
  align-items: center;
  padding: 0.25rem 0.65rem;
  border-radius: 999px;
  font-size: 0.8125rem;
  font-weight: 600;
}
.format-badge--source {
  background: var(--deid-surface-2);
  color: var(--deid-ink-secondary);
  border: 1px solid var(--deid-border);
}
.format-badge--md {
  background: var(--deid-primary-soft, rgba(59, 130, 246, 0.12));
  color: var(--deid-primary);
  border: 1px solid var(--deid-primary-border, rgba(59, 130, 246, 0.25));
}
.convert-arrow {
  color: var(--deid-ink-muted);
  font-size: 1.125rem;
}
.convert-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1rem;
  font-size: 0.8125rem;
  color: var(--deid-ink-muted);
}
.preview-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.view-toggle {
  display: inline-flex;
  padding: 3px;
  border-radius: 8px;
  background: var(--deid-surface-2);
  border: 1px solid var(--deid-border);
}
.toggle-btn {
  border: none;
  background: transparent;
  padding: 0.35rem 0.75rem;
  border-radius: 6px;
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--deid-ink-muted);
  cursor: pointer;
}
.toggle-btn.active {
  background: var(--deid-surface);
  color: var(--deid-ink);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
}
.truncate-hint {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--deid-ink-muted);
}
.preview-panel {
  max-height: min(52vh, 520px);
  overflow: auto;
  padding: 1rem 1.15rem;
}
.md-render {
  font-size: 0.9375rem;
  line-height: 1.65;
  color: var(--deid-ink);
  word-break: break-word;
}
.md-render :deep(h1),
.md-render :deep(h2),
.md-render :deep(h3) {
  margin: 1.25em 0 0.5em;
  line-height: 1.3;
  color: var(--deid-ink);
}
.md-render :deep(h1) { font-size: 1.35rem; }
.md-render :deep(h2) { font-size: 1.15rem; }
.md-render :deep(h3) { font-size: 1rem; }
.md-render :deep(p) {
  margin: 0.65em 0;
}
.md-render :deep(ul),
.md-render :deep(ol) {
  margin: 0.5em 0;
  padding-left: 1.35em;
}
.md-render :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0.75em 0;
  font-size: 0.875rem;
}
.md-render :deep(th),
.md-render :deep(td) {
  border: 1px solid var(--deid-border);
  padding: 0.35rem 0.5rem;
  text-align: left;
}
.md-render :deep(th) {
  background: var(--deid-surface-2);
}
.md-render :deep(code) {
  font-family: ui-monospace, monospace;
  font-size: 0.85em;
  background: var(--deid-surface-2);
  padding: 0.1em 0.35em;
  border-radius: 4px;
}
.md-render :deep(pre) {
  overflow: auto;
  padding: 0.75rem;
  background: var(--deid-surface-2);
  border-radius: 8px;
  font-size: 0.8125rem;
}
.md-source {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.8125rem;
  line-height: 1.55;
  color: var(--deid-ink-secondary);
}
.cta {
  display: flex;
  justify-content: flex-end;
  padding-top: 0.25rem;
}
</style>
