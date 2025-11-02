import axios from 'axios'
import {
  ProjectCreateInput,
  ProjectDetail,
  ProjectListResponse,
  ProjectSummary,
  ResearchPaper,
  ResearchPaperCreate,
  ResearchPaperUpdate,
  ResearchPaperList,
  PaperMemberCreate,
  Document,

  DocumentList,
  DocumentChunk,
  Tag,
  TagCreate,
  AIArtifact,
  AIArtifactType,
  AIArtifactStatus,
  ProjectReferenceSuggestion,
  ProjectDiscoveryPreferences,
  ProjectDiscoverySettingsPayload,
  ProjectDiscoveryRunResponse,
  ProjectDiscoveryResultsResponse,
  ProjectDiscoveryCountResponse,
  ProjectDiscoveryResultItem,
  ProjectDiscoveryClearResponse,
  ProjectSyncSession,
  ProjectSyncMessage,
  ProjectNotification,
  SyncSessionTokenResponse,
  MeetingSummary,
  AISummaryResponse,
  AIRephraseResponse,
  AIDocumentAnalysis,
  AIChatResponse,
  AIStatusResponse,
  AIOutlineResponse,
  AIKeywordsResponse,
  User,
  DiscussionMessage,
  DiscussionThread,
  DiscussionMessageCreate,
  DiscussionMessageUpdate,
  DiscussionStats,
  DiscussionChannelSummary,
  DiscussionChannelCreate,
  DiscussionChannelUpdate,
  DiscussionChannelResource,
  DiscussionChannelResourceCreate,
  DiscussionTask,
  DiscussionTaskCreate,
  DiscussionTaskUpdate,
  DiscussionTaskStatus,
  DiscussionAssistantRequest,
  DiscussionAssistantResponse,
  DiscussionAssistantHistoryItem,
} from '../types'

const deduceRuntimeOrigin = () => {
  if (typeof window !== 'undefined' && window?.location) {
    return window.location.origin
  }
  return ''
}

