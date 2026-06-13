import apiClient from './client'
import type { ApiResponse, ActiveSearch } from '@/types/api'

export async function getActiveSearches(): Promise<ApiResponse<ActiveSearch[]>> {
    const { data } = await apiClient.get<ApiResponse<ActiveSearch[]>>('/api/v1/searches/active')
    return data
}
