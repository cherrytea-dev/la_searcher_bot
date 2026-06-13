import apiClient from './client'
import type { ApiResponse, AuthResult } from '@/types/api'

/**
 * Authenticate via Telegram Login Widget data.
 * Sends {id, hash, auth_date, ...} to backend for verification.
 */
export async function authTg(data: Record<string, unknown>): Promise<ApiResponse<AuthResult>> {
    const { data: response } = await apiClient.post<ApiResponse<AuthResult>>('/api/v1/auth/tg', data)
    return response
}

/**
 * Authenticate via VK ID OAuth 2.0 with PKCE.
 * Sends {code, code_verifier, device_id, redirect_uri} — backend exchanges for access_token.
 */
export async function authVk(params: {
    code: string
    code_verifier: string
    device_id: string
    redirect_uri: string
}): Promise<ApiResponse<AuthResult>> {
    const { data: response } = await apiClient.post<ApiResponse<AuthResult>>('/api/v1/auth/vk', params)
    return response
}
