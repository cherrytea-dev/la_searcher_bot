import apiClient from './client'
import type { ApiResponse, AuthResult } from '@/types/api'

/**
 * Authenticate via Telegram Login Widget data.
 * Sends {id, hash, auth_date, ...} to backend for verification.
 */
export async function authTg(data: Record<string, unknown>): Promise<ApiResponse<AuthResult>> {
    const { data: response } = await apiClient.post<ApiResponse<AuthResult>>('/', {
        path: '/api/v1/auth/tg',
        ...data,
    })
    return response
}

/**
 * Authenticate via VK OAuth 2.0 code exchange.
 * Sends {code, redirect_uri} — backend exchanges for access_token.
 */
export async function authVk(code: string, redirectUri: string): Promise<ApiResponse<AuthResult>> {
    const { data: response } = await apiClient.post<ApiResponse<AuthResult>>('/', {
        path: '/api/v1/auth/vk',
        code,
        redirect_uri: redirectUri,
    })
    return response
}
