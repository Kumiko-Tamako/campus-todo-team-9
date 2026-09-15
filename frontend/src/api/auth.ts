import { apiClient } from './client'
import type { AuthUserResponse, LoginRequest, RegisterRequest, TokenPair } from './types'

export const authApi = {
  login(payload: LoginRequest) {
    return apiClient.post<TokenPair>('/v1/auth/login', payload).then(({ data }) => data)
  },
  register(payload: RegisterRequest) {
    return apiClient.post<AuthUserResponse>('/v1/auth/register', payload).then(({ data }) => data)
  },
  me() {
    return apiClient.get<AuthUserResponse>('/v1/auth/me').then(({ data }) => data)
  },
  logout(refreshToken: string) {
    return apiClient.post<void>('/v1/auth/logout', { refresh_token: refreshToken })
  },
}

