export const isCollabEnabled = () => import.meta.env.VITE_COLLAB_ENABLED === 'true'

export const collabConfig = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
  tokenEndpoint: '/api/v1/collab/token',
  wsUrl: import.meta.env.VITE_COLLAB_WS ?? 'ws://localhost:3001',
}
