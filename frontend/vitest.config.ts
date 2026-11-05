import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'json-summary'],
      include: [
        'src/api/auth.ts',
        'src/api/client.ts',
        'src/api/errors.ts',
        'src/api/questions.ts',
        'src/api/reputation.ts',
        'src/pages/registerValidation.ts',
      ],
      exclude: ['**/*.test.ts', '**/*.test.tsx', '**/*.d.ts'],
      thresholds: {
        statements: 70,
        branches: 65,
        functions: 70,
        lines: 70,
      },
    },
  },
})
