<template>
  <AppLayout>
    <LoadingSpinner v-if="loading" message="Загрузка типов поисков..." />
    <ErrorAlert v-else-if="error" :message="error" closable @close="error = null" />

    <template v-else>
      <Card>
        <template #content>
          <h3>Типы поисков</h3>
          <p class="text-secondary">Выберите типы поисков, о которых хотите получать уведомления</p>

          <div class="topic-types-list">
            <div
              v-for="tt in topicTypes"
              :key="tt.id"
              class="topic-type-item"
            >
              <span>{{ tt.label }}</span>
              <ToggleSwitch
                :modelValue="tt.enabled"
                @update:modelValue="toggle(tt.id)"
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
import { getTopicTypes, addTopicType, removeTopicType } from '@/api/topicTypes'

interface TopicTypeItem {
  id: number
  label: string
  enabled: boolean
}

const TOPIC_TYPE_LABELS: Record<number, string> = {
  0: 'Стандартные активные поиски',
  1: 'Обратные поиски',
  2: 'Ночной патруль',
  3: 'Учебные поиски',
  4: 'Информационная поддержка',
  5: 'Резонансные поиски',
  6: 'Мероприятия',
}

const loading = ref(true)
const error = ref<string | null>(null)
const topicTypes = ref<TopicTypeItem[]>([])

async function toggle(id: number) {
  error.value = null
  const item = topicTypes.value.find((t) => t.id === id)
  if (!item) return

  if (item.enabled) {
    // Disable: remove topic type
    const res = await removeTopicType(id)
    if (!res.ok) {
      error.value = res.error || 'Ошибка отключения'
      item.enabled = true // revert
    }
  } else {
    // Enable: add topic type
    const res = await addTopicType(id)
    if (res.ok) {
      item.enabled = true
    } else {
      error.value = res.error || 'Ошибка включения'
    }
  }
}

onMounted(async () => {
  error.value = null
  const res = await getTopicTypes()
  if (res.ok) {
    const enabledIds: number[] = res.data || []
    topicTypes.value = Object.entries(TOPIC_TYPE_LABELS).map(([id, label]) => ({
      id: Number(id),
      label,
      enabled: enabledIds.includes(Number(id)),
    }))
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

.topic-types-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.topic-type-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 0;
  border-bottom: 1px solid #eee;
  color: var(--app-text-color);
}

.topic-type-item:last-child {
  border-bottom: none;
}
</style>
