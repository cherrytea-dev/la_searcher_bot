<template>
  <AppLayout>
    <LoadingSpinner v-if="loading" message="Загрузка радиуса..." />
    <ErrorAlert v-else-if="error" :message="error" closable @close="error = null" />

    <template v-else>
      <Card>
        <template #content>
          <div class="radius-control">
            <div v-if="!hasRadius" class="radius-empty">
              <p class="radius-empty-text">Радиус уведомлений не установлен.</p>
              <p class="radius-empty-hint">Укажите расстояние от дома, в пределах которого вы готовы выезжать на поиски.</p>
            </div>
            <div v-else class="radius-current">
              <label>Радиус уведомлений: <strong>{{ radius }} км</strong></label>
            </div>
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
              <Button
                :label="hasRadius ? 'Сохранить' : 'Установить'"
                icon="pi pi-check"
                @click="save"
                :loading="saving"
              />
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
  if (res.ok && res.data && res.data.radius !== null) {
    radius.value = res.data.radius
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
.radius-empty-text {
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0 0 0.25rem;
  color: var(--app-text-color);
}
.radius-empty-hint {
  margin: 0;
  color: var(--p-text-muted-color, #6c757d);
  font-size: 0.9rem;
}
.radius-current label {
  font-size: 1.1rem;
  color: var(--app-text-color);
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
