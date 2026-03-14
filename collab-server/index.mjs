import { createHash } from 'crypto'
import { Server } from '@hocuspocus/server'
import { Logger } from '@hocuspocus/extension-logger'
import { Redis } from '@hocuspocus/extension-redis'
import jwt from 'jsonwebtoken'
import pino from 'pino'
import * as Y from 'yjs'

const log = pino({ level: process.env.LOG_LEVEL ?? 'info' })
const backendBaseUrl = (process.env.BACKEND_BASE_URL || 'http://backend:8000').replace(/\/$/, '')
const bootstrapSecret = process.env.COLLAB_BOOTSTRAP_SECRET || process.env.COLLAB_JWT_SECRET || null

const port = Number.parseInt(process.env.PORT ?? '3001', 10)
const redisHost = process.env.REDIS_HOST ?? 'redis'
const redisPort = Number.parseInt(process.env.REDIS_PORT ?? '6379', 10)
const redisPassword = process.env.REDIS_PASSWORD
const jwtSecret = process.env.COLLAB_JWT_SECRET ?? process.env.HOCUSPOCUS_SECRET ?? 'development-only-secret'
const REDIS_ORIGIN = '__hocuspocus__redis__origin__'
const SNAPSHOT_INTERVAL_MS = 5 * 60 * 1000

const dirtyDocuments = new Map()
const lastSnapshotAt = new Map()
const lastSnapshotHash = new Map()
const snapshotInFlight = new Set()

let autoSnapshotTimer = null

if (!process.env.COLLAB_JWT_SECRET && !process.env.HOCUSPOCUS_SECRET) {
  log.warn('COLLAB_JWT_SECRET is not set, using an insecure fallback. Do not use this in production!')
}

function contentHash(text) {
  return createHash('sha256').update(text, 'utf8').digest('hex').slice(0, 16)
}

function encodeDocumentState(document) {
  return Buffer.from(Y.encodeStateAsUpdate(document)).toString('base64')
}

function writeJson(response, status, payload) {
  response.writeHead(status, { 'Content-Type': 'application/json' })
  response.end(JSON.stringify(payload))
}

function getCollabSecret(request) {
  const header = request.headers['x-collab-secret']
  return Array.isArray(header) ? header[0] : header
}

function isSnapshotDue(documentName, now = Date.now()) {
  const baseTime = lastSnapshotAt.get(documentName) ?? dirtyDocuments.get(documentName)
  return typeof baseTime === 'number' && now - baseTime >= SNAPSHOT_INTERVAL_MS
}

async function maybeCreateAutoSnapshot({ documentName, document, materializedText, reason }) {
  if (!bootstrapSecret || !dirtyDocuments.has(documentName)) {
    return false
  }

  if (!materializedText) {
    dirtyDocuments.delete(documentName)
    return false
  }

  if (snapshotInFlight.has(documentName)) {
    return false
  }

  const now = Date.now()
  if (!isSnapshotDue(documentName, now)) {
    return false
  }

  snapshotInFlight.add(documentName)

  try {
    const hash = contentHash(materializedText)
    if (lastSnapshotHash.get(documentName) === hash) {
      dirtyDocuments.delete(documentName)
      log.debug({ document: documentName, hash, reason }, 'Auto-snapshot skipped: content unchanged')
      return false
    }

    const response = await fetch(`${backendBaseUrl}/api/v1/papers/${documentName}/snapshots/auto`, {
      method: 'POST',
      headers: {
        'X-Collab-Secret': bootstrapSecret,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        yjs_state_base64: encodeDocumentState(document),
        materialized_text: materializedText,
        snapshot_type: 'auto',
      }),
    })

    if (!response.ok) {
      log.warn({ document: documentName, status: response.status, reason }, 'Auto-snapshot failed')
      return false
    }

    lastSnapshotHash.set(documentName, hash)
    lastSnapshotAt.set(documentName, now)
    dirtyDocuments.delete(documentName)
    log.debug({ document: documentName, hash, reason }, 'Auto-snapshot created')
    return true
  } catch (error) {
    log.error({ document: documentName, error, reason }, 'Auto-snapshot fetch failed')
    return false
  } finally {
    snapshotInFlight.delete(documentName)
  }
}

