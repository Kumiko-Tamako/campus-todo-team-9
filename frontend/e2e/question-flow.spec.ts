import { expect, test } from '@playwright/test'

const user = {
  id: 'user-1',
  email: 'student@campus.edu.cn',
  student_id: '20260001',
  staff_id: null,
  created_at: '2026-10-22T00:00:00Z',
  role: 'student',
}

const question = {
  id: 'question-1',
  title: '如何为 React 项目设计登录状态？',
  body: '我希望在刷新后保留登录状态，并且能正确处理令牌过期。',
  author_id: user.id,
  created_at: '2026-10-22T00:00:00Z',
  tags: ['React'],
  status: 'open',
}

test('用户可以登录、浏览问题并提交新问题', async ({ page }) => {
  await page.route('**/api/v1/auth/login', async (route) => {
    await route.fulfill({ json: { access_token: 'access-token', refresh_token: 'refresh-token', token_type: 'bearer', expires_in: 900 } })
  })
  await page.route('**/api/v1/auth/me', async (route) => {
    await route.fulfill({ json: user })
  })
  await page.route('**/api/v1/questions/question-1', async (route) => {
    await route.fulfill({ json: { ...question, accepted_answer_id: null, answers: [], comments: [] } })
  })
  await page.route('**/api/v1/tags', async (route) => {
    await route.fulfill({ json: { tags: ['React', 'TypeScript'] } })
  })
  await page.route(/\/api\/v1\/questions(?:\?.*)?$/, async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ json: { ...question, id: 'question-2', title: '新问题：如何测试路由？' } })
      return
    }
    await route.fulfill({ json: { items: [question], total: 1, page: 1, page_size: 10, total_pages: 1 } })
  })

  await page.goto('/login')
  await page.getByLabel('学号 / 工号').fill('20260001')
  await page.getByLabel('密码').fill('Passw0rd!')
  await page.getByRole('button', { name: '登录' }).click()

  await expect(page).toHaveURL(/\/questions$/)
  await expect(page.getByRole('link', { name: question.title })).toBeVisible()
  await page.getByRole('link', { name: question.title }).click()
  await expect(page).toHaveURL(/\/questions\/question-1$/)
  await expect(page.getByRole('heading', { name: question.title })).toBeVisible()

  await page.getByRole('link', { name: '发布问题' }).click()
  await expect(page).toHaveURL(/\/questions\/new$/)
  await page.getByLabel('标题').fill('新问题：如何测试路由？')
  await page.getByLabel('问题描述').fill('我想为路由和权限边界补充一个稳定的浏览器测试。')
  await page.getByRole('button', { name: '发布问题' }).click()

  await expect(page).toHaveURL(/\/questions\/question-2$/)
})
