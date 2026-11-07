import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  // GitHub Pages serves the app under /<repo>/; local dev and preview stay at /.
  base: process.env.VITE_BASE ?? '/',
  plugins: [react(), tailwindcss()],
  server: { proxy: { '/api': process.env.CLAVION_API_URL ?? 'http://localhost:8000' } },
})
