// Use the shared, configured API client (handles auth + refresh)
import api from './api'

export interface Branch {
  id: string
  name: string
  paperId: string
  parentBranchId?: string
  createdAt: string
  updatedAt: string
  status: 'active' | 'merged' | 'archived'
  authorId: string
  authorName: string
  lastCommitMessage: string
  isMain: boolean
}

export interface MergeRequest {
  id: string
  sourceBranchId: string
  targetBranchId: string
  paperId: string
  title: string
  description: string
  status: 'open' | 'merged' | 'closed' | 'conflicted'
  createdAt: string
  updatedAt: string
  authorId: string
  authorName: string
  conflicts?: Conflict[]
}

export interface Conflict {
  id: string
  section: string
  sourceContent: string
  targetContent: string
  resolvedContent?: string
  status: 'unresolved' | 'resolved' | 'auto-resolved'
  resolutionStrategy: 'manual' | 'auto' | 'source-wins' | 'target-wins'
}

export interface Commit {
  id: string
  branchId: string
  message: string
  content: string
  content_json?: any
  compilation_status?: 'success' | 'failed' | 'not_compiled'
  pdf_url?: string | null
  compile_logs?: string | null
  authorId: string
  authorName: string
  timestamp: string
  changes: Change[]
}

export interface Change {
  type: 'insert' | 'delete' | 'update'
  section: string
  oldContent?: string
  newContent?: string
  position: number
}

class BranchService {
  private baseUrl = '/branches'  // Relative to /api/v1
  private isDemoMode = false // Disable demo mode - use production APIs
  
  // Helper method to check if we should use demo mode
  private shouldUseDemoMode(): boolean {
    // Fall back to demo if no access token present
    return this.isDemoMode || !localStorage.getItem('access_token')
  }

  // Helper method to convert HTML to readable text
  private htmlToText(html: string): string {
    // Create a temporary div to parse HTML
    const tempDiv = document.createElement('div')
    tempDiv.innerHTML = html
    
    // Extract text content and preserve some structure
    const textContent = tempDiv.textContent || tempDiv.innerText || ''
    
    // Clean up extra whitespace while preserving line breaks
    return textContent
      .replace(/\s+/g, ' ')  // Replace multiple spaces with single space
      .replace(/\n\s*\n/g, '\n')  // Remove empty lines
      .trim()
  }

  // Helper method to extract meaningful sections from HTML
  private extractSections(html: string): { type: string, content: string }[] {
    const tempDiv = document.createElement('div')
    tempDiv.innerHTML = html
    
    const sections: { type: string, content: string }[] = []
    
    // Extract headings
    const headings = tempDiv.querySelectorAll('h1, h2, h3, h4, h5, h6')
    headings.forEach((heading) => {
      sections.push({
        type: `Heading (${heading.tagName})`,
        content: heading.textContent?.trim() || ''
      })
    })
    
    // Extract paragraphs
    const paragraphs = tempDiv.querySelectorAll('p')
    paragraphs.forEach((p, index) => {
      const text = p.textContent?.trim()
      if (text && text.length > 10) {  // Only include substantial paragraphs
        sections.push({
          type: `Paragraph ${index + 1}`,
          content: text.length > 150 ? text.substring(0, 150) + '...' : text
        })
      }
    })
    
    // If no specific sections found, return the full text
    if (sections.length === 0) {
      const text = this.htmlToText(html)
      if (text.trim()) {
        sections.push({
          type: 'Content',
          content: text.length > 200 ? text.substring(0, 200) + '...' : text
        })
      }
    }
    
    return sections
  }

