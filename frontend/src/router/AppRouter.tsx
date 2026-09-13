import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '../components/AppShell'
import { useAuthStore } from '../stores/authStore'
import { LoginPage } from '../pages/LoginPage'
import { NewQuestionPage } from '../pages/NewQuestionPage'
import { QuestionDetailPage } from '../pages/QuestionDetailPage'
import { QuestionsPage } from '../pages/QuestionsPage'
import { RegisterPage } from '../pages/RegisterPage'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((state) => state.token)
  return token ? children : <Navigate to="/login" replace />
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/questions" replace />} />
          <Route path="/questions" element={<QuestionsPage />} />
          <Route path="/questions/:questionId" element={<QuestionDetailPage />} />
          <Route
            path="/questions/new"
            element={
              <ProtectedRoute>
                <NewQuestionPage />
              </ProtectedRoute>
            }
          />
        </Route>
        <Route path="*" element={<Navigate to="/questions" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
