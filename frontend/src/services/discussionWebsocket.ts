import { API_ROOT } from './api'

type Listener = (payload: any) => void

type ListenerMap = Map<string, Set<Listener>>

class DiscussionWebSocketService {
  private ws: WebSocket | null = null
  private projectId: string | null = null
  private channelId: string | null = null
  private listeners: ListenerMap = new Map()
  private isConnecting = false

  on(event: string, listener: Listener) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set())
    }
    this.listeners.get(event)!.add(listener)
  }

  off(event: string, listener: Listener) {
    const bucket = this.listeners.get(event)
    if (!bucket) return
    bucket.delete(listener)
    if (bucket.size === 0) {
      this.listeners.delete(event)
    }
  }

  private emit(event: string, payload: any) {
    const bucket = this.listeners.get(event)
    if (!bucket) return
    bucket.forEach((listener) => {
      try {
        listener(payload)
      } catch (error) {
        console.error('discussionWebsocket listener error', error)
      }
    })
  }

  private handleMessage(raw: string) {
    try {
      const parsed = JSON.parse(raw)
      if (!parsed || typeof parsed.type !== 'string') return
      this.emit(parsed.type, parsed)
    } catch (error) {
      console.error('Failed to parse discussion websocket payload', error)
    }
  }

  async connect(projectId: string, channelId: string, token: string) {
    if (this.isConnecting) return
    if (
      this.ws &&
      this.ws.readyState === WebSocket.OPEN &&
      this.projectId === projectId &&
      this.channelId === channelId
    ) {
      return
    }

    this.disconnect()

    this.isConnecting = true
    this.projectId = projectId
    this.channelId = channelId

    const tokenParam = encodeURIComponent(token || 'demo')
    const browserOrigin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3000'
    const derivedOrigin = API_ROOT || browserOrigin
    const wsPrimary = derivedOrigin.replace(/^http/, 'ws')
    const wsFallback = browserOrigin.replace(/^http/, 'ws')
    const path = `/api/v1/projects/${projectId}/discussion/channels/${channelId}/ws?token=${tokenParam}`
    const candidates = Array.from(new Set([
      `${wsPrimary}${path}`,
      `${wsFallback}${path}`,
      `ws://localhost:8000${path}`,
    ]))

    let resolved = false

    await new Promise<void>((resolve, reject) => {
      let attemptIndex = 0

      const tryConnect = () => {
        const url = candidates[attemptIndex]
        try {
          this.ws = new WebSocket(url)
        } catch (error) {
          nextAttempt(error instanceof Error ? error : new Error('WebSocket init failed'))
          return
        }

        this.ws.onopen = () => {
          resolved = true
          this.isConnecting = false
          resolve()
        }

        this.ws.onmessage = (event) => {
          if (typeof event.data === 'string') {
            this.handleMessage(event.data)
          }
        }

        this.ws.onerror = (event) => {
          this.emit('ws_error', { event })
          nextAttempt(new Error('WebSocket error'))
        }

        this.ws.onclose = (event) => {
          this.emit('ws_closed', { code: event.code, reason: event.reason })
          if (!resolved) {
            nextAttempt(new Error(`WebSocket closed: ${event.code}`))
          } else {
            this.cleanupSocket()
          }
        }
      }

      const nextAttempt = (error: Error) => {
        if (resolved) {
          return
        }

        if (attemptIndex < candidates.length - 1) {
          attemptIndex += 1
          tryConnect()
          return
        }

        this.cleanupSocket()
        this.isConnecting = false
        reject(error)
      }

      tryConnect()
    })
  }

  disconnect() {
    this.isConnecting = false
    if (this.ws) {
      this.ws.onopen = null
      this.ws.onclose = null
      this.ws.onerror = null
      this.ws.onmessage = null
      try {
        this.ws.close()
      } catch (error) {
        console.error('Error closing discussion websocket', error)
      }
    }
    this.cleanupSocket()
  }

  private cleanupSocket() {
    this.ws = null
  }

  getConnectionInfo() {
    return {
      projectId: this.projectId,
      channelId: this.channelId,
      connected: this.ws?.readyState === WebSocket.OPEN,
    }
  }
}

const discussionWebsocket = new DiscussionWebSocketService()

export default discussionWebsocket
