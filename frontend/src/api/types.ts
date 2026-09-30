export type UserRole = 'student' | 'teacher'

export type TokenPair = {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export type RegisterRequest = {
  role: UserRole
  email: string
  password: string
  student_id?: string
  staff_id?: string
}

export type AuthUserResponse = {
  id: string
  role: UserRole
  email: string
  student_id: string | null
  staff_id: string | null
  created_at: string
}

export type LoginRequest = {
  identifier: string
  password: string
}

export type CommentResponse = {
  id: string
  body: string
  author_id: string
  created_at: string
}

export type AnswerResponse = {
  id: string
  body: string
  author_id: string
  created_at: string
  votes: number
  is_accepted: boolean
  comments: CommentResponse[]
}

export type ReputationEntryResponse = {
  source: string
  event_id: string
  delta: number
  reason: string
  occurred_at: string
}

export type ReputationResponse = {
  user_id: string
  total: number
  entries: ReputationEntryResponse[]
}

