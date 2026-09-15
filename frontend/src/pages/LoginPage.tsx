import { LockOutlined, LoginOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Form, Input, Typography } from 'antd'
import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { authApi } from '../api/auth'
import { getApiErrorMessage } from '../api/errors'

type LoginValues = {
  identifier: string
  password: string
}

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const setTokens = useAuthStore((state) => state.setTokens)
  const setUser = useAuthStore((state) => state.setUser)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const from = (location.state as { from?: string } | null)?.from ?? '/questions'

  const onFinish = async (values: LoginValues) => {
    setErrorMessage(null)
    setIsSubmitting(true)
    try {
      const tokens = await authApi.login(values)
      setTokens(tokens)
      const user = await authApi.me()
      setUser({
        id: user.id,
        email: user.email,
        studentId: user.student_id,
        staffId: user.staff_id,
        createdAt: user.created_at,
        displayName: user.student_id ?? user.staff_id ?? user.email,
        role: user.role,
      })
      navigate(from, { replace: true })
    } catch (error) {
      useAuthStore.getState().logout()
      setErrorMessage(getApiErrorMessage(error, '登录失败，请检查账号和密码'))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <Card className="auth-card" bordered={false}>
        <div className="auth-heading">
          <span className="brand-mark brand-mark-large">C</span>
          <Typography.Title level={2}>欢迎回到 CampusOverflow</Typography.Title>
          <Typography.Paragraph type="secondary">登录后参与校园知识交流</Typography.Paragraph>
        </div>
        {errorMessage ? <Alert className="demo-alert" message={errorMessage} type="error" showIcon /> : null}
        <Form<LoginValues>
          layout="vertical"
          size="large"
          onFinish={onFinish}
          requiredMark={false}
          onFinishFailed={() => undefined}
        >
          <Form.Item
            label="学号 / 工号"
            name="identifier"
            rules={[{ required: true, message: '请输入学号或工号' }]}
          >
            <Input prefix={<UserOutlined />} placeholder="例如：20260001" autoComplete="username" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="请输入密码" autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block icon={<LoginOutlined />} loading={isSubmitting}>
            登录
          </Button>
        </Form>
        <Typography.Paragraph className="auth-switch" type="secondary">
          还没有账号？ <Link to="/register">立即注册</Link>
        </Typography.Paragraph>
      </Card>
    </main>
  )
}
