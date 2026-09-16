import { describe, expect, it } from 'vitest'
import { isStrongPassword } from './registerValidation'

describe('isStrongPassword', () => {
  it('accepts passwords with at least eight characters, letters, and digits', () => {
    expect(isStrongPassword('campus123')).toBe(true)
  })

  it('rejects passwords without both letters and digits', () => {
    expect(isStrongPassword('12345678')).toBe(false)
    expect(isStrongPassword('campusxx')).toBe(false)
  })

  it('rejects passwords shorter than eight characters', () => {
    expect(isStrongPassword('camp1')).toBe(false)
  })
})
