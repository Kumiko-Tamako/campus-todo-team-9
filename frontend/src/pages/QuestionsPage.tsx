import { PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { Button, Empty, Input, List, Skeleton, Typography } from 'antd'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuestions } from '../hooks/useQuestions'

export function QuestionsPage() {
  const navigate = useNavigate()
  const { data, isLoading, isError } = useQuestions()
  const [search, setSearch] = useState('')

  const filteredQuestions = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    if (!keyword) return data?.items ?? []
    return (data?.items ?? []).filter((question) => question.title.toLowerCase().includes(keyword))
  }, [data?.items, search])

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
          placeholder="搜索问题标题"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <Typography.Text type="secondary">共 {search.trim() ? filteredQuestions.length : data?.total ?? 0} 个问题</Typography.Text>
      </div>
      {isError ? <Empty description="暂时无法加载问题，请稍后再试" /> : isLoading ? (
        <List className="question-list" dataSource={[1, 2, 3]} renderItem={() => <List.Item><Skeleton active /></List.Item>} />
      ) : filteredQuestions.length ? (
        <List
          className="question-list"
          itemLayout="vertical"
          dataSource={filteredQuestions}
          renderItem={(question) => (
            <List.Item key={question.id}>
              <List.Item.Meta
                title={<Link className="question-title" to={`/questions/${question.id}`}>{question.title}</Link>}
              />
              <Typography.Text className="question-meta" type="secondary">发布时间：{new Date(question.created_at).toLocaleDateString('zh-CN')}</Typography.Text>
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
