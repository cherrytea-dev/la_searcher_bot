import apiClient from './client'
import type { ApiResponse, Region } from '@/types/api'

export async function getRegions(): Promise<ApiResponse<Region[]>> {
    const { data } = await apiClient.get<ApiResponse<Region[]>>('/api/v1/regions')
    return data
}

export async function toggleRegion(regionName: string): Promise<ApiResponse<null>> {
    const { data } = await apiClient.post<ApiResponse<null>>('/api/v1/regions/toggle', {
        region_name: regionName,
    })
    return data
}
