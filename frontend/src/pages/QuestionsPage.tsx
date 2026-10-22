import { PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { Button, Empty, Input, List, Pagination, Select, Skeleton, Space, Tag, Typography } from 'antd'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuestions } from '../hooks/useQuestions'
import type { QuestionSort } from '../api/questions'

export function QuestionsPage() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState<QuestionSort>('latest')
  const { data, isLoading, isError } = useQuestions({ page, pageSize: 10, sort })
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
        <Space wrap>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索当前页标题"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <Select
            aria-label="问题排序"
            value={sort}
            options={[{ value: 'latest', label: '最新发布' }, { value: 'votes', label: '票数优先' }]}
            onChange={(value: QuestionSort) => { setSort(value); setPage(1) }}
          />
        </Space>
        <Typography.Text type="secondary">共 {data?.total ?? 0} 个问题</Typography.Text>
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
              {question.tags.length ? <Space wrap className="tag-row">{question.tags.map((tag) => <Tag color="blue" key={tag}>{tag}</Tag>)}</Space> : null}
              <Typography.Text className="question-meta" type="secondary">发布时间：{new Date(question.created_at).toLocaleDateString('zh-CN')}</Typography.Text>
            </List.Item>
          )}
        />
      ) : (
        <Empty description={search ? '当前页没有匹配的问题' : '还没有问题，来发布第一个吧'}>
          {!search && <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/questions/new')}>发布问题</Button>}
        </Empty>
      )}
      {data && data.total_pages > 1 ? <Pagination
        current={data.page}
        pageSize={data.page_size}
        total={data.total}
        showSizeChanger={false}
        onChange={(nextPage) => { setPage(nextPage); window.scrollTo({ top: 0, behavior: 'smooth' }) }}
      /> : null}
    </div>
  )
}