  // Helper method to calculate changes between commits with detailed diff
  private calculateChanges(branchId: string, newContent: string): Change[] {
    const previousCommits = this.mockCommits.filter(c => c.branchId === branchId)
    const previousCommit = previousCommits.length > 0 ? previousCommits[previousCommits.length - 1] : null
    const previousContent = previousCommit?.content || ''
    
    const changes: Change[] = []
    
    if (previousContent !== newContent) {
      // Extract sections from both versions
      const oldSections = this.extractSections(previousContent)
      const newSections = this.extractSections(newContent)
      
      // Simple comparison by section count and content
      if (oldSections.length === 0 && newSections.length > 0) {
        // New content added
        newSections.forEach((section, index) => {
          changes.push({
            type: 'insert',
            section: section.type,
            newContent: section.content,
            position: index
          })
        })
      } else if (oldSections.length > 0 && newSections.length === 0) {
        // Content deleted
        oldSections.forEach((section, index) => {
          changes.push({
            type: 'delete',
            section: section.type,
            oldContent: section.content,
            position: index
          })
        })
      } else {
        // Content modified - compare sections
        const maxSections = Math.max(oldSections.length, newSections.length)
        
        for (let i = 0; i < maxSections; i++) {
          const oldSection = oldSections[i]
          const newSection = newSections[i]
          
          if (!oldSection && newSection) {
            // Section added
            changes.push({
              type: 'insert',
              section: newSection.type,
              newContent: newSection.content,
              position: i
            })
          } else if (oldSection && !newSection) {
            // Section deleted
            changes.push({
              type: 'delete',
              section: oldSection.type,
              oldContent: oldSection.content,
              position: i
            })
          } else if (oldSection && newSection && oldSection.content !== newSection.content) {
            // Section modified
            changes.push({
              type: 'update',
              section: newSection.type,
              oldContent: oldSection.content,
              newContent: newSection.content,
              position: i
            })
          }
        }
      }
      
      // If no specific changes detected, add a general update
      if (changes.length === 0) {
        const oldText = this.htmlToText(previousContent)
        const newText = this.htmlToText(newContent)
        
        changes.push({
          type: 'update',
          section: 'Document Content',
          oldContent: oldText.length > 100 ? oldText.substring(0, 100) + '...' : oldText,
          newContent: newText.length > 100 ? newText.substring(0, 100) + '...' : newText,
          position: 0
        })
      }
    }
    
    return changes.length > 0 ? changes : [{
      type: 'insert',
      section: 'Initial Content',
      newContent: 'Document created with initial content',
      position: 0
    }]
  }

  // Mock data for demo
  // Mock data for demo - branches are created dynamically per paper
  private mockBranches: Branch[] = [
  ]

  private mockCommits: Commit[] = [
  ]

  // Branch Management
  async createBranch(paperId: string, name: string, parentBranchId?: string): Promise<Branch> {
    if (this.shouldUseDemoMode()) {
      const newBranch: Branch = {
        id: `branch-${Date.now()}`,
        name,
        paperId,
        parentBranchId,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        status: 'active',
        authorId: 'demo-user',
        authorName: 'Demo User',
        lastCommitMessage: 'Branch created',
        isMain: false
      }
      this.mockBranches.push(newBranch)
      return newBranch
    }

    const response = await api.post(this.baseUrl, {
      paperId,
      name,
      parentBranchId
    })
    return response.data as Branch
  }

  async getBranches(paperId: string): Promise<Branch[]> {
    if (this.shouldUseDemoMode()) {
      // Ensure there's always a main branch for each paper
      const existingBranches = this.mockBranches.filter(b => b.paperId === paperId)
      
      if (existingBranches.length === 0) {
        // Create default main branch for this paper
        const mainBranch: Branch = {
          id: `main-${paperId}`,
          name: 'main',
          paperId,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          status: 'active',
          authorId: 'demo-user',
          authorName: 'Demo User',
          lastCommitMessage: 'Initial commit',
          isMain: true
        }
        this.mockBranches.push(mainBranch)
        
        // Create initial commit for main branch
        const initialCommit: Commit = {
          id: `commit-${Date.now()}`,
          branchId: mainBranch.id,
          message: 'Initial commit',
          content: '',
          authorId: 'demo-user',
          authorName: 'Demo User',
          timestamp: new Date().toISOString(),
          changes: [{
            type: 'insert',
            section: 'content',
            newContent: 'Initial paper created (blank)',
            position: 0
          }]
        }
        this.mockCommits.push(initialCommit)
        
        return [mainBranch]
      }
      
      return existingBranches
    }

    try {
      const response = await api.get(`${this.baseUrl}/paper/${paperId}`)
      return response.data as Branch[]
    } catch (error: any) {
      console.warn('API call failed, falling back to demo mode:', error?.message)
      // If API call fails (e.g., no auth), fallback to demo mode
      this.isDemoMode = true
      return this.getBranches(paperId) // Recursive call will use demo mode
    }
  }

  async switchBranch(paperId: string, branchId: string): Promise<{ content: string; branch: Branch }> {
    if (this.isDemoMode) {
      const branch = this.mockBranches.find(b => b.id === branchId)
      if (!branch) {
        throw new Error('Branch not found')
      }
      return {
        branch,
        content: '<h1>Switched to ' + branch.name + '</h1><p>This is the content from the ' + branch.name + ' branch.</p>'
      }
    }

    const response = await api.post(`${this.baseUrl}/${branchId}/switch`, { paperId })
    return response.data as { content: string; branch: Branch }
  }

  async deleteBranch(branchId: string): Promise<void> {
    if (this.isDemoMode) {
      const index = this.mockBranches.findIndex(b => b.id === branchId)
      if (index > -1) {
        this.mockBranches.splice(index, 1)
      }
      return
    }

    await api.delete(`${this.baseUrl}/${branchId}`)
  }

