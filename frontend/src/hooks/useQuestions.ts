import { useQuery } from '@tanstack/react-query'
import { questionsApi } from '../api/questions'
import type { QuestionSort } from '../api/questions'

export function useQuestions(params: { page: number; pageSize: number; sort: QuestionSort }) {
  return useQuery({
    queryKey: ['questions', params],
    queryFn: () => questionsApi.list({ page: params.page, page_size: params.pageSize, sort: params.sort }),
  })
}

export function useTags() {
  return useQuery({ queryKey: ['tags'], queryFn: questionsApi.listTags, staleTime: 300_000 })
}

export function useQuestion(questionId: string | undefined) {
  return useQuery({
    queryKey: ['questions', questionId],
    queryFn: () => questionsApi.get(questionId!),
    enabled: Boolean(questionId),
  })
}
