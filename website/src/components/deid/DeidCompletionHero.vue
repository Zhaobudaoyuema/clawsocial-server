<script setup lang="ts">

import { computed } from 'vue'

import DeidVerificationCard from './DeidVerificationCard.vue'



const props = defineProps<{

  job: Record<string, unknown>

  entities: Record<string, unknown>[]

}>()



const verification = computed(

  () => (props.job.verification as Record<string, unknown>) || {},

)

const runSummary = computed(

  () => (props.job.run_summary as Record<string, unknown>) || {},

)



const entityCount = computed(

  () => props.entities.filter((e) => !(e as { is_excluded?: boolean }).is_excluded).length,

)

const companyCount = computed(

  () =>

    props.entities.filter(

      (e) =>

        !(e as { is_excluded?: boolean }).is_excluded &&

        (e as { entity_type: string }).entity_type === 'company',

    ).length,

)

const replacementCount = computed(

  () => (runSummary.value.replacement_count as number) || 0,

)

const engine = computed(() => (props.job.engine as string) || 'standard')

</script>



<template>

  <section class="hero">

    <DeidVerificationCard

      :passed="!!verification.passed"

      :summary="(verification.summary as string) || undefined"

      :residuals="(verification.residuals as string[]) || []"

    />



    <div class="stats">

      <div class="stat-card">

        <span class="stat-num">{{ entityCount }}</span>

        <span class="stat-label">脱敏主体</span>

      </div>

      <div class="stat-card">

        <span class="stat-num">{{ replacementCount }}</span>

        <span class="stat-label">替换次数</span>

      </div>

      <div class="stat-card">

        <span class="stat-num">{{ companyCount }}</span>

        <span class="stat-label">公司实体</span>

      </div>

      <div class="stat-card">

        <span class="stat-num deid-mono">{{ engine }}</span>

        <span class="stat-label">处理引擎</span>

      </div>

    </div>

  </section>

</template>



<style scoped>

.hero {

  margin-bottom: 1.5rem;

}

.stats {

  display: grid;

  grid-template-columns: repeat(4, 1fr);

  gap: 0.65rem;

}

.stat-card {

  background: var(--deid-surface);

  border: 1px solid var(--deid-border);

  border-radius: var(--deid-radius);

  padding: 0.85rem 1rem;

  border-left: 3px solid var(--deid-primary);

  box-shadow: var(--deid-shadow-sm);

}

.stat-num {

  display: block;

  font-size: 1.75rem;

  font-weight: 600;

  letter-spacing: -0.02em;

  color: var(--deid-ink);

  line-height: 1.2;

}

.stat-label {

  display: block;

  margin-top: 0.2rem;

  font-size: 0.875rem;

  color: var(--deid-ink-muted);

}

@media (max-width: 640px) {

  .stats {

    grid-template-columns: repeat(2, 1fr);

  }

}

</style>


