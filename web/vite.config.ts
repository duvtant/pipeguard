import path from 'node:path'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// Dev: the browser talks to Vite, Vite proxies /api to the FastAPI container.
// Prod: nginx serves the build and proxies /api (see infra/nginx/default.conf).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, './src') } },
  server: {
    proxy: { '/api': { target: process.env.VITE_DEV_API ?? 'http://localhost:8000', changeOrigin: true } },
  },
})
