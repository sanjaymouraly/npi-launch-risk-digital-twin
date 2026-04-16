import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  define: {
    // The partial Plotly bundles are CommonJS and reference `global`.
    global: 'globalThis',
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1600,
    rollupOptions: {
      output: {
        manualChunks: {
          plotly: ['plotly.js/lib/core', 'plotly.js/lib/bar', 'plotly.js/lib/scatter'],
          react: ['react', 'react-dom', 'react-router-dom'],
        },
      },
    },
  },
})
