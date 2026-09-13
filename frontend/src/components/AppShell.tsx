import { LogoutOutlined, PlusOutlined, ReadOutlined } from '@ant-design/icons'
import { Button, Layout, Menu, Space, Tag, Typography } from 'antd'
import type { MenuProps } from 'antd'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'

const { Header, Content, Footer } = Layout

export function AppShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const { user, logout } = useAuthStore()

  const menuItems: MenuProps['items'] = [
    { key: '/questions', icon: <ReadOutlined />, label: <Link to="/questions">问题广场</Link> },
    ...(user
      ? [{ key: '/questions/new', icon: <PlusOutlined />, label: <Link to="/questions/new">发布问题</Link> }]
      : []),
  ]

  const handleLogout = () => {
    logout()
    navigate('/questions')
  }

  return (
    <Layout className="app-layout">
      <Header className="app-header">
        <div className="header-inner">
          <Link className="brand" to="/questions">
            <span className="brand-mark">C</span>
            <span>CampusOverflow</span>
          </Link>
          <Menu
            className="main-menu"
            mode="horizontal"
            selectedKeys={[location.pathname.startsWith('/questions') ? location.pathname : '/questions']}
            items={menuItems}
          />
          <Space className="header-actions">
            {user ? (
              <>
                <Tag color="blue">{user.displayName}</Tag>
                <Button type="text" icon={<LogoutOutlined />} onClick={handleLogout}>
                  退出
                </Button>
              </>
            ) : (
              <Button type="primary" onClick={() => navigate('/login')}>
                登录
              </Button>
            )}
          </Space>
        </div>
      </Header>
      <Content className="app-content">
        <div className="content-container">
          <Outlet />
        </div>
      </Content>
      <Footer className="app-footer">
        <Typography.Text type="secondary">CampusOverflow · 校园问答社区</Typography.Text>
      </Footer>
    </Layout>
  )
}
