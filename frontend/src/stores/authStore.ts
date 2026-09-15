import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { TokenPair, UserRole } from '../api/types'

export type AuthUser = {
  id: string
  email: string
  studentId: string | null
  staffId: string | null
  createdAt: string
  displayName: string
  role: UserRole
}

type AuthState = {
  accessToken: string | null
  refreshToken: string | null
  user: AuthUser | null
  setTokens: (tokens: TokenPair) => void
  setUser: (user: AuthUser) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      setTokens: ({ access_token, refresh_token }) => set({ accessToken: access_token, refreshToken: refresh_token }),
      setUser: (user) => set({ user }),
      logout: () => set({ accessToken: null, refreshToken: null, user: null }),
    }),
    {
      name: 'campus-overflow-auth',
      partialize: ({ accessToken, refreshToken, user }) => ({ accessToken, refreshToken, user }),
    },
  ),
)
