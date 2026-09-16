export function isStrongPassword(password: string | undefined): boolean {
  return password !== undefined && password.length >= 8 && /[A-Za-z]/.test(password) && /\d/.test(password)
}
