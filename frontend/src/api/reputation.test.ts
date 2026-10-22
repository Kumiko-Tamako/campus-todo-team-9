import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('./client', () => ({ apiClient: apiMocks }))

import { reputationApi } from './reputation'

describe('reputationApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('requests the current-user reputation contract path', async () => {
    const response = { user_id: 'user-id', total: 12, entries: [] }
    apiMocks.get.mockResolvedValue({ data: response })

    await expect(reputationApi.get('user-id')).resolves.toEqual(response)
    expect(apiMocks.get).toHaveBeenCalledWith('/v1/users/user-id/reputation')
  })
})
