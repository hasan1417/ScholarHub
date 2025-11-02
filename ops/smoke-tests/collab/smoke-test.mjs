import { HocuspocusProvider } from '@hocuspocus/provider'
import jwt from 'jsonwebtoken'
import * as Y from 'yjs'

const serverUrl = process.env.COLLAB_WS_URL ?? 'ws://localhost:3001'
const paperId = process.env.PAPER_ID ?? 'collab-smoke-paper'
const userId = process.env.USER_ID ?? 'smoke-tester'
const displayName = process.env.DISPLAY_NAME ?? 'Smoke Tester'
const secret = process.env.COLLAB_JWT_SECRET ?? 'development-only-secret'

const token = jwt.sign(
  {
    paperId,
    userId,
    displayName,
    roles: ['tester'],
  },
  secret,
  { expiresIn: '5m' },
)

const provider = new HocuspocusProvider({
  url: serverUrl,
  name: paperId,
  token,
  document: new Y.Doc(),
})

const timeoutMs = Number.parseInt(process.env.SMOKE_TIMEOUT ?? '5000', 10)

const gracefulExit = (code) => {
  provider.destroy()
  setTimeout(() => process.exit(code), 100)
}

provider.on('status', (event) => {
  console.log(`[status] ${event.status}`)
  if (event.status === 'disconnected') {
    console.warn('Provider disconnected before sync completed')
  }
})

provider.on('synced', (isSynced) => {
  if (isSynced) {
    console.log('Synced with collaboration server ✓')
    gracefulExit(0)
  }
})

provider.on('connection-error', (event) => {
  console.error('Connection error', event)
  gracefulExit(1)
})

provider.on('authenticationFailed', () => {
  console.error('Authentication failed – check COLLAB_JWT_SECRET')
  gracefulExit(1)
})

setTimeout(() => {
  console.error('Smoke test timed out before sync')
  gracefulExit(1)
}, timeoutMs)
