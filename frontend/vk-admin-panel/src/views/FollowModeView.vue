<template>
  <AppLayout>
    <LoadingSpinner v-if="loading" message="Загрузка режима отслеживания..." />
    <ErrorAlert v-else-if="error" :message="error" closable @close="error = null" />

    <template v-else>
      <Card>
        <template #content>
          <h3>Режим отслеживания поисков</h3>
          <p class="text-secondary">
            Включите, чтобы получать уведомления об изменениях в поисках, которые вы отслеживаете
          </p>

          <div class="follow-mode-toggle">
            <span>Отслеживание поисков</span>
            <ToggleSwitch
              :modelValue="enabled"
              @update:modelValue="toggle"
            />
          </div>
        </template>
      </Card>
    </template>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getFollowMode, setFollowMode } from '@/api/followMode'

const loading = ref(true)
const error = ref<string | null>(null)
const enabled = ref(false)

async function toggle(val: boolean) {
  error.value = null
  const res = await setFollowMode(val)
  if (res.ok) {
    enabled.value = val
  } else {
    error.value = res.error || 'Ошибка сохранения'
  }
}

onMounted(async () => {
  error.value = null
  const res = await getFollowMode()
  if (res.ok) {
    enabled.value = res.data ?? false
  } else {
    error.value = res.error || 'Ошибка загрузки'
  }
  loading.value = false
})
</script>

<style scoped>
h3 {
  color: var(--app-text-color);
}

.text-secondary {
  color: #888;
  margin-bottom: 1rem;
}

.follow-mode-toggle {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 0;
  color: var(--app-text-color);
}
</style>
