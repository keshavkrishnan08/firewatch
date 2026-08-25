import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// FIREWATCH COP dev server.
// The app fetches `${API}/api/event/:id/cop` and camera frames from `${API}/outputs/...`.
// In dev, API is same-origin ('') and these paths are proxied to the FIREWATCH backend.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/outputs': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 2500,
  },
});