const rawApiRoot = (typeof import.meta !== 'undefined' && (import.meta as any).env?.VITE_API_URL) || deduceRuntimeOrigin()
export const API_ROOT = rawApiRoot.replace(/\/$/, '')
export const API_BASE_URL = `${API_ROOT}/api/v1`.replace(/^\/api\//, '/api/')
export const buildApiUrl = (path: string) => {
  const sanitized = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE_URL}${sanitized}`
}

// Create axios instance with base configuration
const api = axios.create({
  baseURL: API_BASE_URL || '/api/v1',
  timeout: 60000, // Increased to 60s to handle slow APIs like Crossref
  headers: {
    'Content-Type': 'application/json',
  },
})

// Track if we're currently refreshing tokens to avoid concurrent refreshes
let isRefreshing = false
let failedQueue: Array<{
  resolve: (value?: any) => void
  reject: (error?: any) => void
}> = []

// Function to process the queue after token refresh
const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach(({ resolve, reject }) => {
    if (error) {
      reject(error)
    } else {
      resolve(token)
    }
  })
  
  failedQueue = []
}

// Function to refresh token
export const refreshAuthToken = async (): Promise<string> => {
  const refreshToken = localStorage.getItem('refresh_token')
  
  if (!refreshToken) {
    throw new Error('No refresh token available')
  }

  try {
    const response = await axios.post<{ access_token: string; refresh_token: string }>(buildApiUrl('/refresh'), {
      refresh_token: refreshToken
    })

    const { access_token, refresh_token: newRefreshToken } = response.data
    
    // Store new tokens
    localStorage.setItem('access_token', access_token)
    localStorage.setItem('refresh_token', newRefreshToken)
    
    return access_token
  } catch (error) {
    // Clear tokens if refresh fails
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user')
    throw error
  }
}

const base64Decode = (input: string): string => {
  if (typeof atob === 'function') {
    return atob(input)
  }

  if (typeof globalThis !== 'undefined') {
    const maybeBuffer = (globalThis as unknown as {
      Buffer?: { from: (data: string, encoding: string) => { toString: (encoding: string) => string } }
    }).Buffer
    if (maybeBuffer) {
      return maybeBuffer.from(input, 'base64').toString('utf-8')
    }
  }

  throw new Error('No base64 decoder available')
}

const decodeJwtPayload = (token: string): Record<string, unknown> => {
  const parts = token.split('.')
  if (parts.length < 2) {
    throw new Error('Invalid JWT structure')
  }

  const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
  const padding = (4 - (base64.length % 4 || 4)) % 4
  const padded = base64 + '='.repeat(padding)
  const decoded = base64Decode(padded)

  return JSON.parse(decoded)
}

// Proactive token refresh - refresh tokens 5 minutes before expiry
const setupTokenRefreshTimer = () => {
  const token = localStorage.getItem('access_token')
  if (!token) return

  if (!token.includes('.') || token.split('.').length < 3) {
    console.warn('Removing malformed access token from storage (token refresh timer)')
    localStorage.removeItem('access_token')
    return
  }

  try {
    const payload = decodeJwtPayload(token)
    const expValue = payload.exp
    const exp = typeof expValue === 'number' ? expValue : Number(expValue)
    if (!exp || Number.isNaN(exp)) {
      throw new Error('Missing exp claim')
    }

    const expiryTime = exp * 1000 // Convert to milliseconds
    const currentTime = Date.now()
    const timeUntilExpiry = expiryTime - currentTime
    const refreshTime = timeUntilExpiry - (5 * 60 * 1000) // 5 minutes before expiry

    if (refreshTime > 0) {
      setTimeout(async () => {
        try {
          await refreshAuthToken()
          console.log('Proactive token refresh successful')
          setupTokenRefreshTimer() // Set up next refresh
        } catch (error) {
          console.error('Proactive token refresh failed:', error)
        }
      }, refreshTime)
    }
  } catch (error) {
    console.error('Error setting up token refresh timer:', error)
    localStorage.removeItem('access_token')
  }
}

// Set up proactive refresh when page loads
if (typeof window !== 'undefined') {
  setupTokenRefreshTimer()
}

// Export the setup function for use after login
export { setupTokenRefreshTimer }

// Request interceptor to add auth token
api.interceptors.request.use(
  (config: any) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      // Don't replace headers object, just add Authorization
      if (!config.headers) {
        config.headers = {}
      }
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor to handle auth errors and auto-refresh tokens
type RetryableRequest = { _retry?: boolean; headers?: Record<string, unknown> } & Record<string, any>

api.interceptors.response.use(
  (response) => {
    return response
  },
  async (error) => {
    const originalRequest = (error?.config || {}) as RetryableRequest
    
    if (error?.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        // If already refreshing, queue this request
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        }).then(token => {
          if (token) {
            originalRequest.headers = {
              ...(originalRequest.headers ?? {}),
              Authorization: `Bearer ${token}`,
            }
          }
          return api(originalRequest as any)
        }).catch(err => {
          return Promise.reject(err)
        })
      }

      originalRequest._retry = true
      isRefreshing = true

      try {
        const newToken = await refreshAuthToken()
        
        // Update the authorization header
        ;(api.defaults.headers.common as Record<string, string>)['Authorization'] = `Bearer ${newToken}`
        originalRequest.headers = {
          ...(originalRequest.headers ?? {}),
          Authorization: `Bearer ${newToken}`,
        }
        
        // Process queued requests
        processQueue(null, newToken)
        
        // Retry the original request
        return api(originalRequest as any)
      } catch (refreshError) {
        // Process queued requests with error
        processQueue(refreshError, null)
        
        // Redirect to login
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        localStorage.removeItem('user')
        window.location.href = '/login'
        
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }
    
    return Promise.reject(error)
  }
)

// Auth API endpoints
export const authAPI = {
  register: (userData: {
    email: string
    password: string
    first_name?: string
    last_name?: string
  }) => api.post('/register', userData),

  login: (credentials: { email: string; password: string }) => {
    // Send as JSON with email and password
    return api.post<{ access_token: string; refresh_token: string }>('/login', {
      email: credentials.email,
      password: credentials.password
    }, {
      headers: {
        'Content-Type': 'application/json',
      },
    })
  },

  refresh: (refreshToken: string) => {
    return api.post<{ access_token: string; refresh_token: string }>('/refresh', {
      refresh_token: refreshToken
    })
  },

  getCurrentUser: () => api.get<User>('/me'),

  requestPasswordReset: (email: string) =>
    api.post('/forgot-password', { email }),
}

// Users API endpoints
export const usersAPI = {
  getUsers: () => api.get('/users'),
  getUser: (id: string) => api.get(`/users/${id}`),
  updateUser: (id: string, userData: any) => api.put(`/users/${id}`, userData),
  changePassword: (passwordData: { current_password: string; new_password: string }) =>
    api.post('/change-password', passwordData),
  lookupByEmail: (email: string) =>
    api.get<{ id?: string; user_id?: string; userId?: string }>(`/users/lookup-by-email`, { params: { email } }),
}

// Projects API endpoints
export const projectsAPI = {
  list: ({ skip = 0, limit = 50 }: { skip?: number; limit?: number } = {}) =>
    api.get<ProjectListResponse>('/projects/', { params: { skip, limit } }),

  create: (projectData: ProjectCreateInput) =>
    api.post<ProjectSummary>('/projects/', projectData),

  get: (projectId: string) => api.get<ProjectDetail>(`/projects/${projectId}`),

  update: (projectId: string, projectData: Partial<ProjectCreateInput>) =>
    api.put<ProjectSummary>(`/projects/${projectId}`, projectData),

  delete: (projectId: string) => api.delete(`/projects/${projectId}`),

  addMember: (projectId: string, payload: { user_id: string; role: string }) =>
    api.post(`/projects/${projectId}/members`, payload),

  updateMember: (projectId: string, memberId: string, payload: { role: string }) =>
    api.patch(`/projects/${projectId}/members/${memberId}`, payload),

  removeMember: (projectId: string, memberId: string) =>
    api.delete(`/projects/${projectId}/members/${memberId}`),

  listPendingInvitations: () =>
    api.get<{ invitations: Array<{ project_id: string; project_title: string; member_id: string; role: string; invited_at?: string | null; invited_by?: string | null }> }>(
      '/projects/pending/invitations'
    ),

  acceptInvitation: (projectId: string, memberId: string) =>
    api.post(`/projects/${projectId}/members/${memberId}/accept`, null),

  declineInvitation: (projectId: string, memberId: string) =>
    api.post(`/projects/${projectId}/members/${memberId}/decline`, null),
}

export const projectReferencesAPI = {
  listSuggestions: (projectId: string) =>
    api.get<{ project_id: string; suggestions: ProjectReferenceSuggestion[] }>(
      `/projects/${projectId}/references/suggestions`
    ),
  list: (projectId: string, params?: { status?: string }) =>
    api.get<{ project_id: string; references: ProjectReferenceSuggestion[] }>(
      `/projects/${projectId}/references`,
      { params: params?.status ? { status: params.status } : undefined }
    ),
  refreshSuggestions: (projectId: string) =>
    api.post<{ project_id: string; created: number; skipped: number }>(
      `/projects/${projectId}/references/suggestions/refresh`
    ),
  createSuggestion: (projectId: string, referenceId: string, confidence?: number) =>
    api.post<{ id: string; status: string }>(
      `/projects/${projectId}/references/suggestions`,
      null,
      {
        params: {
          reference_id: referenceId,
          confidence,
        },
      }
    ),
  approveSuggestion: (projectId: string, suggestionId: string, paperId?: string) =>
    api.post(
      `/projects/${projectId}/references/${suggestionId}/approve`,
      null,
      { params: paperId ? { paper_id: paperId } : undefined }
    ),
  rejectSuggestion: (projectId: string, suggestionId: string) =>
    api.post(`/projects/${projectId}/references/${suggestionId}/reject`, null),
  attachToPaper: (projectId: string, projectReferenceId: string, paperId: string) =>
    api.post(`/projects/${projectId}/references/${projectReferenceId}/attach`, {
      paper_id: paperId,
    }),
  detachFromPaper: (projectId: string, projectReferenceId: string, paperId: string) =>
    api.delete(`/projects/${projectId}/references/${projectReferenceId}/papers/${paperId}`),
  remove: (projectId: string, projectReferenceId: string) =>
    api.delete(`/projects/${projectId}/references/${projectReferenceId}`),
  listPaperReferences: (projectId: string, paperId: string) =>
    api.get<{ project_id: string; paper_id: string; references: any[] }>(
      `/projects/${projectId}/papers/${paperId}/references`
    ),
}

export const projectAIAPI = {
  listArtifacts: (
    projectId: string,
    params?: { status?: AIArtifactStatus; paperId?: string }
  ) =>
    api.get<{ project_id: string; artifacts: AIArtifact[] }>(
      `/projects/${projectId}/ai/artifacts`,
      {
        params: {
          status_filter: params?.status,
          paper_id: params?.paperId,
        },
      }
    ),
  generateArtifact: (
    projectId: string,
    payload: { type: AIArtifactType; paper_id?: string; focus?: string }
  ) => api.post(`/projects/${projectId}/ai/artifacts/generate`, payload),
}

export const projectDiscoveryAPI = {
  getSettings: (projectId: string) =>
    api.get<ProjectDiscoveryPreferences>(`/projects/${projectId}/discovery/settings`),
  updateSettings: (projectId: string, payload: ProjectDiscoverySettingsPayload) =>
    api.put<ProjectDiscoveryPreferences>(`/projects/${projectId}/discovery/settings`, payload),
  runDiscovery: (
    projectId: string,
    payload: {
      query?: string | null
      keywords?: string[] | null
      sources?: string[] | null
      max_results?: number | null
      relevance_threshold?: number | null
      auto_refresh_enabled?: boolean | null
      refresh_interval_hours?: number | null
    }
  ) =>
    api.post<ProjectDiscoveryRunResponse>(
      `/projects/${projectId}/discovery/run`,
      payload,
      { timeout: 120000 },
    ),
  listResults: (
    projectId: string,
    options?: { status?: string; skip?: number; limit?: number }
  ) =>
    api.get<ProjectDiscoveryResultsResponse>(
      `/projects/${projectId}/discovery/results`,
      {
        params: {
          status: options?.status,
          skip: options?.skip,
          limit: options?.limit,
        },
      }
    ),
  getPendingCount: (projectId: string) =>
    api.get<ProjectDiscoveryCountResponse>(`/projects/${projectId}/discovery/results/pending/count`),
  promoteResult: (projectId: string, resultId: string) =>
    api.post<ProjectDiscoveryResultItem>(
      `/projects/${projectId}/discovery/results/${resultId}/promote`,
      null,
    ),
  dismissResult: (projectId: string, resultId: string) =>
    api.post<ProjectDiscoveryResultItem>(
      `/projects/${projectId}/discovery/results/${resultId}/dismiss`,
      null,
    ),
  deleteResult: (projectId: string, resultId: string) =>
    api.delete<void>(
      `/projects/${projectId}/discovery/results/${resultId}`
    ),
  clearDismissedResults: (projectId: string) =>
    api.delete<ProjectDiscoveryClearResponse>(
      `/projects/${projectId}/discovery/results/dismissed`
    ),
  streamDiscovery: (projectId: string, payload: any) =>
    fetch(buildApiUrl(`/projects/${projectId}/discovery/stream`), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`
      },
      body: JSON.stringify(payload),
    }),
}

