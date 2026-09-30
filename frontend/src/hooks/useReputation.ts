import { useQuery } from '@tanstack/react-query'
import { reputationApi } from '../api/reputation'

export function useReputation(userId: string | undefined) {
  return useQuery({
    queryKey: ['reputation', userId],
    queryFn: () => reputationApi.get(userId!),
    enabled: Boolean(userId),
  })
}
