import { describe, it, expect, beforeEach } from 'vitest'
import { buildApiUrl, buildAuthHeaders } from '../services/api'

describe('buildApiUrl', () => {
  it('appends path to API base', () => {
    const url = buildApiUrl('/items/123')
    expect(url).toContain('/api/v1/items/123')
  })

  it('adds leading slash if missing', () => {
    const url = buildApiUrl('items/123')
    expect(url).toContain('/api/v1/items/123')
  })

  it('does not duplicate slashes', () => {
    const url = buildApiUrl('/test')
    expect(url).not.toContain('//test')
  })
})

describe('buildAuthHeaders', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('returns Content-Type header', () => {
    const headers = buildAuthHeaders()
    expect(headers['Content-Type']).toBe('application/json')
  })

  it('includes Authorization when token exists', () => {
    localStorage.setItem('access_token', 'test-token-123')
    const headers = buildAuthHeaders()
    expect(headers.Authorization).toBe('Bearer test-token-123')
  })

  it('omits Authorization when no token', () => {
    const headers = buildAuthHeaders()
    expect(headers.Authorization).toBeUndefined()
  })
})
