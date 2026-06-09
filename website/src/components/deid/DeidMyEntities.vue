<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useDeidStore } from '../../stores/deid'
import DeidEmptyState from './DeidEmptyState.vue'
import DeidStepper from './DeidStepper.vue'
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
</script>

<template>
  <main class="my-entities">
    <DeidStepper current="upload" />

    <header class="head">
      <h2 class="deid-page-title">我的实体</h2>
      <p class="deid-page-sub">记住的实体会在扫描时自动匹配</p>
    </header>

    <div class="toolbar">
      <input
        v-model="search"
        class="deid-input search"
        placeholder="搜索实体名称"
      />
      <button type="button" class="deid-btn" @click="showTypes = !showTypes">
        {{ showTypes ? '收起分类' : '管理分类' }}
      </button>
      <button type="button" class="deid-btn deid-btn--primary" @click="showAdd = !showAdd">
        + 添加
      </button>
    </div>

    <div v-if="showTypes" class="types-panel deid-panel">
      <div class="types-head">
        <h3 class="types-title">{{ typeFormTitle }}</h3>
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

    <div v-if="showAdd" class="add-form deid-panel">
      <input v-model="newName" class="deid-input" placeholder="实体名称" />
      <DeidEntityTypeSelect v-model="newType" />
      <button type="button" class="deid-btn deid-btn--primary" @click="addEntity">保存</button>
    </div>

    <DeidEmptyState
      v-if="!store.libraryEntities.length"
      class="deid-panel"
      title="还没有记住的实体"
      hint="扫描时勾选「记住」，或在此手动添加"
      cta-label="去上传文档"
      @action="goUpload"
    />

    <table v-else class="table deid-panel">
      <thead>
        <tr>
          <th>名称</th>
          <th>类型</th>
          <th>别名</th>
          <th />
        </tr>
      </thead>
      <tbody>
        <tr v-for="e in store.libraryEntities" :key="(e as { id: number }).id">
          <td>{{ (e as { canonical_name: string }).canonical_name }}</td>
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
  </main>
</template>

<style scoped>
.my-entities {
  flex: 1;
  width: 100%;
  max-width: var(--deid-content-max);
}
.toolbar {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}
.search {
  flex: 1;
  min-width: 200px;
}
.types-panel {
  margin-bottom: 1rem;
  padding: 1rem 1.25rem !important;
}
.types-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}
.types-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
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
}
.table th {
  text-align: left;
  padding: 0.85rem 1rem;
  border-bottom: 1px solid var(--deid-border);
  background: var(--deid-surface-2);
  color: var(--deid-ink-secondary);
  font-size: 0.875rem;
}
.table td {
  padding: 0.85rem 1rem;
  border-bottom: 1px solid var(--deid-border);
}
.aliases {
  color: var(--deid-ink-muted);
  font-size: 0.9375rem;
}
</style>
