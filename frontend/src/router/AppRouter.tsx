import { lazy, Suspense, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'

const AppShell = lazy(() => import('../components/AppShell').then(({ AppShell: component }) => ({ default: component })))
const LoginPage = lazy(() => import('../pages/LoginPage').then(({ LoginPage: component }) => ({ default: component })))
const NewQuestionPage = lazy(() => import('../pages/NewQuestionPage').then(({ NewQuestionPage: component }) => ({ default: component })))
const QuestionDetailPage = lazy(() => import('../pages/QuestionDetailPage').then(({ QuestionDetailPage: component }) => ({ default: component })))
const QuestionsPage = lazy(() => import('../pages/QuestionsPage').then(({ QuestionsPage: component }) => ({ default: component })))
const RegisterPage = lazy(() => import('../pages/RegisterPage').then(({ RegisterPage: component }) => ({ default: component })))
const ReputationPage = lazy(() => import('../pages/ReputationPage').then(({ ReputationPage: component }) => ({ default: component })))
const TagsPage = lazy(() => import('../pages/TagsPage').then(({ TagsPage: component }) => ({ default: component })))

function PageLoading() {
  return <div className="page-loading" role="status">正在加载页面...</div>
}

function ProtectedRoute({ children }: { children: ReactNode }) {
  const accessToken = useAuthStore((state) => state.accessToken)
  return accessToken ? children : <Navigate to="/login" replace />
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageLoading />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route element={<AppShell />}>
            <Route index element={<Navigate to="/questions" replace />} />
            <Route path="/questions" element={<QuestionsPage />} />
            <Route path="/tags" element={<TagsPage />} />
            <Route path="/reputation" element={<ProtectedRoute><ReputationPage /></ProtectedRoute>} />
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
      </Suspense>
    </BrowserRouter>
  )
}
