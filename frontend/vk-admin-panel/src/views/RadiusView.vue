<template>
  <AppLayout>
    <LoadingSpinner v-if="loading" message="Загрузка радиуса..." />
    <ErrorAlert v-else-if="error" :message="error" closable @close="error = null" />

    <template v-else>
      <Card>
        <template #content>
          <div class="radius-control">
            <label>Радиус уведомлений: <strong>{{ radius }} км</strong></label>
            <Slider
              v-model="radius"
              :min="1"
              :max="500"
              :step="1"
              class="radius-slider"
            />
            <div class="radius-input-row">
              <InputNumber
                v-model="radius"
                :min="1"
                :max="500"
                suffix=" км"
                class="radius-input"
              />
            </div>
            <div class="radius-actions">
              <Button label="Сохранить" icon="pi pi-check" @click="save" :loading="saving" />
              <Button
                v-if="hasRadius"
                label="Удалить"
                icon="pi pi-trash"
                severity="danger"
                @click="remove"
                :loading="deleting"
              />
            </div>
          </div>
        </template>
      </Card>
    </template>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getRadius, saveRadius, deleteRadius } from '@/api/radius'

const loading = ref(true)
const error = ref<string | null>(null)
const saving = ref(false)
const deleting = ref(false)
const hasRadius = ref(false)
const radius = ref(50)

async function save() {
  saving.value = true
  error.value = null
  const res = await saveRadius(radius.value)
  if (res.ok) {
    hasRadius.value = true
  } else {
    error.value = res.error || 'Ошибка сохранения'
  }
  saving.value = false
}

async function remove() {
  deleting.value = true
  error.value = null
  const res = await deleteRadius()
  if (res.ok) {
    hasRadius.value = false
    radius.value = 50
  } else {
    error.value = res.error || 'Ошибка удаления'
  }
  deleting.value = false
}

onMounted(async () => {
  const res = await getRadius()
  if (res.ok && res.data !== null) {
    radius.value = res.data
    hasRadius.value = true
  }
  loading.value = false
})
</script>

<style scoped>
.radius-control {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-width: 400px;
}
.radius-slider {
  width: 100%;
}
.radius-input-row {
  display: flex;
  justify-content: center;
}
.radius-input {
  width: 120px;
}
.radius-actions {
  display: flex;
  gap: 0.5rem;
}
</style>
