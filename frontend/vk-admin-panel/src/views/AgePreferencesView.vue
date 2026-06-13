<template>
  <AppLayout>
    <LoadingSpinner v-if="loading" message="Загрузка возрастных предпочтений..." />
    <ErrorAlert v-else-if="error" :message="error" closable @close="error = null" />

    <template v-else>
      <Card>
        <template #content>
          <h3>Текущие периоды</h3>
          <div v-if="periods.length === 0" class="empty-state">
            <p>Нет возрастных предпочтений</p>
          </div>
          <div v-else class="periods-list">
            <Chip
              v-for="(p, i) in periods"
              :key="i"
              :label="`${p.min_age}–${p.max_age} лет`"
              removable
              @remove="removePeriod(i)"
            />
          </div>

          <Divider />

          <h3>Добавить период</h3>
          <div class="add-period-form">
            <div class="field">
              <label>От</label>
              <InputNumber v-model="newMin" :min="0" :max="120" />
            </div>
            <div class="field">
              <label>До</label>
              <InputNumber v-model="newMax" :min="0" :max="120" />
            </div>
            <Button label="Добавить" icon="pi pi-plus" @click="addPeriod" :disabled="!isValid" />
          </div>
        </template>
      </Card>
    </template>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getAgePreferences, saveAgePeriod, deleteAgePeriod } from '@/api/agePreferences'
import type { AgePeriod } from '@/api/agePreferences'

const loading = ref(true)
const error = ref<string | null>(null)
const periods = ref<AgePeriod[]>([])
const newMin = ref(18)
const newMax = ref(60)

const isValid = computed(() => newMin.value >= 0 && newMax.value > newMin.value && newMax.value <= 120)

async function addPeriod() {
  if (!isValid.value) return
  error.value = null
  const period: AgePeriod = { min_age: newMin.value, max_age: newMax.value }
  const res = await saveAgePeriod(period)
  if (res.ok) {
    periods.value.push(period)
  } else {
    error.value = res.error || 'Ошибка добавления'
  }
}

async function removePeriod(index: number) {
  error.value = null
  const period = periods.value[index]
  const res = await deleteAgePeriod(period)
  if (res.ok) {
    periods.value.splice(index, 1)
  } else {
    error.value = res.error || 'Ошибка удаления'
  }
}

onMounted(async () => {
  error.value = null
  const res = await getAgePreferences()
  if (res.ok) {
    periods.value = res.data || []
  } else {
    error.value = res.error || 'Ошибка загрузки'
  }
  loading.value = false
})
</script>

<style scoped>
.empty-state {
  text-align: center;
  color: #888;
  padding: 1rem 0;
}

.periods-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.add-period-form {
  display: flex;
  gap: 1rem;
  align-items: flex-end;
  flex-wrap: wrap;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.field label {
  font-size: 0.875rem;
  color: #666;
}
</style>