export const projectMeetingsAPI = {
  listMeetings: (projectId: string, options?: { status?: MeetingSummary['status'] }) =>
    api.get<{ project_id: string; meetings: MeetingSummary[] }>(
      `/projects/${projectId}/meetings`,
      {
        params: options?.status ? { status_filter: options.status } : undefined,
      }
    ),
  listSyncSessions: (projectId: string) =>
    api.get<{ project_id: string; sessions: ProjectSyncSession[] }>(
      `/projects/${projectId}/sync-sessions`
    ),
  createSyncSession: (
    projectId: string,
    payload: Partial<ProjectSyncSession>
  ) => api.post<ProjectSyncSession>(`/projects/${projectId}/sync-sessions`, payload),
  endSyncSession: (
    projectId: string,
    sessionId: string,
    payload: { status?: 'ended' | 'cancelled'; provider_payload?: Record<string, unknown> }
  ) => api.post<ProjectSyncSession>(`/projects/${projectId}/sync-sessions/${sessionId}/end`, payload),
  listSyncMessages: (projectId: string, sessionId: string) =>
    api.get<{ session: ProjectSyncSession; messages: ProjectSyncMessage[] }>(
      `/projects/${projectId}/sync-sessions/${sessionId}/messages`
    ),
  createSyncMessage: (
    projectId: string,
    sessionId: string,
    payload: { content: string; is_command?: boolean; role?: string | null; command?: string | null; metadata?: Record<string, unknown> | null }
  ) =>
    api.post<ProjectSyncMessage>(
      `/projects/${projectId}/sync-sessions/${sessionId}/messages`,
      payload
    ),
  attachRecording: (
    projectId: string,
    sessionId: string,
    payload: { audio_url?: string; summary?: string; action_items?: Record<string, unknown>; transcript?: Record<string, unknown> }
  ) =>
    api.post<MeetingSummary>(
      `/projects/${projectId}/sync-sessions/${sessionId}/recording`,
      payload
    ),
  uploadRecording: (projectId: string, sessionId: string, file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post<MeetingSummary>(
      `/projects/${projectId}/sync-sessions/${sessionId}/recording/upload`,
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
      }
    )
  },
  createCallToken: (projectId: string, sessionId: string) =>
    api.post<SyncSessionTokenResponse>(
      `/projects/${projectId}/sync-sessions/${sessionId}/token`,
      {}
    ),
  deleteSyncSession: (projectId: string, sessionId: string) =>
    api.delete<void>(`/projects/${projectId}/sync-sessions/${sessionId}`),
}

