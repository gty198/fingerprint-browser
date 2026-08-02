import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // 开发时把 /api 代理到控制层,避免跨域
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