async function runAutoSnapshotPass(documents) {
  for (const [documentName, document] of documents.entries()) {
    if (!dirtyDocuments.has(documentName) || !isSnapshotDue(documentName) || document.saveMutex.isLocked()) {
      continue
    }

    const materializedText = document.getText('main').toString()
    await maybeCreateAutoSnapshot({
      documentName,
      document,
      materializedText,
      reason: 'timer',
    })
  }
}

const redisExtension = new Redis({
  host: redisHost,
  port: redisPort,
  ...(redisPassword ? { options: { password: redisPassword } } : {}),
})

const loggerExtension = new Logger({
  onMessageLogged: ({ level, message, context }) => {
    if (level === 'error') {
      log.error({ context }, message)
      return
    }
    if (level === 'warn') {
      log.warn({ context }, message)
      return
    }
    log.debug({ context }, message)
  },
})

const server = new Server({
  name: 'scholarhub-collab',
  port,
  extensions: [loggerExtension, redisExtension],
  async onAuthenticate(payload) {
    const headerToken = payload.requestHeaders?.authorization ?? payload.request?.headers?.authorization
    const token = payload.token ?? (headerToken ? headerToken.replace(/^Bearer\\s+/i, '') : undefined)
    if (!token) {
      throw new Error('Missing collaboration token')
    }

    let decoded
    try {
      decoded = jwt.verify(token, jwtSecret)
    } catch (error) {
      log.warn({ error }, 'Unable to verify JWT')
      throw new Error('Invalid collaboration token')
    }

    const { paperId, userId, displayName, color, roles } = decoded ?? {}
    if (!paperId || !userId) {
      throw new Error('Token missing paperId or userId')
    }

    payload.context ??= {}
    payload.context.user = {
      id: userId,
      name: displayName ?? 'Unknown user',
      color: color ?? '#3B82F6',
      roles: Array.isArray(roles) ? roles : [],
    }
    payload.context.paperId = paperId
    payload.documentName = paperId
  },
  async onLoadDocument({ documentName, document }) {
    const yText = document.getText('main')

    if (!bootstrapSecret) {
      log.warn({ document: documentName }, 'Skipping bootstrap: secret not configured')
      return
    }

    try {
      const response = await fetch(`${backendBaseUrl}/api/v1/collab/bootstrap/${documentName}`, {
        headers: {
          'X-Collab-Secret': bootstrapSecret,
          Accept: 'application/json',
        },
      })

      if (!response.ok) {
        log.warn({ document: documentName, status: response.status }, 'Bootstrap request failed')
        return
      }

      const payload = await response.json()
      const latexSource = typeof payload?.latex_source === 'string' ? payload.latex_source : ''

      log.info({ document: documentName, backendLength: latexSource.length, realtimeLength: yText.length }, 'Bootstrap payload received')

      if (!latexSource) {
        log.info({ document: documentName }, 'Bootstrap skipped: backend returned empty payload')
        return
      }

      // Use a Y.Doc transaction so delete+insert is atomic.
      // Without this, a concurrent client insert (from yCollab syncing
      // editor content) can interleave with our delete/insert and cause
      // the Yjs CRDT to merge both insertions — doubling the content.
      document.transact(() => {
        if (yText.length > 0) {
          yText.delete(0, yText.length)
          log.info({ document: documentName }, 'Cleared existing realtime doc before bootstrap')
        }
        yText.insert(0, latexSource)

        // Bootstrap extra .tex files (multi-file projects)
        const latexFiles = payload?.latex_files
        if (latexFiles && typeof latexFiles === 'object') {
          for (const [filename, content] of Object.entries(latexFiles)) {
            if (typeof content !== 'string') continue
            const fileText = document.getText(`file:${filename}`)
            if (fileText.length > 0) fileText.delete(0, fileText.length)
            fileText.insert(0, content)
          }
          log.info({ document: documentName, fileCount: Object.keys(latexFiles).length }, 'Bootstrapped extra files')
        }
      })
      log.info({ document: documentName, length: latexSource.length }, 'Bootstrapped document from backend')
    } catch (error) {
      log.error({ document: documentName, error }, 'Bootstrap fetch failed')
    } finally {
      if (yText.length === 0) {
        yText.insert(0, '')
      }
    }
  },
  async onConnect(data) {
    const userId = data.context?.user?.id
    log.info({ document: data.documentName, userId }, 'Client connected')
  },
  async onDisconnect(data) {
    const userId = data.context?.user?.id
    log.info({ document: data.documentName, userId }, 'Client disconnected')
  },
  async onChange(data) {
    const { documentName, update, transactionOrigin } = data
    if (transactionOrigin !== REDIS_ORIGIN) {
      dirtyDocuments.set(documentName, dirtyDocuments.get(documentName) ?? Date.now())
    }
    log.debug({ document: documentName, updateLength: update?.length ?? 0 }, 'Document changed')
  },
  async onStoreDocument({ documentName, document }) {
    const yText = document.getText('main')
    const materializedText = yText.toString()

    if (!bootstrapSecret) {
      return
    }

    // Safety guard: don't persist if Y.Text('main') contains sub-file content
    // (no \documentclass means it's not the real main.tex — likely a file-switch race)
    if (materializedText.length > 10 && !materializedText.includes('\\documentclass')) {
      log.warn({ document: documentName, length: materializedText.length }, 'Skipping persist: main Y.Text lacks \\documentclass (possible file-switch race)')
      return
    }

    try {
      const response = await fetch(`${backendBaseUrl}/api/v1/collab/persist/${documentName}`, {
        method: 'POST',
        headers: {
          'X-Collab-Secret': bootstrapSecret,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ latex_source: materializedText }),
      })

      if (!response.ok) {
        log.warn({ document: documentName, status: response.status }, 'Persist failed')
        return
      }

      log.debug({ document: documentName, length: materializedText.length }, 'Document persisted')

      await maybeCreateAutoSnapshot({
        documentName,
        document,
        materializedText,
        reason: 'store',
      })
    } catch (error) {
      log.error({ document: documentName, error }, 'Persist fetch failed')
    }
  },
  async afterUnloadDocument({ documentName }) {
    dirtyDocuments.delete(documentName)
  },
  async onRequest({ request, response, instance }) {
    const url = new URL(request.url ?? '/', `http://${request.headers.host ?? 'localhost'}`)
    const match = request.method === 'GET' ? url.pathname.match(/^\/documents\/([^/]+)\/state$/) : null

    if (match) {
      if (!bootstrapSecret) {
        writeJson(response, 503, { detail: 'Collaboration secret is not configured' })
        throw null
      }

      if (getCollabSecret(request) !== bootstrapSecret) {
        writeJson(response, 401, { detail: 'Unauthorized' })
        throw null
      }

      const paperId = decodeURIComponent(match[1])
      const document = instance.documents.get(paperId)

      if (!document) {
        writeJson(response, 404, { detail: 'Document is not loaded' })
        throw null
      }

      const materializedText = document.getText('main').toString()
      writeJson(response, 200, {
        yjs_state_base64: encodeDocumentState(document),
        materialized_text: materializedText,
        content_hash: contentHash(materializedText),
      })
      throw null
    }

    if (url.pathname.startsWith('/documents/') && url.pathname.endsWith('/state')) {
      response.writeHead(405, { Allow: 'GET' })
      response.end()
      throw null
    }
  },
  async onDestroy() {
    if (autoSnapshotTimer) {
      clearInterval(autoSnapshotTimer)
      autoSnapshotTimer = null
    }
    log.info('Collaboration server shutting down')
    await redisExtension.destroy?.()
  },
})

const hocuspocus = await server.listen()

autoSnapshotTimer = setInterval(() => {
  void runAutoSnapshotPass(hocuspocus.documents).catch((error) => {
    log.error({ error }, 'Auto-snapshot timer failed')
  })
}, SNAPSHOT_INTERVAL_MS)

autoSnapshotTimer.unref?.()

log.info({ port }, 'Hocuspocus collaboration server ready')
