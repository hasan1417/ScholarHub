// User types
export interface User {
  id: string
  email: string
  first_name?: string
  last_name?: string
  avatar_url?: string
  is_active: boolean
  is_verified: boolean
  auth_provider?: string  // "local" or "google"
  created_at: string
  updated_at: string
}

// Project types
export interface ProjectMemberSummary {
  id: string
  user_id: string
  role: string
  status: string
  first_name?: string | null
  last_name?: string | null
  email: string
}

export interface ProjectSummary {
  id: string
  title: string
  idea?: string
  keywords?: string[] | null
  scope?: string | null
  status: string
  created_by: string
  created_at: string
  updated_at: string
  discovery_preferences?: ProjectDiscoveryPreferences | null
  members?: ProjectMemberSummary[] | null
  current_user_role?: string | null
  current_user_status?: string | null
  paper_count?: number
  reference_count?: number
}

export interface ProjectListResponse {
  projects: ProjectSummary[]
  total: number
  skip: number
  limit: number
}

export interface ProjectMemberUser {
  id: string
  email: string
  first_name?: string | null
  last_name?: string | null
  display_name?: string
}

export interface ProjectMember {
  id: string
  project_id: string
  user_id: string
  role: string
  status: string
  invited_by?: string | null
  invited_at?: string | null
  joined_at?: string | null
  user: ProjectMemberUser
}

export interface ProjectDetail extends Omit<ProjectSummary, 'members'> {
  members: ProjectMember[]
}

export type AIArtifactType = 'summary' | 'litReview' | 'outline' | 'directoryHelp' | 'intent'

