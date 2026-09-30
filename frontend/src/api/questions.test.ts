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
    apiMocks.get.mockResolvedValue({ data: {
      items: [{ id: 'question-id', title: '标题', author_id: 'author-id', created_at: '2026-09-15T00:00:00Z' }],
      total: 1,
      page: 2,
      page_size: 10,
      total_pages: 1,
    } })

    await expect(questionsApi.list({ page: 2, page_size: 10, sort: 'votes' })).resolves.toMatchObject({
      items: [{ id: 'question-id', tags: [] }],
    })

    expect(apiMocks.get).toHaveBeenCalledWith('/v1/questions', { params: { page: 2, page_size: 10, sort: 'votes' } })
  })

  it('posts only title and body when creating a question', async () => {
    apiMocks.post.mockResolvedValue({ data: { id: 'question-id' } })

    await questionsApi.create({ title: '一个问题标题', body: '问题的详细描述' })

    expect(apiMocks.post).toHaveBeenCalledWith('/v1/questions', {
      title: '一个问题标题',
      body: '问题的详细描述',
    })
  })

  it('normalizes optional detail collections to empty arrays', async () => {
    apiMocks.get.mockResolvedValue({
      data: {
        id: 'question-id',
        title: '问题标题',
        body: '问题正文',
        author_id: 'author-id',
        created_at: '2026-09-15T00:00:00Z',
        answers: [{ id: 'answer-id', body: '回答', author_id: 'author-id', created_at: '2026-09-15T00:00:00Z', votes: 2, is_accepted: false }],
      },
    })

    await expect(questionsApi.get('question-id')).resolves.toMatchObject({
      tags: [],
      answers: [{ id: 'answer-id', comments: [] }],
      comments: [],
      accepted_answer_id: null,
    })
    expect(apiMocks.get).toHaveBeenCalledWith('/v1/questions/question-id')
  })

  it('sends tags when creating a question and normalizes the response', async () => {
    apiMocks.post.mockResolvedValue({ data: { id: 'question-id', title: '标题', body: '正文' } })

    await expect(questionsApi.create({ title: '标题', body: '正文', tags: ['React'] })).resolves.toMatchObject({
      id: 'question-id',
      tags: [],
    })
    expect(apiMocks.post).toHaveBeenCalledWith('/v1/questions', { title: '标题', body: '正文', tags: ['React'] })
  })

  it('uses the answer, vote, comment, accept, and tag contract paths', async () => {
    apiMocks.post.mockImplementation(async (path: string) => {
      if (path.endsWith('/answers')) {
        return { data: { id: 'answer-id', body: '回答', author_id: 'author-id', created_at: '2026-09-15T00:00:00Z', votes: 0, is_accepted: false } }
      }
      if (path.includes('/comments')) {
        return { data: { id: 'comment-id', body: '评论', author_id: 'author-id', created_at: '2026-09-15T00:00:00Z' } }
      }
      return { data: undefined }
    })
    apiMocks.get.mockResolvedValue({ data: { tags: ['React', 'TypeScript'] } })

    await expect(questionsApi.postAnswer('question-id', { body: '回答' })).resolves.toMatchObject({ comments: [] })
    await questionsApi.voteQuestion('question-id', 'up')
    await questionsApi.voteAnswer('question-id', 'answer-id', 'down')
    await questionsApi.commentQuestion('question-id', { body: '评论问题' })
    await questionsApi.commentAnswer('answer-id', { body: '评论回答' })
    await questionsApi.acceptAnswer('answer-id')
    await expect(questionsApi.listTags()).resolves.toEqual(['React', 'TypeScript'])

    expect(apiMocks.post).toHaveBeenNthCalledWith(1, '/v1/questions/question-id/answers', { body: '回答' })
    expect(apiMocks.post).toHaveBeenNthCalledWith(2, '/v1/questions/question-id/vote', { direction: 'up' })
    expect(apiMocks.post).toHaveBeenNthCalledWith(3, '/v1/questions/question-id/answers/answer-id/vote', { direction: 'down' })
    expect(apiMocks.post).toHaveBeenNthCalledWith(4, '/v1/questions/question-id/comments', { body: '评论问题' })
    expect(apiMocks.post).toHaveBeenNthCalledWith(5, '/v1/answers/answer-id/comments', { body: '评论回答' })
    expect(apiMocks.post).toHaveBeenNthCalledWith(6, '/v1/answers/answer-id/accept')
    expect(apiMocks.get).toHaveBeenCalledWith('/v1/tags')
  })
})
