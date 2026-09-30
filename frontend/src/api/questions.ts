import { apiClient } from './client'
import type { AnswerResponse, CommentResponse } from './types'

export type QuestionSort = 'latest' | 'votes'

export type QuestionListItem = {
  id: string
  title: string
  author_id: string
  created_at: string
  tags: string[]
}

export type QuestionListResponse = {
  items: QuestionListItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export type QuestionResponse = {
  id: string
  title: string
  body: string
  author_id: string
  created_at: string
  tags: string[]
}

export type QuestionDetailResponse = QuestionResponse & {
  accepted_answer_id: string | null
  answers: AnswerResponse[]
  comments: CommentResponse[]
}

export type QuestionDetail = QuestionResponse & {
  accepted_answer_id: string | null
  tags: string[]
  answers: AnswerResponse[]
  comments: CommentResponse[]
}

function normalizeAnswer(answer: AnswerResponse): AnswerResponse {
  return { ...answer, comments: answer.comments ?? [] }
}

export const questionsApi = {
  list(params?: { page?: number; page_size?: number; sort?: QuestionSort }) {
    return apiClient.get<QuestionListResponse>('/v1/questions', { params }).then(({ data }) => ({
      ...data,
      items: data.items.map((item) => ({ ...item, tags: item.tags ?? [] })),
    }))
  },
  get(questionId: string) {
    return apiClient.get<QuestionDetailResponse>(`/v1/questions/${questionId}`).then(({ data }) => ({
      ...data,
      tags: data.tags ?? [],
      answers: (data.answers ?? []).map(normalizeAnswer),
      accepted_answer_id: data.accepted_answer_id ?? null,
      comments: data.comments ?? [],
    }))
  },
  create(payload: { title: string; body: string; tags?: string[] }) {
    return apiClient.post<QuestionResponse>('/v1/questions', payload).then(({ data }) => ({ ...data, tags: data.tags ?? [] }))
  },
  postAnswer(questionId: string, payload: { body: string }) {
    return apiClient.post<AnswerResponse>(`/v1/questions/${questionId}/answers`, payload).then(({ data }) => normalizeAnswer(data))
  },
  voteQuestion(questionId: string, direction: 'up' | 'down') {
    return apiClient.post<void>(`/v1/questions/${questionId}/vote`, { direction })
  },
  voteAnswer(questionId: string, answerId: string, direction: 'up' | 'down') {
    return apiClient.post<void>(`/v1/questions/${questionId}/answers/${answerId}/vote`, { direction })
  },
  commentQuestion(questionId: string, payload: { body: string }) {
    return apiClient.post<CommentResponse>(`/v1/questions/${questionId}/comments`, payload).then(({ data }) => data)
  },
  commentAnswer(answerId: string, payload: { body: string }) {
    return apiClient.post<CommentResponse>(`/v1/answers/${answerId}/comments`, payload).then(({ data }) => data)
  },
  acceptAnswer(answerId: string) {
    return apiClient.post<void>(`/v1/answers/${answerId}/accept`)
  },
  listTags() {
    return apiClient.get<{ tags: string[] }>('/v1/tags').then(({ data }) => data.tags)
  },
}
