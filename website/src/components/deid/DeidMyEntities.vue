<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useDeidStore } from '../../stores/deid'
import DeidEmptyState from './DeidEmptyState.vue'
import DeidEntityTypeSelect from './DeidEntityTypeSelect.vue'

const store = useDeidStore()
const search = ref('')
const showAdd = ref(false)
const showTypes = ref(false)
const newName = ref('')
const newType = ref('company')
const newPackId = ref<number | null>(null)

const typeCode = ref('')
const typeLabel = ref('')
const typePrefix = ref('')
const editingCode = ref<string | null>(null)

const BUILTIN = new Set(['company', 'person', 'org'])

let searchTimer: ReturnType<typeof setTimeout> | undefined

onMounted(async () => {
  await store.fetchEntityTypes()
  await store.fetchLibrary()
  await store.fetchGlobalExperience()
  if (store.entityTypes.length) {
    newType.value = store.entityTypes[0].code
  }
  const r = await fetch('/api/deid/packs')
  if (r.ok) {
    const packs = (await r.json()) as { id: number; code: string }[]
    const gf = packs.find((p) => p.code === 'general_finance')
    if (gf) newPackId.value = gf.id
    else if (packs[0]) newPackId.value = packs[0].id
  }
})

watch(
  () => store.entityTypes,
  (types) => {
    if (types.length && !types.some((t) => t.code === newType.value)) {
      newType.value = types[0].code
    }
  },
)

watch(search, (q) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    store.fetchLibrary(q.trim() || undefined)
  }, 300)
})

function goUpload() {
  store.closeEntitiesPanel()
  store.newTask()
}

async function addEntity() {
  if (!newName.value.trim() || !newPackId.value) return
  await fetch('/api/deid/entities', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      pack_id: newPackId.value,
      canonical_name: newName.value.trim(),
      entity_type: newType.value,
      aliases: [newName.value.trim()],
    }),
  })
  newName.value = ''
  showAdd.value = false
  await store.fetchLibrary(search.value.trim() || undefined)
}

async function deactivate(id: number) {
  await fetch(`/api/deid/entities/${id}`, { method: 'DELETE' })
  await store.fetchLibrary(search.value.trim() || undefined)
}

function resetTypeForm() {
  typeCode.value = ''
  typeLabel.value = ''
  typePrefix.value = ''
  editingCode.value = null
}

function startEditType(t: { code: string; label: string; placeholder_prefix: string }) {
  editingCode.value = t.code
  typeCode.value = t.code
  typeLabel.value = t.label
  typePrefix.value = t.placeholder_prefix
  showTypes.value = true
}

async function saveType() {
  if (!typeLabel.value.trim() || !typePrefix.value.trim()) return
  try {
    if (editingCode.value) {
      await store.updateEntityType(editingCode.value, {
        label: typeLabel.value.trim(),
        placeholder_prefix: typePrefix.value.trim(),
      })
    } else {
      if (!typeCode.value.trim()) return
      await store.createEntityType({
        code: typeCode.value.trim().toLowerCase(),
        label: typeLabel.value.trim(),
        placeholder_prefix: typePrefix.value.trim(),
      })
    }
    resetTypeForm()
  } catch (e) {
    alert(e instanceof Error ? e.message : '保存失败')
  }
}

async function removeType(code: string) {
  if (BUILTIN.has(code)) return
  if (!confirm(`删除分类「${store.entityTypeLabel(code)}」？`)) return
  try {
    await store.deleteEntityType(code)
    if (editingCode.value === code) resetTypeForm()
  } catch (e) {
    alert(e instanceof Error ? e.message : '删除失败')
  }
}

const typeFormTitle = computed(() => (editingCode.value ? '修改分类' : '新增分类'))

const newExpText = ref('')
const editingExpId = ref<number | null>(null)
const editingExpText = ref('')

async function addGlobalExp() {
  const t = newExpText.value.trim()
  if (!t) return
  await store.createGlobalExperience(t)
  newExpText.value = ''
}

function startEditExp(row: Record<string, unknown>) {
  editingExpId.value = row.id as number
  editingExpText.value = String(row.text || '')
}

async function saveEditExp() {
  if (editingExpId.value == null) return
  await store.updateGlobalExperience(editingExpId.value, editingExpText.value)
  editingExpId.value = null
  editingExpText.value = ''
}

async function removeGlobalExp(id: number) {
  if (!confirm('删除这条全局经验？')) return
  await store.deleteGlobalExperience(id)
}
</script>

