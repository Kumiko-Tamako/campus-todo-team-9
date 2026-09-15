import { apiClient } from './client'

export type QuestionListItem = {
  id: string
  title: string
  author_id: string
  created_at: string
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
}

export type QuestionDetailResponse = QuestionResponse & {
  tags?: string[]
  answers?: string[]
}

export type QuestionDetail = QuestionResponse & {
  tags: string[]
  answers: string[]
}

export const questionsApi = {
  list(params?: { page?: number; page_size?: number }) {
    return apiClient.get<QuestionListResponse>('/v1/questions', { params }).then(({ data }) => data)
  },
  get(questionId: string) {
    return apiClient.get<QuestionDetailResponse>(`/v1/questions/${questionId}`).then(({ data }) => ({
      ...data,
      tags: data.tags ?? [],
      answers: data.answers ?? [],
    }))
  },
  create(payload: { title: string; body: string }) {
    return apiClient.post<QuestionResponse>('/v1/questions', payload).then(({ data }) => data)
  },
}
