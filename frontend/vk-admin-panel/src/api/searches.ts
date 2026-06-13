import apiClient from './client'
import type { ApiResponse, ActiveSearch } from '@/types/api'

export async function getActiveSearches(): Promise<ApiResponse<ActiveSearch[]>> {
    const { data } = await apiClient.post<ApiResponse<ActiveSearch[]>>('/', {
        path: '/api/v1/searches/active',
    })
    return data
}
