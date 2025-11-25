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

if (!process.env.COLLAB_JWT_SECRET && !process.env.HOCUSPOCUS_SECRET) {
  log.warn('COLLAB_JWT_SECRET is not set, using an insecure fallback. Do not use this in production!')
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

      if (yText.length > 0) {
        yText.delete(0, yText.length)
        log.info({ document: documentName }, 'Cleared existing realtime doc before bootstrap')
      }

      yText.insert(0, latexSource)
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
  async onChange({ documentName, update }) {
    log.debug({ document: documentName, updateLength: update?.length ?? 0 }, 'Document update received')
  },
  async onDestroy() {
    log.info('Collaboration server shutting down')
    await redisExtension.destroy?.()
  },
})

server.listen()

log.info({ port }, 'Hocuspocus collaboration server ready')