  // Commit Management
  async commitChanges(branchId: string, message: string, content: string, contentJson?: any): Promise<Commit> {
    if (this.isDemoMode) {
      const newCommit: Commit = {
        id: `commit-${Date.now()}`,
        branchId,
        message,
        content,
        content_json: contentJson,
        authorId: 'demo-user',
        authorName: 'Demo User',
        timestamp: new Date().toISOString(),
        changes: this.calculateChanges(branchId, content)
      }
      this.mockCommits.push(newCommit)
      
      // Update branch last commit message
      const branch = this.mockBranches.find(b => b.id === branchId)
      if (branch) {
        branch.lastCommitMessage = message
        branch.updatedAt = new Date().toISOString()
      }
      
      return newCommit
    }

    const payload: any = { message, content }
    if (contentJson) payload.content_json = contentJson
    const response = await api.post(`${this.baseUrl}/${branchId}/commit`, payload)
    return response.data as Commit
  }

  async getCommitHistory(branchId: string): Promise<Commit[]> {
    if (this.isDemoMode) {
      const branchCommits = this.mockCommits.filter(c => c.branchId === branchId)
      // Sort by timestamp descending (newest first)
      return branchCommits.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
    }

    const response = await api.get(`${this.baseUrl}/${branchId}/commits`)
    return response.data as Commit[]
  }

  // Mock merge requests for demo
  private mockMergeRequests: MergeRequest[] = []

  // Merge Management
  async createMergeRequest(
    sourceBranchId: string,
    targetBranchId: string,
    title: string,
    description: string
  ): Promise<MergeRequest> {
    if (this.isDemoMode) {
      const newMR: MergeRequest = {
        id: `mr-${Date.now()}`,
        sourceBranchId,
        targetBranchId,
        paperId: 'demo-paper-123',
        title,
        description,
        status: 'open',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        authorId: 'demo-user',
        authorName: 'Demo User'
      }
      this.mockMergeRequests.push(newMR)
      return newMR
    }

    const response = await api.post(`${this.baseUrl}/merge-requests`, {
      sourceBranchId,
      targetBranchId,
      title,
      description
    })
    return response.data as MergeRequest
  }

  async getMergeRequests(paperId: string): Promise<MergeRequest[]> {
    if (this.isDemoMode) {
      return this.mockMergeRequests.filter(mr => mr.paperId === paperId)
    }

    const response = await api.get(`${this.baseUrl}/merge-requests/paper/${paperId}`)
    return response.data as MergeRequest[]
  }

  async mergeBranches(
    sourceBranchId: string,
    targetBranchId: string,
    strategy: 'auto' | 'manual' = 'auto'
  ): Promise<{ success: boolean; conflicts?: Conflict[]; mergedContent?: string }> {
    if (this.isDemoMode) {
      // Simulate successful merge for demo
      return {
        success: true,
        mergedContent: '<h1>Merged Content</h1><p>This content was successfully merged from multiple branches.</p>'
      }
    }

    const response = await api.post(`${this.baseUrl}/merge`, {
      sourceBranchId,
      targetBranchId,
      strategy
    })
    return response.data as { success: boolean; conflicts?: Conflict[]; mergedContent?: string }
  }

  async resolveConflict(conflictId: string, resolvedContent: string): Promise<Conflict> {
    if (this.isDemoMode) {
      // Return mock resolved conflict
      return {
        id: conflictId,
        section: 'Demo Section',
        sourceContent: 'Source content',
        targetContent: 'Target content',
        resolvedContent,
        status: 'resolved',
        resolutionStrategy: 'manual'
      }
    }

    const response = await api.put(`${this.baseUrl}/conflicts/${conflictId}`, {
      resolvedContent,
      status: 'resolved'
    })
    return response.data as Conflict
  }

  // Conflict Analysis
  async analyzeConflicts(sourceBranchId: string, targetBranchId: string): Promise<Conflict[]> {
    if (this.isDemoMode) {
      // Return mock conflicts for demo
      return [
        {
          id: 'conflict-1',
          section: 'Introduction',
          sourceContent: 'This is the source content for the introduction.',
          targetContent: 'This is the target content for the introduction.',
          status: 'unresolved',
          resolutionStrategy: 'manual'
        }
      ]
    }

    const response = await api.post(`${this.baseUrl}/analyze-conflicts`, {
      sourceBranchId,
      targetBranchId
    })
    return response.data as Conflict[]
  }

  // Auto-merge strategies
  async autoMergeStrategy(
    conflicts: Conflict[],
    strategy: 'source-wins' | 'target-wins' | 'smart'
  ): Promise<Conflict[]> {
    if (this.isDemoMode) {
      // Return resolved conflicts based on strategy
      return conflicts.map(conflict => ({
        ...conflict,
        status: 'resolved',
        resolvedContent: strategy === 'source-wins' ? conflict.sourceContent : conflict.targetContent
      }))
    }

    const response = await api.post(`${this.baseUrl}/auto-merge`, {
      conflicts,
      strategy
    })
    return response.data as Conflict[]
  }
}

export const branchService = new BranchService()