<template>
  <main class="lexicon-panel">
    <div class="deid-workbench-column">
      <header class="page-head">
        <h2 class="deid-page-title">词库</h2>
        <p class="deid-page-sub">词库实体在扫描时自动匹配；全局经验注入后续任务的初次识别</p>
      </header>

      <section class="exp-panel deid-panel">
        <h3 class="section-title">全局识别经验</h3>
        <p class="exp-hint">最多 20 条；注入后续任务的初次识别（最近 10 条）。</p>
        <div class="exp-add">
          <input
            v-model="newExpText"
            class="deid-input"
            maxlength="100"
            placeholder="新增经验（≤100 字）"
          />
          <button type="button" class="deid-btn deid-btn--primary" @click="addGlobalExp">添加</button>
        </div>
        <ul v-if="store.globalExperience.length" class="exp-list">
          <li v-for="row in store.globalExperience" :key="(row as { id: number }).id" class="exp-row">
            <template v-if="editingExpId === (row as { id: number }).id">
              <input v-model="editingExpText" class="deid-input" maxlength="100" />
              <button type="button" class="deid-btn" @click="saveEditExp">保存</button>
              <button type="button" class="deid-btn deid-btn--ghost" @click="editingExpId = null">取消</button>
            </template>
            <template v-else>
              <span class="exp-text">{{ (row as { text: string }).text }}</span>
              <button type="button" class="deid-btn deid-btn--ghost" @click="startEditExp(row)">编辑</button>
              <button
                type="button"
                class="deid-btn deid-btn--ghost deid-btn--danger"
                @click="removeGlobalExp((row as { id: number }).id)"
              >
                删除
              </button>
            </template>
          </li>
        </ul>
        <p v-else class="empty-hint">暂无全局经验</p>
      </section>

      <section class="entity-list-panel deid-panel">
        <div class="list-head">
          <h3 class="section-title">词库实体</h3>
          <div class="toolbar">
            <input
              v-model="search"
              class="deid-input search"
              placeholder="搜索实体名称…"
            />
            <button type="button" class="deid-btn" @click="showTypes = !showTypes">
              {{ showTypes ? '收起分类' : '管理分类' }}
            </button>
            <button type="button" class="deid-btn deid-btn--primary" @click="showAdd = !showAdd">
              + 添加
            </button>
          </div>
        </div>

        <div v-if="showTypes" class="types-panel">
          <div class="types-head">
            <h4 class="types-subtitle">{{ typeFormTitle }}</h4>
            <button v-if="editingCode" type="button" class="deid-btn deid-btn--ghost" @click="resetTypeForm">
              取消编辑
            </button>
          </div>
          <div class="type-form">
            <input
              v-if="!editingCode"
              v-model="typeCode"
              class="deid-input"
              placeholder="代码（如 project）"
            />
            <input v-model="typeLabel" class="deid-input" placeholder="显示名称（如 项目）" />
            <input v-model="typePrefix" class="deid-input" placeholder="占位前缀（如 项目）" />
            <button type="button" class="deid-btn deid-btn--primary" @click="saveType">保存</button>
          </div>
          <table class="types-table">
            <thead>
              <tr>
                <th>代码</th>
                <th>显示名</th>
                <th>占位前缀</th>
                <th />
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in store.entityTypes" :key="t.code">
                <td><code>{{ t.code }}</code></td>
                <td>{{ t.label }}</td>
                <td>{{ t.placeholder_prefix }}</td>
                <td class="type-actions">
                  <button type="button" class="deid-btn deid-btn--ghost" @click="startEditType(t)">
                    修改
                  </button>
                  <button
                    v-if="!BUILTIN.has(t.code)"
                    type="button"
                    class="deid-btn deid-btn--ghost deid-btn--danger"
                    @click="removeType(t.code)"
                  >
                    删除
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="showAdd" class="add-form">
          <input v-model="newName" class="deid-input" placeholder="实体名称" />
          <DeidEntityTypeSelect v-model="newType" />
          <button type="button" class="deid-btn deid-btn--primary" @click="addEntity">保存</button>
        </div>

        <DeidEmptyState
          v-if="!store.libraryEntities.length"
          title="词库还是空的"
          hint="扫描时勾选「记住」，或在此手动添加"
          cta-label="去上传文档"
          @action="goUpload"
        />

        <div v-else class="entity-wrap">
          <table class="table entity-desktop">
            <thead>
              <tr>
                <th>名称</th>
                <th>分类</th>
                <th>别名</th>
                <th />
              </tr>
            </thead>
            <tbody>
              <tr v-for="e in store.libraryEntities" :key="(e as { id: number }).id">
                <td class="name-cell" :title="(e as { canonical_name: string }).canonical_name">
                  <span class="name-text">{{ (e as { canonical_name: string }).canonical_name }}</span>
                </td>
                <td>{{ store.entityTypeLabel((e as { entity_type: string }).entity_type) }}</td>
                <td class="aliases">{{ ((e as { aliases: string[] }).aliases || []).join('、') }}</td>
                <td>
                  <button
                    type="button"
                    class="deid-btn deid-btn--ghost deid-btn--danger"
                    @click="deactivate((e as { id: number }).id)"
                  >
                    删除
                  </button>
                </td>
              </tr>
            </tbody>
          </table>

          <ul class="entity-cards entity-mobile">
            <li v-for="e in store.libraryEntities" :key="(e as { id: number }).id" class="entity-card">
              <div class="entity-card__name">{{ (e as { canonical_name: string }).canonical_name }}</div>
              <div class="entity-card__meta">
                <span class="type-tag">{{ store.entityTypeLabel((e as { entity_type: string }).entity_type) }}</span>
                <span v-if="(e as { aliases: string[] }).aliases?.length" class="aliases">
                  {{ ((e as { aliases: string[] }).aliases || []).join('、') }}
                </span>
              </div>
              <button
                type="button"
                class="deid-btn deid-btn--ghost deid-btn--danger del-btn--touch"
                @click="deactivate((e as { id: number }).id)"
              >
                删除
              </button>
            </li>
          </ul>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped>
