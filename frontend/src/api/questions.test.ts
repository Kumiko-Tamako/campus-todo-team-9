import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('./client', () => ({ apiClient: apiMocks }))

import { questionsApi } from './questions'

describe('questionsApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('requests the paginated question list with the contract path and params', async () => {
    apiMocks.get.mockResolvedValue({ data: { items: [], total: 0, page: 2, page_size: 10, total_pages: 0 } })

    await questionsApi.list({ page: 2, page_size: 10 })

    expect(apiMocks.get).toHaveBeenCalledWith('/v1/questions', { params: { page: 2, page_size: 10 } })
  })

  it('posts only title and body when creating a question', async () => {
    apiMocks.post.mockResolvedValue({ data: { id: 'question-id' } })

    await questionsApi.create({ title: '一个问题标题', body: '问题的详细描述' })

    expect(apiMocks.post).toHaveBeenCalledWith('/v1/questions', {
      title: '一个问题标题',
      body: '问题的详细描述',
    })
  })
})

