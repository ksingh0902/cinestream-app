import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vite.dev/config/
export default defineConfig({
  resolve: {
    preserveSymlinks: true,
  },
  plugins: [react()],
  server: {
    port: 5173,
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/login': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/logout': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/proxy': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
});
