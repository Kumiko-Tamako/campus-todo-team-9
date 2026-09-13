import { ArrowLeftOutlined, SendOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Form, Input, Space, Tag, Typography } from 'antd'
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { useQuestionStore } from '../stores/questionStore'

type NewQuestionValues = {
  title: string
  body: string
  tags?: string
}

export function NewQuestionPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAuthStore((state) => state.user)
  const addQuestion = useQuestionStore((state) => state.addQuestion)
  const [submitted, setSubmitted] = useState(false)

  const onFinish = (values: NewQuestionValues) => {
    const tags = (values.tags ?? '')
      .split(/[,，\s]+/)
      .map((tag) => tag.trim())
      .filter(Boolean)
      .slice(0, 5)
    const question = addQuestion({ title: values.title, body: values.body, tags }, user?.displayName ?? '校园用户')
    queryClient.setQueryData(['questions'], useQuestionStore.getState().questions)
    queryClient.setQueryData(['questions', question.id], question)
    setSubmitted(true)
    navigate(`/questions/${question.id}`)
  }

  return (
    <div className="form-page">
      <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/questions')}>返回问题广场</Button>
      <Card className="question-form-card" bordered={false}>
        <Typography.Text className="eyebrow">ASK THE COMMUNITY</Typography.Text>
        <Typography.Title level={2}>发布一个新问题</Typography.Title>
        <Typography.Paragraph type="secondary">描述清楚你遇到的场景，其他同学会更容易给出有效答案。</Typography.Paragraph>
        {submitted ? <Alert message="问题已发布" type="success" showIcon /> : null}
        <Form<NewQuestionValues> layout="vertical" size="large" onFinish={onFinish} requiredMark={false}>
          <Form.Item label="标题" name="title" rules={[{ required: true, min: 8, message: '标题至少需要 8 个字符' }]}>
            <Input placeholder="例如：如何为 React 项目设计登录状态？" showCount maxLength={120} />
          </Form.Item>
          <Form.Item label="问题描述" name="body" rules={[{ required: true, min: 20, message: '请补充至少 20 个字符的描述' }]}>
            <Input.TextArea placeholder="补充背景、已尝试的方法和具体报错..." autoSize={{ minRows: 7, maxRows: 14 }} showCount maxLength={5000} />
          </Form.Item>
          <Form.Item label="标签（可选，最多 5 个）" name="tags" extra="多个标签用空格或逗号分隔">
            <Input placeholder="React 前端 软件工程" />
          </Form.Item>
          <Space>
            <Button onClick={() => navigate('/questions')}>取消</Button>
            <Button type="primary" htmlType="submit" icon={<SendOutlined />}>发布问题</Button>
          </Space>
        </Form>
        <div className="form-tip"><Tag color="blue">演示模式</Tag> 发布内容仅保存在当前浏览器，接入后端接口后会同步到团队环境。</div>
      </Card>
    </div>
  )
}
