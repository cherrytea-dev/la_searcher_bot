<template>
  <AppLayout>
    <LoadingSpinner v-if="loading" message="Загрузка уведомлений..." />
    <ErrorAlert v-else-if="error" :message="error" closable @close="error = null" />

    <template v-else>
      <div class="preferences-list">
        <div v-for="pref in allPreferences" :key="pref.key" class="pref-item">
          <div class="pref-info">
            <span class="pref-name">{{ pref.label }}</span>
          </div>
          <ToggleSwitch
            :modelValue="enabledPreferences.includes(pref.key)"
            @update:modelValue="(val: boolean) => togglePreference(pref.key, val)"
          />
        </div>
      </div>
    </template>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getPreferences, setPreference } from '@/api/preferences'

const loading = ref(true)
const error = ref<string | null>(null)
const enabledPreferences = ref<string[]>([])

const allPreferences = [
  { key: 'new_searches', label: 'Новые поиски' },
  { key: 'status_changes', label: 'Изменение статуса' },
  { key: 'title_changes', label: 'Изменение заголовка' },
  { key: 'comments_changes', label: 'Все комментарии' },
  { key: 'inforg_comments', label: 'Комментарии Инфорга' },
  { key: 'first_post_changes', label: 'Изменение первого поста' },
  { key: 'field_trips_new', label: 'Новый выезд' },
  { key: 'field_trips_change', label: 'Изменение выезда' },
  { key: 'coords_change', label: 'Изменение координат' },
  { key: 'all_in_followed_search', label: 'Всё в избранных поисках' },
]

async function togglePreference(key: string, enabled: boolean) {
  error.value = null
  const res = await setPreference(key, enabled)
  if (res.ok) {
    if (enabled) {
      enabledPreferences.value.push(key)
    } else {
      enabledPreferences.value = enabledPreferences.value.filter((p) => p !== key)
    }
  } else {
    error.value = res.error || 'Ошибка при изменении настройки'
  }
}

onMounted(async () => {
  loading.value = true
  const res = await getPreferences()
  if (res.ok && res.data) {
    enabledPreferences.value = res.data
  } else {
    error.value = res.error || 'Ошибка загрузки'
  }
  loading.value = false
})
</script>

<style scoped>
.preferences-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-width: 500px;
}
.pref-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  background: white;
  border-radius: 6px;
  border: 1px solid var(--p-surface-200);
}
.pref-name {
  font-weight: 500;
  color: var(--app-text-color);
}
</style>