export const projectNotificationsAPI = {
  listProjectNotifications: (projectId: string, options?: { unreadOnly?: boolean }) =>
    api.get<{ project_id: string; notifications: ProjectNotification[] }>(
      `/projects/${projectId}/notifications`,
      {
        params: {
          unread_only: options?.unreadOnly ?? false,
        },
      }
    ),
  markNotificationAsRead: (notificationId: string) =>
    api.post<ProjectNotification>(`/notifications/${notificationId}/read`, null),
}

// Project Discussion API endpoints
export const projectDiscussionAPI = {
  listMessages: (
    projectId: string,
    options?: { limit?: number; offset?: number; parentId?: string | null; channelId?: string | null }
  ) =>
    api.get<DiscussionMessage[]>(`/projects/${projectId}/discussion/messages`, {
      params: {
        limit: options?.limit ?? 100,
        offset: options?.offset ?? 0,
        parent_id: options?.parentId,
        channel_id: options?.channelId,
      },
    }),

  listThreads: (
    projectId: string,
    options?: { limit?: number; offset?: number; channelId?: string | null }
  ) =>
    api.get<DiscussionThread[]>(`/projects/${projectId}/discussion/threads`, {
      params: {
        limit: options?.limit ?? 50,
        offset: options?.offset ?? 0,
        channel_id: options?.channelId,
      },
    }),

  createMessage: (projectId: string, messageData: DiscussionMessageCreate) =>
    api.post<DiscussionMessage>(`/projects/${projectId}/discussion/messages`, messageData),

  updateMessage: (projectId: string, messageId: string, messageData: DiscussionMessageUpdate) =>
    api.put<DiscussionMessage>(`/projects/${projectId}/discussion/messages/${messageId}`, messageData),

  deleteMessage: (projectId: string, messageId: string) =>
    api.delete<void>(`/projects/${projectId}/discussion/messages/${messageId}`),

  getStats: (projectId: string, options?: { channelId?: string | null }) =>
    api.get<DiscussionStats>(`/projects/${projectId}/discussion/stats`, {
      params: {
        channel_id: options?.channelId,
      },
    }),

  listChannels: (projectId: string, options?: { includeArchived?: boolean }) =>
    api.get<DiscussionChannelSummary[]>(`/projects/${projectId}/discussion/channels`, {
      params: {
        include_archived: options?.includeArchived ?? false,
      },
    }),

  createChannel: (projectId: string, payload: DiscussionChannelCreate) =>
    api.post<DiscussionChannelSummary>(`/projects/${projectId}/discussion/channels`, payload),

  updateChannel: (projectId: string, channelId: string, payload: DiscussionChannelUpdate) =>
    api.put<DiscussionChannelSummary>(`/projects/${projectId}/discussion/channels/${channelId}`, payload),

  listAssistantHistory: (projectId: string, channelId: string) =>
    api.get<DiscussionAssistantHistoryItem[]>(
      `/projects/${projectId}/discussion/channels/${channelId}/assistant-history`
    ),

  listChannelResources: (projectId: string, channelId: string) =>
    api.get<DiscussionChannelResource[]>(
      `/projects/${projectId}/discussion/channels/${channelId}/resources`
    ),

  createChannelResource: (
    projectId: string,
    channelId: string,
    payload: DiscussionChannelResourceCreate
  ) =>
    api.post<DiscussionChannelResource>(
      `/projects/${projectId}/discussion/channels/${channelId}/resources`,
      payload
    ),

  deleteChannelResource: (projectId: string, channelId: string, resourceId: string) =>
    api.delete<void>(
      `/projects/${projectId}/discussion/channels/${channelId}/resources/${resourceId}`
    ),

  listTasks: (
    projectId: string,
    options?: { channelId?: string | null; status?: DiscussionTaskStatus | null }
  ) =>
    api.get<DiscussionTask[]>(`/projects/${projectId}/discussion/tasks`, {
      params: {
        channel_id: options?.channelId,
        status_filter: options?.status,
      },
    }),

  createTask: (
    projectId: string,
    channelId: string,
    payload: DiscussionTaskCreate
  ) =>
    api.post<DiscussionTask>(
      `/projects/${projectId}/discussion/channels/${channelId}/tasks`,
      payload
    ),

  updateTask: (projectId: string, taskId: string, payload: DiscussionTaskUpdate) =>
    api.put<DiscussionTask>(`/projects/${projectId}/discussion/tasks/${taskId}`, payload),

  deleteTask: (projectId: string, taskId: string) =>
    api.delete<void>(`/projects/${projectId}/discussion/tasks/${taskId}`),

  invokeAssistant: (
    projectId: string,
    channelId: string,
    payload: DiscussionAssistantRequest
  ) =>
    api.post<DiscussionAssistantResponse>(
      `/projects/${projectId}/discussion/channels/${channelId}/assistant`,
      payload
    ),
}

