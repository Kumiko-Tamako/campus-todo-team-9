import { create } from 'zustand'

export type Question = {
  id: string
  title: string
  body: string
  author: string
  createdAt: string
  tags: string[]
  votes: number
  views: number
}

type NewQuestion = Pick<Question, 'title' | 'body' | 'tags'>

type QuestionState = {
  questions: Question[]
  addQuestion: (question: NewQuestion, author: string) => Question
}

const initialQuestions: Question[] = [
  {
    id: 'q-1',
    title: '软件工程课程的迭代计划应该如何拆分？',
    body: '我们准备开始第一个 Sprint，想了解如何把用户故事拆成适合团队并行开发的任务。',
    author: '林同学',
    createdAt: '2026-09-12T09:30:00.000Z',
    tags: ['软件工程', '敏捷开发'],
    votes: 12,
    views: 86,
  },
  {
    id: 'q-2',
    title: 'React 中应该在哪里管理登录状态？',
    body: '项目使用 React Router 和 Ant Design，想请教登录信息放在什么位置更容易维护。',
    author: '周同学',
    createdAt: '2026-09-11T14:10:00.000Z',
    tags: ['React', '前端'],
    votes: 8,
    views: 54,
  },
]

export const useQuestionStore = create<QuestionState>((set) => ({
  questions: initialQuestions,
  addQuestion: (question, author) => {
    const created: Question = {
      ...question,
      id: `q-${Date.now()}`,
      author,
      createdAt: new Date().toISOString(),
      votes: 0,
      views: 0,
    }
    set((state) => ({ questions: [created, ...state.questions] }))
    return created
  },
}))
