<template>
  <AppLayout>
    <LoadingSpinner v-if="loading" message="Загрузка активных поисков..." />
    <ErrorAlert v-else-if="error" :message="error" closable @close="error = null" />

    <template v-else>
      <Card>
        <template #content>
          <h3>Активные поиски</h3>
          <p class="text-secondary" v-if="searches.length === 0">Нет активных поисков в ваших регионах</p>

          <DataTable
            v-else
            :value="searches"
            stripedRows
            paginator
            :rows="20"
            :rowsPerPageOptions="[10, 20, 50]"
            sortField="started_at"
            :sortOrder="-1"
          >
            <Column field="topic_id" header="ID" sortable style="width: 80px" />
            <Column field="title" header="Название" sortable>
              <template #body="{ data }">
                <a
                  :href="forumTopicUrl(data.topic_id)"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {{ data.title }}
                </a>
              </template>
            </Column>
            <Column field="status" header="Статус" sortable style="width: 120px" />
            <Column field="started_at" header="Начало" sortable style="width: 160px">
              <template #body="{ data }">
                {{ formatDate(data.started_at) }}
              </template>
            </Column>
            <Column field="region_name" header="Регион" sortable style="width: 150px" />
          </DataTable>
        </template>
      </Card>
    </template>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getActiveSearches } from '@/api/searches'
import type { ActiveSearch } from '@/types/api'

const FORUM_BASE_URL = 'https://lizaalert.org/forum/viewtopic.php?t='

const loading = ref(true)
const error = ref<string | null>(null)
const searches = ref<ActiveSearch[]>([])

function forumTopicUrl(topicId: number): string {
  return `${FORUM_BASE_URL}${topicId}`
}

function formatDate(dateStr: string): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

onMounted(async () => {
  error.value = null
  const res = await getActiveSearches()
  if (res.ok) {
    searches.value = res.data || []
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

a {
  color: var(--p-primary-color, #3b82f6);
  text-decoration: none;
}

a:hover {
  text-decoration: underline;
}
</style>
