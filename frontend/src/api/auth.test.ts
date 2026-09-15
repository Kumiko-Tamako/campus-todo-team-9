import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('./client', () => ({ apiClient: apiMocks }))

import { authApi } from './auth'

describe('authApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('posts the login payload to the contract endpoint', async () => {
    const tokens = {
      access_token: 'access-token',
      refresh_token: 'refresh-token',
      token_type: 'bearer',
      expires_in: 900,
    }
    apiMocks.post.mockResolvedValue({ data: tokens })

    await expect(authApi.login({ identifier: '20260001', password: 'password123' })).resolves.toEqual(tokens)
    expect(apiMocks.post).toHaveBeenCalledWith('/v1/auth/login', {
      identifier: '20260001',
      password: 'password123',
    })
  })

  it('sends only the student identifier for student registration', async () => {
    apiMocks.post.mockResolvedValue({ data: { id: 'user-id' } })

    await authApi.register({
      role: 'student',
      email: 'student@campus.edu.cn',
      password: 'password123',
      student_id: '20260001',
    })

    expect(apiMocks.post).toHaveBeenCalledWith('/v1/auth/register', {
      role: 'student',
      email: 'student@campus.edu.cn',
      password: 'password123',
      student_id: '20260001',
    })
  })

  it('sends only the staff identifier for teacher registration', async () => {
    apiMocks.post.mockResolvedValue({ data: { id: 'user-id' } })

    await authApi.register({
      role: 'teacher',
      email: 'teacher@campus.edu.cn',
      password: 'password123',
      staff_id: 'T10001',
    })

    expect(apiMocks.post).toHaveBeenCalledWith('/v1/auth/register', {
      role: 'teacher',
      email: 'teacher@campus.edu.cn',
      password: 'password123',
      staff_id: 'T10001',
    })
  })

  it('uses the current-user and logout contract endpoints', async () => {
    const user = {
      id: 'user-id',
      role: 'student',
      email: 'student@campus.edu.cn',
      student_id: '20260001',
      staff_id: null,
      created_at: '2026-09-15T00:00:00Z',
    }
    apiMocks.get.mockResolvedValue({ data: user })
    apiMocks.post.mockResolvedValue({ data: undefined })

    await expect(authApi.me()).resolves.toEqual(user)
    await authApi.logout('refresh-token')

    expect(apiMocks.get).toHaveBeenCalledWith('/v1/auth/me')
    expect(apiMocks.post).toHaveBeenCalledWith('/v1/auth/logout', { refresh_token: 'refresh-token' })
  })
})
