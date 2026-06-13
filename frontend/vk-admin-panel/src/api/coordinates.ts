import apiClient from './client'
import type { ApiResponse } from '@/types/api'

export interface CoordinatesData {
    lat: number
    lon: number
}

export async function getCoordinates(): Promise<ApiResponse<CoordinatesData | null>> {
    const { data } = await apiClient.get<ApiResponse<CoordinatesData | null>>('/api/v1/coordinates')
    return data
}

export async function saveCoordinates(lat: number, lon: number): Promise<ApiResponse<null>> {
    const { data } = await apiClient.post<ApiResponse<null>>('/api/v1/coordinates', {
        latitude: lat,
        longitude: lon,
    })
    return data
}

export async function deleteCoordinates(): Promise<ApiResponse<null>> {
    const { data } = await apiClient.delete<ApiResponse<null>>('/api/v1/coordinates')
    return data
}
