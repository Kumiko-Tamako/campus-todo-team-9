import { useQuery } from '@tanstack/react-query'
import { useQuestionStore } from '../stores/questionStore'

export function useQuestions() {
  return useQuery({
    queryKey: ['questions'],
    queryFn: async () => useQuestionStore.getState().questions,
  })
}

export function useQuestion(questionId: string | undefined) {
  return useQuery({
    queryKey: ['questions', questionId],
    queryFn: async () => {
      const question = useQuestionStore.getState().questions.find((item) => item.id === questionId)
      if (!question) {
        throw new Error('问题不存在')
      }
      return question
    },
    enabled: Boolean(questionId),
  })
}
