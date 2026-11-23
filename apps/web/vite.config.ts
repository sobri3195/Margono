import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const host = '127.0.0.1';
const proxy = { '/api': `http://${host}:8000` };

export default defineConfig({
  plugins: [react()],
  server: { host, proxy },
  preview: { host, proxy },
});
