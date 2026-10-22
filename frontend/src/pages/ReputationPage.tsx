import { ArrowDownOutlined, ArrowUpOutlined } from '@ant-design/icons'
import { Card, Empty, Statistic, Table, Tag, Typography } from 'antd'
import { useAuthStore } from '../stores/authStore'
import { useReputation } from '../hooks/useReputation'

export function ReputationPage() {
  const user = useAuthStore((state) => state.user)
  const { data, isLoading, isError } = useReputation(user?.id)
  if (isLoading) return <Card loading bordered={false} />
  return <div className="page-stack">
    <section className="page-intro"><div><Typography.Text className="eyebrow">YOUR CONTRIBUTION</Typography.Text><Typography.Title level={1}>我的声誉</Typography.Title><Typography.Paragraph type="secondary">声誉流水由回答、投票和采纳事件异步结算。</Typography.Paragraph></div></section>
    {isError || !data ? <Empty description="暂时无法加载声誉，请稍后重试" /> : <>
      <Card bordered={false}><Statistic title="当前总声誉" value={data.total} /></Card>
      <Card title="变动流水" bordered={false}>
        {data.entries.length ? <Table rowKey="event_id" pagination={false} dataSource={data.entries} columns={[
          { title: '来源', dataIndex: 'source' },
          { title: '原因', dataIndex: 'reason' },
          { title: '变化', dataIndex: 'delta', render: (delta: number) => <Tag color={delta >= 0 ? 'success' : 'error'} icon={delta >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}>{delta > 0 ? `+${delta}` : delta}</Tag> },
          { title: '时间', dataIndex: 'occurred_at', render: (value: string) => new Date(value).toLocaleString('zh-CN') },
        ]} /> : <Empty description="暂时没有声誉流水" />}
      </Card>
    </>}
  </div>
}