.lexicon-panel {
  width: 100%;
  padding: 1rem 2rem 2rem;
  background: var(--deid-bg);
  box-sizing: border-box;
}
.page-head {
  margin-bottom: 0.25rem;
}
.section-title {
  margin: 0 0 0.75rem;
  font-size: 1.0625rem;
  font-weight: 600;
}
.types-subtitle {
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 600;
}
.exp-panel {
  padding: 1rem 1.25rem;
}
.exp-hint {
  margin: 0 0 0.75rem;
  font-size: 0.875rem;
  color: var(--deid-ink-secondary);
}
.exp-add {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
.exp-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.exp-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--deid-border);
}
.exp-row:last-child {
  border-bottom: none;
}
.exp-text {
  flex: 1;
  min-width: 0;
  font-size: 0.9375rem;
}
.empty-hint {
  margin: 0;
  font-size: 0.875rem;
  color: var(--deid-ink-muted);
}
.entity-list-panel {
  padding: 1rem 1.25rem;
}
.list-head {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1rem;
}
.toolbar {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.search {
  flex: 1;
  min-width: 160px;
}
.types-panel {
  margin-bottom: 1rem;
  padding: 0.85rem 1rem;
  border: 1px solid var(--deid-border);
  border-radius: var(--deid-radius-sm);
  background: var(--deid-surface-2);
}
.types-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}
.type-form {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}
.types-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9375rem;
}
.types-table th,
.types-table td {
  text-align: left;
  padding: 0.55rem 0.65rem;
  border-bottom: 1px solid var(--deid-border);
}
.types-table th {
  color: var(--deid-ink-secondary);
  font-weight: 500;
  font-size: 0.8125rem;
}
.type-actions {
  display: flex;
  gap: 0.25rem;
  white-space: nowrap;
}
.add-form {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 1rem;
  table-layout: fixed;
}
.table th {
  text-align: left;
  padding: 0.85rem 1rem;
  border-bottom: 1px solid var(--deid-border);
  background: var(--deid-surface-2);
  color: var(--deid-ink-secondary);
  font-size: 0.875rem;
  font-weight: 500;
}
.table td {
  padding: 0.85rem 1rem;
  border-bottom: 1px solid var(--deid-border);
}
.table tbody tr:hover {
  background: var(--deid-primary-soft);
}
.name-cell {
  max-width: 0;
  overflow: hidden;
}
.name-text {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
.aliases {
  color: var(--deid-ink-muted);
  font-size: 0.9375rem;
}
.entity-wrap {
  overflow: visible;
}
.entity-mobile {
  display: none;
  list-style: none;
  margin: 0;
  padding: 0;
  gap: 0.65rem;
}
.entity-card {
  padding: 0.85rem 0;
  border-bottom: 1px solid var(--deid-border);
}
.entity-card:last-child {
  border-bottom: none;
}
.entity-card__name {
  font-weight: 500;
  font-size: 1rem;
  word-break: break-word;
  margin-bottom: 0.4rem;
}
.entity-card__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
  font-size: 0.875rem;
}
.type-tag {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  background: var(--deid-preset-bg);
  color: var(--deid-preset);
  font-weight: 500;
  font-size: 0.8125rem;
}
.del-btn--touch {
  min-height: 44px;
  padding: 0.35rem 0.75rem;
}
@media (max-width: 768px) {
  .lexicon-panel {
    padding: 1.25rem 1rem 2rem;
  }
  .entity-desktop {
    display: none;
  }
  .entity-mobile {
    display: flex;
    flex-direction: column;
  }
  .search {
    flex: 1 1 100%;
  }
}
</style>
