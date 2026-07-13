import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // dev server 直連本機 compose 環境的 nginx(BFF 掛在 /api)
    proxy: {
      '/api': 'http://localhost:8080',
    },
  },
})
