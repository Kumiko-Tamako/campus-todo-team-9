import { PlusOutlined, SearchOutlined, EyeOutlined, LikeOutlined } from '@ant-design/icons'
import { Button, Empty, Input, List, Skeleton, Space, Tag, Typography } from 'antd'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuestions } from '../hooks/useQuestions'

export function QuestionsPage() {
  const navigate = useNavigate()
  const { data: questions, isLoading, isError } = useQuestions()
  const [search, setSearch] = useState('')

  const filteredQuestions = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    if (!keyword) return questions ?? []
    return (questions ?? []).filter((question) => `${question.title} ${question.body} ${question.tags.join(' ')}`.toLowerCase().includes(keyword))
  }, [questions, search])

  return (
    <div className="page-stack">
      <section className="page-intro">
        <div>
          <Typography.Text className="eyebrow">COMMUNITY QUESTIONS</Typography.Text>
          <Typography.Title level={1}>问题广场</Typography.Title>
          <Typography.Paragraph type="secondary">从同学和老师的经验中找到下一步答案。</Typography.Paragraph>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/questions/new')}>
          发布问题
        </Button>
      </section>
      <div className="toolbar-row">
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="搜索问题、正文或标签"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <Typography.Text type="secondary">共 {filteredQuestions.length} 个问题</Typography.Text>
      </div>
      {isError ? <Empty description="暂时无法加载问题，请稍后再试" /> : null}
      {isLoading ? (
        <List className="question-list" dataSource={[1, 2, 3]} renderItem={() => <List.Item><Skeleton active /></List.Item>} />
      ) : filteredQuestions.length ? (
        <List
          className="question-list"
          itemLayout="vertical"
          dataSource={filteredQuestions}
          renderItem={(question) => (
            <List.Item
              key={question.id}
              actions={[
                <Space key="votes" size={4}><LikeOutlined /> {question.votes} 赞</Space>,
                <Space key="views" size={4}><EyeOutlined /> {question.views} 浏览</Space>,
              ]}
            >
              <List.Item.Meta
                title={<Link className="question-title" to={`/questions/${question.id}`}>{question.title}</Link>}
                description={<Space wrap>{question.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</Space>}
              />
              <Typography.Paragraph ellipsis={{ rows: 2 }} type="secondary">{question.body}</Typography.Paragraph>
              <Typography.Text className="question-meta" type="secondary">{question.author} · {new Date(question.createdAt).toLocaleDateString('zh-CN')}</Typography.Text>
            </List.Item>
          )}
        />
      ) : (
        <Empty description={search ? '没有匹配的问题' : '还没有问题，来发布第一个吧'}>
          {!search && <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/questions/new')}>发布问题</Button>}
        </Empty>
      )}
    </div>
  )
}
