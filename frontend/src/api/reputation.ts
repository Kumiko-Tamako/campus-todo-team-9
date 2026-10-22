import { apiClient } from './client'
import type { ReputationResponse } from './types'

export const reputationApi = {
  get(userId: string) {
    return apiClient.get<ReputationResponse>(`/v1/users/${userId}/reputation`).then(({ data }) => data)
  },
}
