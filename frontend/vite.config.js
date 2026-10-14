import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite configuration. `host: true` makes the dev server listen on 0.0.0.0 so it
// is reachable from outside the Docker container.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    // HMR needs to know which host the browser uses in Docker.
    watch: { usePolling: true },
  },
})
