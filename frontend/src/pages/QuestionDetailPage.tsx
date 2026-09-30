import { ArrowDownOutlined, ArrowLeftOutlined, ArrowUpOutlined, CheckOutlined, SendOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Empty, Form, Input, List, Space, Tag, Typography } from 'antd'
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { getApiErrorMessage } from '../api/errors'
import { questionsApi } from '../api/questions'
import { useQuestion } from '../hooks/useQuestions'
import { useAuthStore } from '../stores/authStore'

function formatDate(value: string) {
  return new Date(value).toLocaleString('zh-CN')
}

function VoteButtons({ onVote, disabled }: { onVote: (direction: 'up' | 'down') => void; disabled?: boolean }) {
  return <Space.Compact direction="vertical">
    <Button aria-label="赞成" icon={<ArrowUpOutlined />} disabled={disabled} onClick={() => onVote('up')} />
    <Button aria-label="反对" icon={<ArrowDownOutlined />} disabled={disabled} onClick={() => onVote('down')} />
  </Space.Compact>
}

function CommentList({ comments }: { comments: { id: string; body: string; created_at: string }[] }) {
  if (!comments.length) return <Typography.Text type="secondary">暂无评论</Typography.Text>
  return <List size="small" dataSource={comments} renderItem={(comment) => <List.Item>
    <Typography.Text>{comment.body}</Typography.Text>
    <Typography.Text type="secondary">{formatDate(comment.created_at)}</Typography.Text>
  </List.Item>} />
}

export function QuestionDetailPage() {
  const { questionId } = useParams<{ questionId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAuthStore((state) => state.user)
  const { data: question, isLoading, isError } = useQuestion(questionId)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [answerBody, setAnswerBody] = useState('')
  const [commentBody, setCommentBody] = useState('')
  const [answerCommentBodies, setAnswerCommentBodies] = useState<Record<string, string>>({})
  const [isSubmitting, setIsSubmitting] = useState(false)

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['questions', questionId] })
  const runAction = async (action: () => Promise<unknown>) => {
    setErrorMessage(null)
    setIsSubmitting(true)
    try { await action(); await refresh() } catch (error) { setErrorMessage(getApiErrorMessage(error)) } finally { setIsSubmitting(false) }
  }

  if (isLoading) return <Card loading bordered={false} />
  if (isError || !question) {
    return <Empty description="找不到这个问题"><Button onClick={() => navigate('/questions')}>返回问题广场</Button></Empty>
  }

  const isQuestionAuthor = user?.id === question.author_id
  return <div className="detail-page">
      <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/questions')}>返回问题广场</Button>
      {errorMessage ? <Alert message={errorMessage} type="error" showIcon closable onClose={() => setErrorMessage(null)} /> : null}
      <Card className="detail-card" bordered={false}>
        {question.tags.length ? <Space wrap className="tag-row">{question.tags.map((tag) => <Tag color="blue" key={tag}>{tag}</Tag>)}</Space> : null}
        <Typography.Title level={1}>{question.title}</Typography.Title>
        <Typography.Text type="secondary">发布于 {formatDate(question.created_at)}</Typography.Text>
        <Typography.Paragraph className="detail-body">{question.body}</Typography.Paragraph>
        {user ? <Space className="detail-actions"><VoteButtons disabled={isSubmitting} onVote={(direction) => runAction(() => questionsApi.voteQuestion(question.id, direction))} /><Typography.Text type="secondary">问题净票数由服务端统计</Typography.Text></Space> : null}
      </Card>

      <Card title={`问题评论（${question.comments.length}）`} bordered={false}>
        <CommentList comments={question.comments} />
        {user ? <Space.Compact className="comment-form"><Input value={commentBody} placeholder="写下你的评论" onChange={(event) => setCommentBody(event.target.value)} /><Button icon={<SendOutlined />} disabled={!commentBody.trim() || isSubmitting} onClick={() => runAction(async () => { await questionsApi.commentQuestion(question.id, { body: commentBody.trim() }); setCommentBody('') })}>评论</Button></Space.Compact> : null}
      </Card>

      <section className="answers-section">
        <Typography.Title level={3}>回答（{question.answers.length}）</Typography.Title>
        {question.answers.length ? question.answers.map((answer) => <Card key={answer.id} className="answer-card" bordered={false}>
          <Space align="start"><VoteButtons disabled={isSubmitting} onVote={(direction) => runAction(() => questionsApi.voteAnswer(question.id, answer.id, direction))} />
            <div className="answer-content"><Typography.Paragraph className="answer-body">{answer.body}</Typography.Paragraph><Space wrap><Typography.Text type="secondary">{formatDate(answer.created_at)} · {answer.votes} 票</Typography.Text>{answer.is_accepted ? <Tag color="success" icon={<CheckOutlined />}>已采纳</Tag> : null}{isQuestionAuthor && !answer.is_accepted ? <Button size="small" icon={<CheckOutlined />} onClick={() => runAction(() => questionsApi.acceptAnswer(answer.id))}>采纳答案</Button> : null}</Space><CommentList comments={answer.comments} />{user ? <Space.Compact className="comment-form"><Input placeholder="评论这个回答" value={answerCommentBodies[answer.id] ?? ''} onChange={(event) => setAnswerCommentBodies((current) => ({ ...current, [answer.id]: event.target.value }))} /><Button disabled={!answerCommentBodies[answer.id]?.trim() || isSubmitting} onClick={() => runAction(async () => { await questionsApi.commentAnswer(answer.id, { body: answerCommentBodies[answer.id].trim() }); setAnswerCommentBodies((current) => ({ ...current, [answer.id]: '' })) })}>评论</Button></Space.Compact> : null}</div>
          </Space>
        </Card>) : <Empty description="暂无回答，成为第一个回答的人吧" />}
      </section>

      {user ? <Card title="发布回答" bordered={false}><Form onFinish={() => { if (answerBody.trim()) void runAction(async () => { await questionsApi.postAnswer(question.id, { body: answerBody.trim() }); setAnswerBody('') }) }}><Form.Item><Input.TextArea value={answerBody} onChange={(event) => setAnswerBody(event.target.value)} placeholder="分享你的解决方案或经验" autoSize={{ minRows: 5, maxRows: 12 }} maxLength={5000} showCount /></Form.Item><Button type="primary" htmlType="submit" icon={<SendOutlined />} loading={isSubmitting} disabled={!answerBody.trim()}>发布回答</Button></Form></Card> : <Alert message="登录后参与回答" description="你可以先浏览内容，登录后发布回答、评论和投票。" type="info" showIcon />}
    </div>
}
