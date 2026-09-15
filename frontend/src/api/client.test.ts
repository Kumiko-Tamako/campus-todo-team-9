import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => {
  const apiClient = {
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
    request: vi.fn(),
  }
  const refreshClient = { post: vi.fn() }
  const storeState = {
    accessToken: 'old-access-token' as string | null,
    refreshToken: 'old-refresh-token' as string | null,
    setTokens: vi.fn(),
    logout: vi.fn(),
  }

  return { apiClient, refreshClient, storeState }
})

vi.mock('axios', () => ({
  default: {
    create: vi.fn()
      .mockReturnValueOnce(mocks.apiClient)
      .mockReturnValueOnce(mocks.refreshClient),
  },
}))

vi.mock('../stores/authStore', () => ({
  useAuthStore: {
    getState: () => mocks.storeState,
  },
}))

import './client'

const requestInterceptor = mocks.apiClient.interceptors.request.use.mock.calls[0][0] as (config: { headers: { set: ReturnType<typeof vi.fn> } }) => unknown
const responseErrorInterceptor = mocks.apiClient.interceptors.response.use.mock.calls[0][1] as (error: unknown) => Promise<unknown>

describe('apiClient authentication interceptors', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.storeState.accessToken = 'old-access-token'
    mocks.storeState.refreshToken = 'old-refresh-token'
  })

  it('adds the current access token to protected requests', () => {
    const headers = { set: vi.fn() }
    const config = { headers }

    expect(requestInterceptor(config)).toEqual(config)
    expect(headers.set).toHaveBeenCalledWith('Authorization', 'Bearer old-access-token')
  })

  it('rotates and persists both tokens before retrying a 401 request', async () => {
    const nextTokens = {
      access_token: 'new-access-token',
      refresh_token: 'new-refresh-token',
      token_type: 'bearer',
      expires_in: 900,
    }
    mocks.refreshClient.post.mockResolvedValue({ data: nextTokens })
    mocks.apiClient.request.mockResolvedValue({ data: { ok: true } })
    const headers = { set: vi.fn() }
    const request = { url: '/v1/questions', headers }

    await expect(responseErrorInterceptor({ response: { status: 401 }, config: request })).resolves.toEqual({ data: { ok: true } })

    expect(mocks.refreshClient.post).toHaveBeenCalledWith('/v1/auth/refresh', { refresh_token: 'old-refresh-token' })
    expect(mocks.storeState.setTokens).toHaveBeenCalledWith(nextTokens)
    expect(request).toMatchObject({ _retry: true })
    expect(headers.set).toHaveBeenCalledWith('Authorization', 'Bearer new-access-token')
    expect(mocks.apiClient.request).toHaveBeenCalledWith(request)
  })

  it('does not refresh public login requests', async () => {
    const error = { response: { status: 401 }, config: { url: '/v1/auth/login', headers: { set: vi.fn() } } }

    await expect(responseErrorInterceptor(error)).rejects.toEqual(error)
    expect(mocks.refreshClient.post).not.toHaveBeenCalled()
    expect(mocks.storeState.logout).not.toHaveBeenCalled()
  })

  it('clears the session when a 401 request has no refresh token', async () => {
    mocks.storeState.refreshToken = null
    const error = { response: { status: 401 }, config: { url: '/v1/questions', headers: { set: vi.fn() } } }

    await expect(responseErrorInterceptor(error)).rejects.toThrow('没有可用的刷新令牌')
    expect(mocks.storeState.logout).toHaveBeenCalledOnce()
  })
})
