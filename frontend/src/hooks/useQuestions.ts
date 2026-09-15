import { useQuery } from '@tanstack/react-query'
import { questionsApi } from '../api/questions'

export function useQuestions() {
  return useQuery({
    queryKey: ['questions'],
    queryFn: () => questionsApi.list(),
  })
}

export function useQuestion(questionId: string | undefined) {
  return useQuery({
    queryKey: ['questions', questionId],
    queryFn: () => questionsApi.get(questionId!),
    enabled: Boolean(questionId),
  })
}
