import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

type OpenApiDocument = {
  paths: Record<string, Record<string, unknown>>
  components?: {
    schemas?: Record<string, {
      required?: string[]
      properties?: Record<string, unknown>
    }>
  }
}

const document = JSON.parse(readFileSync(resolve(process.cwd(), '..', 'openapi.json'), 'utf8')) as OpenApiDocument

describe('checked-in API contract', () => {
  it('keeps the frontend question and auth operations available', () => {
    expect(document.paths['/api/v1/auth/login']?.post).toBeDefined()
    expect(document.paths['/api/v1/auth/me']?.get).toBeDefined()
    expect(document.paths['/api/v1/questions']?.get).toBeDefined()
    expect(document.paths['/api/v1/questions']?.post).toBeDefined()
    expect(document.paths['/api/v1/questions/{question_id}']?.get).toBeDefined()
  })

  it('keeps question status and answer fields required by the UI', () => {
    const schemas = document.components?.schemas ?? {}
    const question = schemas.QuestionResponse
    const questionListItem = schemas.QuestionListItem
    const detail = schemas.QuestionDetailResponse
    const answer = schemas.AnswerResponse

    expect(question?.required).toEqual(expect.arrayContaining(['id', 'title', 'body', 'status']))
    expect(question?.properties?.tags).toBeDefined()
    expect(questionListItem?.required).toEqual(expect.arrayContaining(['id', 'title', 'status']))
    expect(questionListItem?.properties?.tags).toBeDefined()
    expect(detail?.required).toEqual(expect.arrayContaining(['accepted_answer_id', 'status']))
    expect(detail?.properties?.answers).toBeDefined()
    expect(detail?.properties?.comments).toBeDefined()
    expect(answer?.required).toEqual(expect.arrayContaining(['id', 'body', 'author_id', 'votes', 'is_accepted']))
  })
})
