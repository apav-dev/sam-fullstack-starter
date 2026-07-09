import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Local dev: proxy API calls to uvicorn (scripts/local-dev.sh)
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
