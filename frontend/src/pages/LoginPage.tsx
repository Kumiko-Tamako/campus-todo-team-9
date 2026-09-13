import { LockOutlined, LoginOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Form, Input, Typography } from 'antd'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'

type LoginValues = {
  identifier: string
  password: string
}

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const login = useAuthStore((state) => state.login)
  const from = (location.state as { from?: string } | null)?.from ?? '/questions'

  const onFinish = (values: LoginValues) => {
    login({ identifier: values.identifier, displayName: values.identifier, role: 'student' })
    navigate(from, { replace: true })
  }

  return (
    <main className="auth-page">
      <Card className="auth-card" bordered={false}>
        <div className="auth-heading">
          <span className="brand-mark brand-mark-large">C</span>
          <Typography.Title level={2}>欢迎回到 CampusOverflow</Typography.Title>
          <Typography.Paragraph type="secondary">登录后参与校园知识交流</Typography.Paragraph>
        </div>
        <Form<LoginValues> layout="vertical" size="large" onFinish={onFinish} requiredMark={false}>
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
          <Alert className="demo-alert" message="当前为演示模式，输入任意符合格式的账号密码即可登录" type="info" showIcon />
          <Button type="primary" htmlType="submit" block icon={<LoginOutlined />}>
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