export type AIArtifactStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export interface AIArtifact {
  id: string
  type: AIArtifactType
  status: AIArtifactStatus
  project_id?: string | null
  paper_id?: string | null
  payload: Record<string, any>
  created_by?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface ProjectReferenceSuggestion {
  id: string
  reference_id: string
  project_id: string
  status: 'pending' | 'approved' | 'rejected'
  confidence?: number | null
  created_at?: string | null
  updated_at?: string | null
  decided_at?: string | null
  decided_by?: string | null
  reference?: {
    id?: string | null
    title?: string
    authors?: string[] | null
    year?: number | null
    doi?: string | null
    url?: string | null
    source?: string | null
    journal?: string | null
    abstract?: string | null
    status?: string | null
    summary?: string | null
    is_open_access?: boolean | null
    pdf_url?: string | null
    pdf_processed?: boolean | null
    document_id?: string | null
    document_status?: string | null
    document_download_url?: string | null
  } | null
  papers?: Array<{
    paper_id: string
    title?: string
  }>
}

export interface PaperReferenceAttachment {
  paper_reference_id: string
  project_reference_id?: string | null
  project_reference_status?: 'pending' | 'approved' | 'rejected' | null
  reference_id: string
  title?: string | null
  authors?: string[] | null
  year?: number | null
  doi?: string | null
  url?: string | null
  source?: string | null
  journal?: string | null
  abstract?: string | null
  is_open_access?: boolean | null
  pdf_url?: string | null
  attached_at?: string | null
}

export interface ProjectDiscoveryPreferences {
  query?: string | null
  keywords?: string[] | null
  sources?: string[] | null
  auto_refresh_enabled?: boolean
  refresh_interval_hours?: number | null
  last_run_at?: string | null
  last_result_count?: number | null
  last_status?: string | null
  max_results?: number | null
  relevance_threshold?: number | null
}

export interface ProjectDiscoverySettingsPayload {
  query?: string | null
  keywords?: string[] | null
  sources?: string[] | null
  auto_refresh_enabled?: boolean
  refresh_interval_hours?: number | null
  max_results?: number | null
  relevance_threshold?: number | null
}

export interface SourceStatsItem {
  source: string
  count: number
  status: 'pending' | 'success' | 'timeout' | 'error' | 'rate_limited' | 'cancelled'
  error: string | null
}

export interface ProjectDiscoveryRunResponse {
  run_id: string
  total_found: number
  results_created: number
  references_created: number
  project_suggestions_created: number
  last_run_at: string
  source_stats: SourceStatsItem[] | null
}

export type ProjectDiscoveryResultStatus = 'pending' | 'promoted' | 'dismissed'
export type ProjectDiscoveryRunType = 'manual' | 'auto'

export interface ProjectDiscoveryResultItem {
  id: string
  run_id: string
  run_type: ProjectDiscoveryRunType
  status: ProjectDiscoveryResultStatus
  source: string
  doi?: string | null
  title?: string | null
  summary?: string | null
  authors?: string[] | null
  published_year?: number | null
  relevance_score?: number | null
  created_at: string
  promoted_at?: string | null
  dismissed_at?: string | null
  run_started_at: string
  run_completed_at?: string | null
  is_open_access?: boolean | null
  has_pdf?: boolean | null
  pdf_url?: string | null
  open_access_url?: string | null
  source_url?: string | null
}

export interface ProjectDiscoveryResultsResponse {
  total: number
  results: ProjectDiscoveryResultItem[]
}

export interface ProjectDiscoveryCountResponse {
  pending: number
}

export interface ProjectDiscoveryClearResponse {
  cleared: number
}

export interface ProjectSyncSession {
  id: string
  project_id: string
  started_by: string | null
  status: 'scheduled' | 'live' | 'ended' | 'cancelled'
  provider?: string | null
  provider_room_id?: string | null
  provider_payload?: Record<string, unknown> | null
  started_at?: string | null
  ended_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  recording?: MeetingSummary | null
  room_url?: string | null
}

export interface ProjectSyncMessage {
  id: string
  session_id: string
  author_id: string | null
  role: 'participant' | 'ai' | 'system'
  content: string
  is_command: boolean
  command?: string | null
  metadata?: Record<string, unknown> | null
  created_at?: string | null
}

export interface ProjectNotification {
  id: string
  user_id: string
  project_id?: string | null
  type: string
  payload?: Record<string, unknown> | null
  read: boolean
  created_at?: string | null
}

export interface MeetingSummary {
  id: string
  project_id: string
  created_by: string | null
  status: 'uploaded' | 'transcribing' | 'completed' | 'failed'
  audio_url?: string | null
  transcript?: Record<string, unknown> | null
  summary?: string | null
  action_items?: Record<string, unknown> | null
  created_at?: string | null
  updated_at?: string | null
}

export interface SyncSessionTokenResponse {
  session_id: string
  token: string
  expires_at: string
  provider: string
  room_name: string
  room_url?: string | null
  join_url?: string | null
  domain?: string | null
}

export interface ProjectCreateInput {
  title: string
  idea?: string
  keywords?: string[]
  scope?: string
  status?: string
}

// Research Paper types
export interface ResearchPaper {
  id: string
  title: string
  abstract?: string
  content?: string
  content_json?: any  // TipTap JSON content
  status: string
  paper_type: string
  owner_id: string
  is_public: boolean
  project_id?: string | null
  format?: string | null
  summary?: string | null
  objectives?: string[] | string | null
  keywords?: string[] | string  // Support both array and string for backward compatibility
  references?: string
  current_version?: string
  
  // Discovery metadata
  year?: number
  doi?: string
  url?: string
  source?: string
  authors?: string[]
  journal?: string
  description?: string
  
  created_at: string
  updated_at: string
}

export interface ResearchPaperCreate {
  title: string
  abstract?: string
  content?: string
  content_json?: any
  keywords?: string[] | string
  paper_type?: string
  is_public?: boolean
  references?: string
  project_id?: string
  format?: string
  summary?: string
  objectives?: string[] | string
}

export interface ResearchPaperUpdate {
  title?: string
  abstract?: string
  content?: string
  content_json?: any
  keywords?: string[] | string
  paper_type?: string
  is_public?: boolean
  references?: string
  status?: string
  project_id?: string
  format?: string
  summary?: string
  objectives?: string[] | string
}

export interface ResearchPaperList {
  papers: ResearchPaper[]
  total: number
  skip: number
  limit: number
}

// Paper Version types
export interface PaperVersion {
  id: string
  paper_id: string
  version_number: string
  title: string
  content?: string
  content_json?: any
  abstract?: string
  keywords?: string
  references?: string
  change_summary?: string
  created_by?: string
  created_at: string
}

export interface PaperVersionList {
  versions: PaperVersion[]
  total: number
  current_version: string
}

// Paper Member types
export interface PaperMember {
  id: string
  paper_id: string
  user_id: string
  role: string
}

export interface PaperMemberCreate {
  paper_id: string
  user_id: string
  role: string
}

export interface PaperMemberResponse {
  id: string
  paper_id: string
  user_id: string
  role: string
}

// Document types
export interface Document {
  id: string
  filename: string
  original_filename: string
  file_path: string
  file_size?: number
  mime_type?: string
  document_type: string
  status: string
  extracted_text?: string
  page_count?: number
  title?: string
  abstract?: string
  authors?: string
  publication_year?: number
  journal?: string
  doi?: string
  owner_id: string
  owner_name?: string  // Name of the user who uploaded the document
  paper_id?: string
  is_processed_for_ai?: boolean
  processed_at?: string
  created_at: string
  updated_at: string
}

export interface DocumentCreate {
  title?: string
  abstract?: string
  authors?: string
  publication_year?: number
  journal?: string
  doi?: string
  paper_id?: string
}

export interface DocumentUpdate {
  title?: string
  abstract?: string
  authors?: string
  publication_year?: number
  journal?: string
  doi?: string
  paper_id?: string
}

export interface DocumentList {
  documents: Document[]
  total: number
  skip: number
  limit: number
}

export interface DocumentUpload {
  file: File
  title?: string
  abstract?: string
  authors?: string
  publication_year?: number
  journal?: string
  doi?: string
  paper_id?: string
  tags?: string[]
}

// Document Chunk types
export interface DocumentChunk {
  id: string
  document_id: string
  chunk_text: string
  chunk_index: number
  page_number?: number
  section_title?: string
  chunk_metadata?: any
  embedding?: number[]
  created_at: string
}

// Tag types
export interface Tag {
  id: string
  name: string
  created_at: string
}

export interface TagCreate {
  name: string
}

export interface TagResponse {
  id: string
  name: string
  created_at: string
}

// AI Response types
export interface AISummaryResponse {
  summary: string
  original_length: number
  summary_length: number
}

export interface AIRephraseResponse {
  rephrased_text: string
  original_text: string
  style: string
}

export interface AIDocumentAnalysis {
  summary: string
  key_points: string[]
  topics: string[]
  sentiment: string
  reading_time: number
}

export interface AIChatResponse {
  response: string
  sources: Array<{
    chunk_id?: string
    document_id: string
    text?: string
    text_preview?: string
    similarity?: number
    metadata?: any
  }>
  chat_id?: string
}

export interface AIStatusResponse {
  ai_service_ready: boolean
  embedding_model: string | null
  status: string
  progress: number
  message: string
  model_loaded: boolean
}

export interface AIOutlineResponse {
  outline: Array<{
    level: number
    title: string
    description?: string
  }>
}

export interface AIKeywordsResponse {
  keywords: string[]
  confidence_scores: number[]
}

// API Response Types
export interface ApiResponse<T> {
  data: T
  message?: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  size: number
  pages: number
}

// Project Discussion types
export interface DiscussionMessageUserInfo {
  id: string
  name: string
  email: string
}

export interface DiscussionMessageAttachment {
  id: string
  message_id: string
  attachment_type: string
  title?: string | null
  url?: string | null
  document_id?: string | null
  paper_id?: string | null
  reference_id?: string | null
  meeting_id?: string | null
  details: Record<string, any>
  created_at: string
  created_by?: string | null
}

export interface DiscussionMessage {
  id: string
  project_id: string
  channel_id: string
  user_id: string
  user: DiscussionMessageUserInfo
  content: string
  parent_id?: string | null
  is_edited: boolean
  is_deleted: boolean
  created_at: string
  updated_at: string
  reply_count: number
  attachments: DiscussionMessageAttachment[]
}

export interface DiscussionThread {
  message: DiscussionMessage
  replies: DiscussionMessage[]
}

export interface DiscussionMessageCreate {
  content: string
  channel_id?: string | null
  parent_id?: string | null
}

export interface DiscussionMessageUpdate {
  content: string
}

export interface DiscussionStats {
  project_id: string
  total_messages: number
  total_threads: number
  channel_id?: string | null
}

// Channel scope: null = project-wide, or specific resource IDs
export interface ChannelScopeConfig {
  paper_ids?: string[] | null
  reference_ids?: string[] | null
  meeting_ids?: string[] | null
}

export interface DiscussionChannelSummary {
  id: string
  project_id: string
  name: string
  slug: string
  description?: string | null
  is_default: boolean
  is_archived: boolean
  scope?: ChannelScopeConfig | null  // null = project-wide, or specific resource IDs
  created_at: string
  updated_at: string
  stats?: DiscussionStats | null
}

export interface DiscussionChannelCreate {
  name: string
  description?: string | null
  slug?: string | null
  scope?: ChannelScopeConfig | null  // null = project-wide, or specific resource IDs
}

export interface DiscussionChannelUpdate {
  name?: string
  description?: string | null
  is_archived?: boolean
  scope?: ChannelScopeConfig | null  // null = don't change, empty = project-wide, or specific resource IDs
}

export type DiscussionResourceType = 'paper' | 'reference' | 'meeting'

export interface DiscussionChannelResource {
  id: string
  channel_id: string
  resource_type: DiscussionResourceType
  paper_id?: string | null
  reference_id?: string | null
  meeting_id?: string | null
  details: Record<string, any>
  added_by?: string | null
  created_at: string
}

export interface DiscussionChannelResourceCreate {
  resource_type: DiscussionResourceType
  paper_id?: string
  reference_id?: string
  meeting_id?: string
  details?: Record<string, any>
}

export type DiscussionTaskStatus = 'open' | 'in_progress' | 'completed' | 'cancelled'

export interface DiscussionTask {
  id: string
  project_id: string
  channel_id: string
  message_id?: string | null
  title: string
  description?: string | null
  status: DiscussionTaskStatus
  assignee_id?: string | null
  due_date?: string | null
  details: Record<string, any>
  created_by?: string | null
  updated_by?: string | null
  completed_at?: string | null
  created_at: string
  updated_at: string
}

export interface DiscussionTaskCreate {
  title: string
  description?: string | null
  assignee_id?: string | null
  due_date?: string | null
  details?: Record<string, any>
  message_id?: string | null
}

export interface DiscussionTaskUpdate {
  title?: string
  description?: string | null
  status?: DiscussionTaskStatus
  assignee_id?: string | null
  due_date?: string | null
  details?: Record<string, any>
}

export interface RecentSearchResultItem {
  title: string
  authors?: string
  year?: number | null
  source?: string
  abstract?: string
  doi?: string
  url?: string
  pdf_url?: string
  is_open_access?: boolean
  journal?: string
}

export interface DiscussionAssistantRequest {
  question: string
  reasoning?: boolean
  scope?: Array<'transcripts' | 'papers' | 'references'>
  recent_search_results?: RecentSearchResultItem[]
}

export type DiscussionAssistantOrigin = 'resource' | 'message'

export interface DiscussionAssistantCitation {
  origin: DiscussionAssistantOrigin
  origin_id: string
  label: string
  resource_type?: string | null
}

export interface DiscussionAssistantResponse {
  message: string
  citations: DiscussionAssistantCitation[]
  reasoning_used: boolean
  model: string
  usage?: Record<string, unknown>
  suggested_actions?: DiscussionAssistantSuggestedAction[]
}

export interface DiscussionAssistantHistoryItem {
  id: string
  question: string
  response: DiscussionAssistantResponse
  created_at: string
  author?: {
    id?: string
    name?: { display?: string; first?: string; last?: string } | string
  } | null
}

export interface DiscussionAssistantSuggestedAction {
  action_type: string
  summary: string
  payload: Record<string, any>
}

// Subscription types
export interface SubscriptionTier {
  id: string
  name: string
  price_monthly_cents: number
  limits: Record<string, number>
  is_active: boolean
  created_at?: string
}

export interface UserSubscription {
  id: string
  user_id: string
  tier_id: string
  status: 'active' | 'cancelled'
  current_period_start?: string
  current_period_end?: string
  custom_limits?: Record<string, number> | null
  created_at?: string
  updated_at?: string
}

export interface UsageTracking {
  id: string
  user_id: string
  period_year: number
  period_month: number
  discussion_ai_calls: number
  paper_discovery_searches: number
  created_at?: string
  updated_at?: string
}

export interface LimitExceededError {
  error: 'limit_exceeded'
  feature?: string
  resource?: string
  current: number
  limit: number
  tier: string
}

export interface SubscriptionState {
  subscription: UserSubscription | null
  usage: UsageTracking | null
  limits: Record<string, number>
  loading: boolean
}
