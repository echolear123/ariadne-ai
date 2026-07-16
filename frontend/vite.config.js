import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:7860',
      '/uploads': 'http://localhost:7860'
    }
  },
  build: {
    outDir: '../static',
    emptyOutDir: true
  }
})
