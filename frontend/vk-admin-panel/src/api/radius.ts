import apiClient from './client'
import type { ApiResponse } from '@/types/api'

export async function getRadius(): Promise<ApiResponse<number | null>> {
    const { data } = await apiClient.get<ApiResponse<number | null>>('/api/v1/radius')
    return data
}

export async function saveRadius(radiusKm: number): Promise<ApiResponse<null>> {
    const { data } = await apiClient.post<ApiResponse<null>>('/api/v1/radius', {
        radius_km: radiusKm,
    })
    return data
}

export async function deleteRadius(): Promise<ApiResponse<null>> {
    const { data } = await apiClient.delete<ApiResponse<null>>('/api/v1/radius')
    return data
}
