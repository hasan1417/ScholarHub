import { collabConfig } from '../config/collab'

interface CollabTokenResponse {
  token: string
  expires_in: number
  ws_url?: string
}

export async function fetchCollabToken(paperId: string, abortSignal?: AbortSignal): Promise<CollabTokenResponse> {
  const url = new URL(collabConfig.tokenEndpoint, collabConfig.apiBaseUrl)
  url.searchParams.set('paper_id', paperId)

  const accessToken = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
  if (!accessToken) {
    throw new Error('Missing access token for collaboration request')
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${accessToken}`,
  }

  const response = await fetch(url.toString(), {
    method: 'POST',
    credentials: 'include',
    headers,
    signal: abortSignal,
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch collaboration token (${response.status})`)
  }

  return response.json()
}
