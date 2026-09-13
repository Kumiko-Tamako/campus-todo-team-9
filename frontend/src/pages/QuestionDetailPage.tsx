import { ArrowLeftOutlined, EyeOutlined, LikeOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Empty, Space, Tag, Typography } from 'antd'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuestion } from '../hooks/useQuestions'

export function QuestionDetailPage() {
  const { questionId } = useParams<{ questionId: string }>()
  const navigate = useNavigate()
  const { data: question, isLoading, isError } = useQuestion(questionId)

  if (isLoading) return <Card loading bordered={false} />
  if (isError || !question) {
    return <Empty description="找不到这个问题"><Button onClick={() => navigate('/questions')}>返回问题广场</Button></Empty>
  }

  return (
    <div className="detail-page">
      <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/questions')}>返回问题广场</Button>
      <Card className="detail-card" bordered={false}>
        <Space wrap className="tag-row">{question.tags.map((tag) => <Tag color="blue" key={tag}>{tag}</Tag>)}</Space>
        <Typography.Title level={1}>{question.title}</Typography.Title>
        <Typography.Text type="secondary">{question.author} 发布于 {new Date(question.createdAt).toLocaleString('zh-CN')}</Typography.Text>
        <Typography.Paragraph className="detail-body">{question.body}</Typography.Paragraph>
        <Space className="detail-stats">
          <Typography.Text type="secondary"><LikeOutlined /> {question.votes} 赞</Typography.Text>
          <Typography.Text type="secondary"><EyeOutlined /> {question.views} 浏览</Typography.Text>
        </Space>
      </Card>
      <Alert message="回答功能将在下一阶段接入" description="当前阶段先完成提问、列表和详情的完整浏览流程。" type="info" showIcon />
      <Link className="back-link" to="/questions">继续浏览其他问题</Link>
    </div>
  )
}
