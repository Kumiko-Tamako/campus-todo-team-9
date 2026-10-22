import { TagOutlined } from '@ant-design/icons'
import { Card, Empty, Skeleton, Space, Tag, Typography } from 'antd'
import { useTags } from '../hooks/useQuestions'

export function TagsPage() {
  const { data: tags, isLoading, isError } = useTags()
  return <div className="page-stack">
    <section className="page-intro"><div><Typography.Text className="eyebrow">COMMUNITY TAGS</Typography.Text><Typography.Title level={1}>标签目录</Typography.Title><Typography.Paragraph type="secondary">浏览社区正在使用的主题标签。</Typography.Paragraph></div></section>
    <Card bordered={false}>
      {isLoading ? <Skeleton active paragraph={{ rows: 3 }} /> : isError ? <Empty description="暂时无法加载标签" /> : tags?.length ? <Space wrap size={[12, 12]}>{tags.map((tag) => <Tag icon={<TagOutlined />} color="blue" key={tag}>{tag}</Tag>)}</Space> : <Empty description="还没有标签" />}
    </Card>
  </div>
}
