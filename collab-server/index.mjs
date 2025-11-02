import { Server } from '@hocuspocus/server'
import { Logger } from '@hocuspocus/extension-logger'
import { Redis } from '@hocuspocus/extension-redis'
import jwt from 'jsonwebtoken'
import pino from 'pino'
import * as Y from 'yjs'

const log = pino({ level: process.env.LOG_LEVEL ?? 'info' })

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
    if (document.getText('main').length === 0) {
      const yText = document.getText('main')
      yText.insert(0, '')
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
