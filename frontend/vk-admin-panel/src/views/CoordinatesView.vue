<template>
  <AppLayout>
    <LoadingSpinner v-if="loading" message="Загрузка координат..." />
    <ErrorAlert v-else-if="error" :message="error" closable @close="error = null" />

    <template v-else>
      <div class="coords-container">
        <div class="coords-form">
          <div class="coords-inputs">
            <div class="field">
              <label>Широта</label>
              <InputNumber
                v-model="lat"
                :min="-90"
                :max="90"
                :step="0.0001"
                :minFractionDigits="6"
                :maxFractionDigits="6"
              />
            </div>
            <div class="field">
              <label>Долгота</label>
              <InputNumber
                v-model="lon"
                :min="-180"
                :max="180"
                :step="0.0001"
                :minFractionDigits="6"
                :maxFractionDigits="6"
              />
            </div>
          </div>
          <div class="coords-actions">
            <Button label="Сохранить" icon="pi pi-check" @click="saveCoords" :loading="saving" />
            <Button
              v-if="hasCoords"
              label="Удалить"
              icon="pi pi-trash"
              severity="danger"
              @click="deleteCoords"
              :loading="deleting"
            />
          </div>
        </div>

        <div class="map-container">
          <div id="yandex-map" ref="mapRef" class="map"></div>
          <p class="map-hint">Перетащите метку на карте для изменения координат</p>
        </div>
      </div>
    </template>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { getCoordinates, saveCoordinates, deleteCoordinates } from '@/api/coordinates'

const YANDEX_API_KEY = import.meta.env.VITE_YANDEX_API_KEY || ''

const loading = ref(true)
const error = ref<string | null>(null)
const saving = ref(false)
const deleting = ref(false)
const hasCoords = ref(false)
const lat = ref(55.7558) // Moscow center as default
const lon = ref(37.6173)
const mapRef = ref<HTMLDivElement>()

let mapInstance: any = null
let placemark: any = null

async function loadYandexMaps(): Promise<void> {
  return new Promise((resolve) => {
    const script = document.createElement('script')
    script.src = `https://api-maps.yandex.ru/2.1/?apikey=${YANDEX_API_KEY}&lang=ru_RU`
    script.onload = () => resolve()
    document.head.appendChild(script)
  })
}

function initMap() {
  if (!mapRef.value || !(window as any).ymaps) return

  const ymaps = (window as any).ymaps
  ymaps.ready(() => {
    mapInstance = new ymaps.Map(mapRef.value, {
      center: [lat.value, lon.value],
      zoom: 10,
    })

    placemark = new ymaps.Placemark(
      [lat.value, lon.value],
      {},
      { draggable: true },
    )

    placemark.events.add('dragend', () => {
      const coords = placemark.geometry.getCoordinates()
      lat.value = coords[0]
      lon.value = coords[1]
    })

    mapInstance.geoObjects.add(placemark)
  })
}

async function saveCoords() {
  saving.value = true
  error.value = null
  const res = await saveCoordinates(lat.value, lon.value)
  if (res.ok) {
    hasCoords.value = true
  } else {
    error.value = res.error || 'Ошибка сохранения'
  }
  saving.value = false
}

async function deleteCoords() {
  deleting.value = true
  error.value = null
  const res = await deleteCoordinates()
  if (res.ok) {
    hasCoords.value = false
    lat.value = 55.7558
    lon.value = 37.6173
  } else {
    error.value = res.error || 'Ошибка удаления'
  }
  deleting.value = false
}

onMounted(async () => {
  // Fetch existing coordinates
  const res = await getCoordinates()
  if (res.ok && res.data) {
    lat.value = res.data.lat
    lon.value = res.data.lon
    hasCoords.value = true
  }
  loading.value = false

  // Load Yandex Maps and init
  await loadYandexMaps()
  initMap()
})
</script>

<style scoped>
.coords-container {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.coords-form {
  background: white;
  padding: 1rem;
  border-radius: 6px;
  border: 1px solid var(--p-surface-200);
}
.coords-inputs {
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.field label {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--p-text-muted-color);
}
.coords-actions {
  display: flex;
  gap: 0.5rem;
}
.map-container {
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--p-surface-200);
}
.map {
  width: 100%;
  height: 400px;
}
.map-hint {
  text-align: center;
  color: var(--p-text-muted-color);
  font-size: 0.85rem;
  padding: 0.5rem;
  margin: 0;
}
</style>
