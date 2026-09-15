import { ArrowLeftOutlined, SendOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Form, Input, Space, Typography } from 'antd'
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { questionsApi, type QuestionDetail } from '../api/questions'
import { getApiErrorMessage } from '../api/errors'

type NewQuestionValues = {
  title: string
  body: string
}

export function NewQuestionPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [submitted, setSubmitted] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const onFinish = async (values: NewQuestionValues) => {
    setErrorMessage(null)
    setIsSubmitting(true)
    try {
      const question = await questionsApi.create({ title: values.title, body: values.body })
      queryClient.invalidateQueries({ queryKey: ['questions'] })
      queryClient.setQueryData<QuestionDetail>(['questions', question.id], { ...question, tags: [], answers: [] })
      setSubmitted(true)
      navigate(`/questions/${question.id}`)
    } catch (error) {
      setErrorMessage(getApiErrorMessage(error, '发布失败，请稍后重试'))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="form-page">
      <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/questions')}>返回问题广场</Button>
      <Card className="question-form-card" bordered={false}>
        <Typography.Text className="eyebrow">ASK THE COMMUNITY</Typography.Text>
        <Typography.Title level={2}>发布一个新问题</Typography.Title>
        <Typography.Paragraph type="secondary">描述清楚你遇到的场景，其他同学会更容易给出有效答案。</Typography.Paragraph>
        {submitted ? <Alert message="问题已发布" type="success" showIcon /> : null}
        {errorMessage ? <Alert message={errorMessage} type="error" showIcon /> : null}
        <Form<NewQuestionValues> layout="vertical" size="large" onFinish={onFinish} requiredMark={false}>
          <Form.Item label="标题" name="title" rules={[{ required: true, min: 8, message: '标题至少需要 8 个字符' }]}>
            <Input placeholder="例如：如何为 React 项目设计登录状态？" showCount maxLength={120} />
          </Form.Item>
          <Form.Item label="问题描述" name="body" rules={[{ required: true, min: 20, message: '请补充至少 20 个字符的描述' }]}>
            <Input.TextArea placeholder="补充背景、已尝试的方法和具体报错..." autoSize={{ minRows: 7, maxRows: 14 }} showCount maxLength={5000} />
          </Form.Item>
          <Space>
            <Button onClick={() => navigate('/questions')}>取消</Button>
            <Button type="primary" htmlType="submit" icon={<SendOutlined />} loading={isSubmitting}>发布问题</Button>
          </Space>
        </Form>
        <div className="form-tip">发布内容会同步到团队服务。</div>
      </Card>
    </div>
  )
}
