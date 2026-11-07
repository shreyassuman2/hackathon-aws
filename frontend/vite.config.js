import { defineConfig } from 'vite'

// Config comes from VITE_* env vars (see frontend/.env.example):
//   VITE_RUNWAY_API_URL   default http://localhost:8000
//   VITE_RUNWAY_TOKEN     must match RUNWAY_API_TOKEN on the API, if set
export default defineConfig({
  server: { port: 3000, open: true },
})
