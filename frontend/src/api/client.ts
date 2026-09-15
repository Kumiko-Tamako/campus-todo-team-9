import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import type { TokenPair } from './types'
import { useAuthStore } from '../stores/authStore'

type RetryableRequestConfig = InternalAxiosRequestConfig & { _retry?: boolean }

export const apiClient = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

const refreshClient = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const { refreshToken } = useAuthStore.getState()
  if (!refreshToken) {
    throw new Error('没有可用的刷新令牌')
  }

  if (!refreshPromise) {
    refreshPromise = refreshClient
      .post<TokenPair>('/v1/auth/refresh', { refresh_token: refreshToken })
      .then(({ data }) => {
        useAuthStore.getState().setTokens(data)
        return data.access_token
      })
      .finally(() => {
        refreshPromise = null
      })
  }

  return refreshPromise
}

apiClient.interceptors.request.use((config) => {
  const accessToken = useAuthStore.getState().accessToken
  if (accessToken) {
    config.headers.set('Authorization', `Bearer ${accessToken}`)
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetryableRequestConfig | undefined
    const isRefreshRequest = originalRequest?.url?.includes('/auth/refresh')

    if (error.response?.status !== 401 || !originalRequest || originalRequest._retry || isRefreshRequest) {
      return Promise.reject(error)
    }

    originalRequest._retry = true
    try {
      const accessToken = await refreshAccessToken()
      originalRequest.headers.set('Authorization', `Bearer ${accessToken}`)
      return apiClient.request(originalRequest)
    } catch (refreshError) {
      useAuthStore.getState().logout()
      return Promise.reject(refreshError)
    }
  },
)

