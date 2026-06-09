<script setup lang="ts">
import { computed } from 'vue'
import { DEFAULT_ENTITY_TYPES, useDeidStore } from '../../stores/deid'

const props = defineProps<{
  modelValue: string
  disabled?: boolean
  width?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const store = useDeidStore()

const options = computed(() =>
  store.entityTypes.length ? store.entityTypes : [...DEFAULT_ENTITY_TYPES],
)

function onChange(e: Event) {
  emit('update:modelValue', (e.target as HTMLSelectElement).value)
}
</script>

<template>
  <select
    class="deid-select"
    :style="width ? { width } : undefined"
    :disabled="disabled"
    :value="modelValue"
    @change="onChange"
  >
    <option v-for="t in options" :key="t.code" :value="t.code">
      {{ t.label }}
    </option>
  </select>
</template>