// Research Papers API endpoints
export const researchPapersAPI = {
  createPaper: (paperData: ResearchPaperCreate) => 
    api.post<ResearchPaper>('/research-papers/', paperData),
  
  getPapers: (
    skipOrOptions: number | { skip?: number; limit?: number; projectId?: string } = 0,
    limit = 100
  ) => {
    let skip = 0
    let limitValue = limit
    let projectId: string | undefined

    if (typeof skipOrOptions === 'object' && skipOrOptions !== null) {
      skip = skipOrOptions.skip ?? 0
      limitValue = skipOrOptions.limit ?? limit
      projectId = skipOrOptions.projectId
    } else {
      skip = skipOrOptions
      limitValue = limit
    }

    const params = new URLSearchParams()
    params.set('skip', String(skip))
    params.set('limit', String(limitValue))
    if (projectId) params.set('project_id', projectId)

    return api.get<ResearchPaperList>(`/research-papers/?${params.toString()}`)
  },
  
  getPaper: (id: string) => 
    api.get<ResearchPaper>(`/research-papers/${id}`),
  
  updatePaper: (id: string, paperData: ResearchPaperUpdate) => 
    api.put<ResearchPaper>(`/research-papers/${id}`, paperData),
  
  deletePaper: (id: string) => 
    api.delete(`/research-papers/${id}`),
  
  // Enhanced content update with JSON support and versioning
  updatePaperContent: (
    id: string, 
    contentData: {
      content?: string;
      content_json?: any;
      save_as_version?: boolean;
      version_summary?: string;
    }
  ) => api.put(`/research-papers/${id}/content`, contentData),
  
  // Versioning endpoints
  getPaperVersions: (paperId: string) =>
    api.get(`/research-papers/${paperId}/versions`),
  
  getPaperVersion: (paperId: string, versionNumber: string) =>
    api.get(`/research-papers/${paperId}/versions/${versionNumber}`),
  
  createPaperVersion: (paperId: string, versionData: {
    version_number: string;
    title: string;
    content?: string;
    content_json?: any;
    abstract?: string;
    keywords?: string;
    references?: string;
    change_summary?: string;
  }) => api.post(`/research-papers/${paperId}/versions`, versionData),
  
  restorePaperVersion: (paperId: string, versionNumber: string) =>
    api.put(`/research-papers/${paperId}/versions/${versionNumber}/restore`),

  uploadFigure: (paperId: string, formData: FormData) =>
    api.post(`/research-papers/${paperId}/figures`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),

  uploadBib: async (paperId: string, formData: FormData) => {
    // Use the same approach as uploadFigure
    const response = await api.post(`/research-papers/${paperId}/upload-bib`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response
  },


  // Branch-based versioning (commits)
  // Helper to find or create a branch by name for a paper
  _getOrCreateBranchId: async (paperId: string, branchName: string): Promise<string> => {
    // List existing branches
    const listResp = await api.get<any[]>(`/branches/paper/${paperId}`)
    const branches: any[] = Array.isArray(listResp.data) ? listResp.data : []
    let found = branches.find(b => (b?.name || '').toLowerCase() === (branchName || '').toLowerCase())
    if (!found) {
      const createResp = await api.post<any>(`/branches/`, { name: branchName, paper_id: paperId })
      found = createResp.data
    }
    return found?.id
  },

  saveVersion: async (
    paperId: string,
    content: string,
    message: string,
    branchName = 'main',
    contentJson?: any,
    compileMeta?: { compilation_status?: 'success' | 'failed' | 'not_compiled'; pdf_url?: string; compile_logs?: string }
  ) => {
    const branchId = await researchPapersAPI._getOrCreateBranchId(paperId, branchName)
    const payload: any = { message: message || 'Update', content, content_json: contentJson }
    if (compileMeta) {
      if (compileMeta.compilation_status) payload.compilation_status = compileMeta.compilation_status
      if (compileMeta.pdf_url) payload.pdf_url = compileMeta.pdf_url
      if (compileMeta.compile_logs) payload.compile_logs = compileMeta.compile_logs
    }
    const resp = await api.post<any>(`/branches/${branchId}/commit`, payload)
    return resp.data
  },

  getVersionHistory: async (paperId: string, branchName = 'main', limit = 50, opts?: { state?: 'draft' | 'ready_for_review' | 'published' }) => {
    const branchId = await researchPapersAPI._getOrCreateBranchId(paperId, branchName)
    const q = new URLSearchParams()
    if (opts?.state) q.set('state', opts.state)
    const url = q.toString() ? `/branches/${branchId}/commits?${q}` : `/branches/${branchId}/commits`
    const resp = await api.get<any[]>(url)
    const commits = Array.isArray(resp.data) ? resp.data : []
    return commits.slice(0, limit)
  },

  updateCommitState: async (commitId: string, state: 'draft'|'ready_for_review'|'published') => {
    const resp = await api.put<any>(`/branches/commit/${commitId}`, { state })
    return resp.data
  },

  switchBranch: async (paperId: string, branchName = 'main') => {
    const branchId = await researchPapersAPI._getOrCreateBranchId(paperId, branchName)
    const resp = await api.post<Record<string, unknown>>(`/branches/${branchId}/switch`, { paper_id: paperId })
    // Also fetch head commit id
    const commitsResp = await api.get<any[]>(`/branches/${branchId}/commits`)
    const headCommit = Array.isArray(commitsResp.data) && commitsResp.data.length > 0 ? commitsResp.data[0] : null
    return { ...(resp.data as Record<string, unknown>), headCommit }
  },

  mergeBranches: async (sourceBranchId: string, targetBranchId: string, strategy: 'auto'|'manual' = 'auto') => {
    const resp = await api.post<any>(`/branches/merge`, { source_branch_id: sourceBranchId, target_branch_id: targetBranchId, strategy })
    return resp.data
  },
  
  // Team management
  addPaperMember: (paperId: string, memberData: PaperMemberCreate) => 
    api.post(`/research-papers/${paperId}/members`, memberData),

  // Invitations
  getPendingInvitations: () =>
    api.get<{ pending_invitations: Array<{ id: string; paper_id: string; role: string; invited_at: string; paper_title: string }> }>(
      '/research-papers/invitations/pending'
    ),

  // References
  addReference: (paperId: string, ref: {
    title: string;
    authors?: string[];
    year?: number;
    doi?: string;
    url?: string;
    source?: string;
    is_open_access?: boolean;
    pdf_url?: string;
  }) => api.post(`/research-papers/${paperId}/references`, ref),

  listReferences: (paperId: string) => api.get<{ references: any[]; total: number }>(`/research-papers/${paperId}/references`),

  deleteReference: (paperId: string, refId: string) => api.delete(`/research-papers/${paperId}/references/${refId}`),
}

// Documents API endpoints (for reference documents, not rich text editing)
export const documentsAPI = {
  // File upload endpoints for reference documents
  uploadDocument: (formData: FormData) => 
    api.post<Document>('/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }),
  
  getDocuments: (paperId?: string, skip = 0, limit = 100) => {
    const params = new URLSearchParams()
    if (paperId) params.append('paper_id', paperId)
    params.append('skip', skip.toString())
    params.append('limit', limit.toString())
    return api.get<DocumentList>(`/documents/list?${params.toString()}`)
  },
  
  getDocument: (id: string) => 
    api.get<Document>(`/documents/${id}`),
  
  createDocument: (documentData: any) => 
    api.post<Document>('/documents/', documentData),
  
  updateDocument: (id: string, documentData: any) => 
    api.put<Document>(`/documents/${id}`, documentData),
  
  deleteDocument: (id: string) => 
    api.delete(`/documents/${id}`),
  
  getDocumentChunks: (id: string, skip = 0, limit = 100) => 
    api.get<{ chunks: DocumentChunk[]; total: number }>(
      `/documents/${id}/chunks?skip=${skip}&limit=${limit}`
    ),
  
  analyzeDocument: (id: string) => 
    api.post<AIDocumentAnalysis>(`/documents/${id}/analyze`),
  
  chatWithDocument: (id: string, question: string) => 
    api.post<AIChatResponse>(`/documents/${id}/chat`, { question }),

  // Ingest a remote PDF by URL (OA PDFs recommended)
  ingestRemote: (formData: FormData) =>
    api.post<Document>(`/documents/ingest-remote`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }),
}


// Team API endpoints
export const teamAPI = {
  getTeamMembers: (paperId: string) => 
    api.get(`/team/papers/${paperId}/members`),
  
  inviteTeamMember: (paperId: string, email: string, role: string) => 
    api.post(`/team/papers/${paperId}/invite`, { email, role }),
  
  acceptInvitation: (paperId: string, memberId: string) => 
    api.post(`/team/papers/${paperId}/members/${memberId}/accept`),
  
  declineInvitation: (paperId: string, memberId: string) => 
    api.post(`/team/papers/${paperId}/members/${memberId}/decline`),
  
  removeTeamMember: (paperId: string, memberId: string) => 
    api.delete(`/team/papers/${paperId}/members/${memberId}`),

  updateMemberRole: (paperId: string, memberId: string, role: string) => 
    api.patch(`/team/papers/${paperId}/members/${memberId}`, { role }),
}

// AI API endpoints
export const aiAPI = {
  // === Reference-based AI endpoints (PRIMARY) ===
  // Main reference-based chat endpoint
  chatWithReferences: (query: string, paperId?: string | null) =>
    api.post<{
      response: string;
      sources: string[];
      sources_data: any[];
      chat_id: string;
      scope: string;
      paper_title?: string;
    }>('/ai/chat-with-references', { query, paper_id: paperId || null }),

  // Reference processing endpoints
  ingestReference: (referenceId: string, forceReprocess?: boolean) =>
    api.post<{ success: boolean; message: string; status: string }>(`/ai/references/${referenceId}/ingest`, {}, {
      params: { force_reprocess: forceReprocess || false }
    }),
    
  ingestPaperReferences: (paperId: string, forceReprocess?: boolean) =>
    api.post<{ success: boolean; message: string; total_references: number; processed: number; failed: number }>(`/ai/papers/${paperId}/ingest-references`, {}, {
      params: { force_reprocess: forceReprocess || false }
    }),
    
  // Reference status endpoints
  getReferenceChatStatus: (referenceId: string) =>
    api.get<{ reference_id: string; chat_ready: boolean; status: string; chunk_count: number; has_pdf: boolean }>(`/ai/references/${referenceId}/chat-status`),
    
  getPaperReferencesChatStatus: (paperId: string) =>
    api.get<{ 
      paper_id: string; 
      paper_title: string; 
      total_references: number; 
      chat_ready_references: number; 
      total_chunks: number; 
      overall_chat_ready: boolean;
      references: any[];
    }>(`/ai/papers/${paperId}/references/chat-status`),

  // === Legacy document-based endpoints (DEPRECATED - use reference-based instead) ===
  chatWithDocuments: (query: string) =>
    api.post<AIChatResponse>('/ai/chat-with-documents', { query }),

  processDocumentForAI: (documentId: string) =>
    api.post<{ success: boolean; message: string; document_id: string }>(`/ai/documents/${documentId}/process`),

  getDocumentChunks: (documentId: string) =>
    api.get<{ chunks: DocumentChunk[] }>(`/ai/documents/${documentId}/chunks`),

  getChatHistory: (limit: number = 20) =>
    api.get<{ chat_sessions: any[]; total_sessions: number }>(`/ai/chat-history?limit=${limit}`),

  // === General AI endpoints ===
  getAIStatus: () =>
    api.get<AIStatusResponse>('/ai/status'),

  getModelConfiguration: () =>
    api.get<any>('/ai/models'),

  updateModelConfiguration: (provider: string, embedding_model?: string, chat_model?: string) =>
    api.put<any>('/ai/models', { provider, embedding_model, chat_model }),

  // === AI Writing Tools endpoints ===
  generateText: (text: string, instruction: string, context?: string, maxLength = 500) =>
    api.post<any>('/ai/writing/generate', { 
      text, 
      instruction, 
      context, 
      max_length: maxLength 
    }),

  checkGrammarAndStyle: (text: string, checkGrammar = true, checkStyle = true, checkClarity = true) =>
    api.post<any>('/ai/writing/grammar-check', { 
      text, 
      check_grammar: checkGrammar, 
      check_style: checkStyle, 
      check_clarity: checkClarity 
    }),

  enhanceWithResearchContext: (text: string, paperIds: string[], queryType: string) =>
    api.post<any>('/ai/writing/research-context', { 
      text, 
      paper_ids: paperIds, 
      query_type: queryType 
    }),

  // === Legacy endpoints (keeping for backward compatibility) ===
  summarizeText: (text: string, maxLength = 150) => 
    api.post<AISummaryResponse>('/ai/summarize', { text, max_length: maxLength }),
  
  rephraseText: (text: string, style = 'academic') => 
    api.post<AIRephraseResponse>('/ai/rephrase', { text, style }),
  
  generateOutline: (topic: string, content?: string) => 
    api.post<AIOutlineResponse>('/ai/generate-outline', { topic, content }),
  
  extractKeywords: (text: string, maxKeywords = 10) => 
    api.post<AIKeywordsResponse>('/ai/extract-keywords', { 
      text, 
      max_keywords: maxKeywords 
    }),
}

// Tags API endpoints
export const tagsAPI = {
  createTag: (tagData: TagCreate) => 
    api.post<Tag>('/tags/', tagData),
  
  getTags: () => 
    api.get<Tag[]>('/tags/'),
}

export default api
// References Library API
export const referencesAPI = {
  listMy: (params?: { skip?: number; limit?: number; q?: string }) => {
    const p = new URLSearchParams()
    if (params?.skip) p.set('skip', String(params.skip))
    if (params?.limit) p.set('limit', String(params.limit))
    if (params?.q) p.set('q', params.q)
    return api.get<{ references?: any[] } | any[]>(`/references/?${p.toString()}`)
  },
  create: (payload: {
    title: string;
    authors?: string[];
    year?: number;
    doi?: string;
    url?: string;
    source?: string;
    journal?: string;
    abstract?: string;
    is_open_access?: boolean;
    pdf_url?: string;
    paper_id?: string;
  }) => api.post<{ reference?: { id?: string }; id?: string }>(`/references/`, payload),
  uploadPdf: (referenceId: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post(`/references/${referenceId}/upload-pdf`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },
  ingestPdf: (referenceId: string) =>
    api.post(`/references/${referenceId}/ingest-pdf`, null),
  attachToPaper: (referenceId: string, paperId: string) => {
    const fd = new FormData()
    fd.append('paper_id', paperId)
    return api.post(`/references/${referenceId}/attach-to-paper`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },
  delete: (referenceId: string) => api.delete(`/references/${referenceId}`)
  ,
}

// Conversion API
export const conversionAPI = {
  convertRichToLatex: (paperId: string, model?: string, strategy: 'strict' | 'ai' = 'strict') =>
    api.post<{ new_paper_id: string; title: string; mode: string; report: any }>(
      '/convert/rich-to-latex',
      { paper_id: paperId, target: 'latex', model: model || undefined, create_copy: true, strategy }
    ),
  convertLatexToRich: (paperId: string, model?: string, strategy: 'strict' | 'ai' = 'strict') =>
    api.post<{ new_paper_id: string; title: string; mode: string; report: any }>(
      '/convert/latex-to-rich',
      { paper_id: paperId, target: 'rich', model: model || undefined, create_copy: true, strategy }
    )
}
