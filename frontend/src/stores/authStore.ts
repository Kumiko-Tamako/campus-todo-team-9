import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type AuthUser = {
  identifier: string
  displayName: string
  role: 'student' | 'teacher'
}

type AuthState = {
  token: string | null
  user: AuthUser | null
  login: (user: AuthUser) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      login: (user) => set({ token: 'demo-access-token', user }),
      logout: () => set({ token: null, user: null }),
    }),
    { name: 'campus-overflow-auth' },
  ),
)
