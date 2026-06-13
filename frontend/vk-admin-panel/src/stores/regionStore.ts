import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Region } from '@/types/api'
import { getRegions, toggleRegion } from '@/api/regions'

export const useRegionStore = defineStore('region', () => {
    const regions = ref<Region[]>([])
    const loading = ref(false)
    const error = ref<string | null>(null)
    const searchQuery = ref('')

    const filteredRegions = computed(() => {
        if (!searchQuery.value) return regions.value
        const q = searchQuery.value.toLowerCase()
        return regions.value.filter((r) => r.name.toLowerCase().includes(q))
    })

    const subscribedCount = computed(() => regions.value.filter((r) => r.subscribed).length)

    async function fetchRegions() {
        loading.value = true
        error.value = null
        try {
            const res = await getRegions()
            if (res.ok && res.data) {
                regions.value = res.data
            } else {
                error.value = res.error || 'Failed to load regions'
            }
        } catch {
            error.value = 'Network error while loading regions'
        } finally {
            loading.value = false
        }
    }

    async function toggle(name: string) {
        const res = await toggleRegion(name)
        if (res.ok) {
            await fetchRegions()
        } else {
            error.value = res.error || 'Failed to toggle region'
        }
    }

    return {
        regions,
        loading,
        error,
        searchQuery,
        filteredRegions,
        subscribedCount,
        fetchRegions,
        toggle,
    }
})
