/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
// Use backend service name in Docker, localhost for native dev
const API_TARGET = process.env.VITE_API_TARGET || 'http://backend:8000'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      'y-codemirror.next': path.resolve(__dirname, 'node_modules/y-codemirror.next/src/index.js'),
    },
  },
  server: {
    port: 3000,
    host: true,
    allowedHosts: ['scholarhub.space', 'localhost'],
    proxy: {
      '/api': {
        target: API_TARGET,
        ws: true,
        changeOrigin: true,
        secure: false,
        timeout: 120000, // 2 minutes timeout for long-running operations like discovery
        configure: (proxy, _options) => {
          proxy.on('error', (err, _req, _res) => {
            console.log('proxy error', err);
          });
          proxy.on('proxyReq', (proxyReq, req, _res) => {
            console.log('Sending Request to the Target:', req.method, req.url);
          });
          proxy.on('proxyRes', (proxyRes, req, _res) => {
            console.log('Received Response from the Target:', proxyRes.statusCode, req.url);
          });
        },
      },
      '/onlyoffice': {
        target: API_TARGET,
        changeOrigin: true,
        secure: false,
      },
      '/health': {
        target: API_TARGET,
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
})
