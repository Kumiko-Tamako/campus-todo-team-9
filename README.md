# CampusOverflow


> 校园问答知识社区 —— 沉淀教学答疑、量化学习参与


## 项目定位


面向高校场景的问答知识社区：学生按课程与标签提问、答疑，讨论沉淀为可复用的教学资产；声誉体系量化学习参与度，为过程性评价提供依据。


《软件工程》课程实践项目，按 DDD 方法论自主设计与实现，不参考任何开源项目代码。


## 技术栈


| 层次 | 选型 |
|:---|:---|
| 语言 | Python 3.12+ |
| Web 框架 | FastAPI + Uvicorn |
| ORM / 迁移 | SQLAlchemy 2.0（async）+ Alembic |
| 数据库 | PostgreSQL 16 |
| 缓存 / Broker | Redis 7 |
| 数据校验 | Pydantic v2 |
| 异步任务 | Celery |
| 测试 | pytest |
| 代码质量 | ruff + mypy --strict |
| CI | GitHub Actions |
| 部署 | Docker Compose |
| 前端 | React 18 + TypeScript 5 |


## 架构决策


| 决策 | 说明 |
|:---|:---|
| 限界上下文纵切 | 按 5 个子域分包：identity / qa / course / reputation / discovery，每个上下文内再分 domain / application / infrastructure / interfaces |
当前版本：v1.0.0（开发中）
