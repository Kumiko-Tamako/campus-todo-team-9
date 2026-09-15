import { LockOutlined, UserAddOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Form, Input, Radio, Typography } from 'antd'
import { Link, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { authApi } from '../api/auth'
import { getApiErrorMessage } from '../api/errors'

type RegisterValues = {
  student_id?: string
  staff_id?: string
  email: string
  password: string
  role: 'student' | 'teacher'
}

export function RegisterPage() {
  const navigate = useNavigate()
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const onFinish = async (values: RegisterValues) => {
    setErrorMessage(null)
    setIsSubmitting(true)
    try {
      await authApi.register({
        role: values.role,
        email: values.email,
        password: values.password,
        ...(values.role === 'student' ? { student_id: values.student_id } : { staff_id: values.staff_id }),
      })
      navigate('/login', { replace: true, state: { registered: true } })
    } catch (error) {
      setErrorMessage(getApiErrorMessage(error, '注册失败，请检查填写的信息'))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <Card className="auth-card" bordered={false}>
        <div className="auth-heading">
          <span className="brand-mark brand-mark-large">C</span>
          <Typography.Title level={2}>创建你的账号</Typography.Title>
          <Typography.Paragraph type="secondary">加入 CampusOverflow，分享和发现答案</Typography.Paragraph>
        </div>
        {errorMessage ? <Alert className="demo-alert" message={errorMessage} type="error" showIcon /> : null}
        <Form<RegisterValues>
          layout="vertical"
          size="large"
          onFinish={onFinish}
          requiredMark={false}
          initialValues={{ role: 'student' }}
        >
          <Form.Item label="身份" name="role">
            <Radio.Group optionType="button" buttonStyle="solid" options={[{ label: '学生', value: 'student' }, { label: '教师', value: 'teacher' }]} />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, current) => prev.role !== current.role}>
            {({ getFieldValue }) => getFieldValue('role') === 'teacher' ? (
              <Form.Item label="工号" name="staff_id" rules={[{ required: true, message: '请输入工号' }]}>
                <Input prefix={<UserOutlined />} placeholder="请输入工号" autoComplete="username" />
              </Form.Item>
            ) : (
              <Form.Item label="学号" name="student_id" rules={[{ required: true, message: '请输入学号' }]}>
                <Input prefix={<UserOutlined />} placeholder="请输入学号" autoComplete="username" />
              </Form.Item>
            )}
          </Form.Item>
          <Form.Item
            label="邮箱"
            name="email"
            rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}
          >
            <Input placeholder="name@campus.edu.cn" autoComplete="email" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, min: 8, message: '密码至少需要 8 位' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="至少 8 位字符" autoComplete="new-password" />
          </Form.Item>
          <Alert className="demo-alert" message="注册成功后请使用学号或工号登录" type="info" showIcon />
          <Button type="primary" htmlType="submit" block icon={<UserAddOutlined />} loading={isSubmitting}>
            注册并开始
          </Button>
        </Form>
        <Typography.Paragraph className="auth-switch" type="secondary">
          已有账号？ <Link to="/login">返回登录</Link>
        </Typography.Paragraph>
      </Card>
    </main>
  )
}
