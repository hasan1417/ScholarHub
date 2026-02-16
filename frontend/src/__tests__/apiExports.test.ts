import { describe, it, expect } from 'vitest'
import api, {
  authAPI,
  usersAPI,
  projectsAPI,
  researchPapersAPI,
  documentsAPI,
  teamAPI,
  aiAPI,
  tagsAPI,
  projectDiscussionAPI,
  projectReferencesAPI,
  projectDiscoveryAPI,
  projectMeetingsAPI,
  projectNotificationsAPI,
  projectAIAPI,
  latexAPI,
  referencesAPI,
  snapshotsAPI,
  zoteroAPI,
  subscriptionAPI,
  conversionAPI,
  streamAPI,
} from '../services/api'

describe('API service exports', () => {
  it('exports default axios instance', () => {
    expect(api).toBeDefined()
    expect(typeof api.get).toBe('function')
    expect(typeof api.post).toBe('function')
    expect(typeof api.put).toBe('function')
    expect(typeof api.delete).toBe('function')
  })

  it('exports authAPI with expected methods', () => {
    expect(authAPI).toBeDefined()
    expect(typeof authAPI.login).toBe('function')
    expect(typeof authAPI.register).toBe('function')
    expect(typeof authAPI.logout).toBe('function')
    expect(typeof authAPI.getCurrentUser).toBe('function')
  })

  it('exports usersAPI with expected methods', () => {
    expect(usersAPI).toBeDefined()
    expect(typeof usersAPI.getUsers).toBe('function')
    expect(typeof usersAPI.getUser).toBe('function')
    expect(typeof usersAPI.uploadAvatar).toBe('function')
  })

  it('exports projectsAPI with CRUD methods', () => {
    expect(projectsAPI).toBeDefined()
    expect(typeof projectsAPI.list).toBe('function')
    expect(typeof projectsAPI.create).toBe('function')
    expect(typeof projectsAPI.get).toBe('function')
    expect(typeof projectsAPI.update).toBe('function')
    expect(typeof projectsAPI.delete).toBe('function')
  })

  it('exports researchPapersAPI with paper operations', () => {
    expect(researchPapersAPI).toBeDefined()
    expect(typeof researchPapersAPI.createPaper).toBe('function')
    expect(typeof researchPapersAPI.getPapers).toBe('function')
    expect(typeof researchPapersAPI.getPaper).toBe('function')
    expect(typeof researchPapersAPI.updatePaper).toBe('function')
    expect(typeof researchPapersAPI.deletePaper).toBe('function')
    expect(typeof researchPapersAPI.saveVersion).toBe('function')
  })

  it('exports documentsAPI', () => {
    expect(documentsAPI).toBeDefined()
    expect(typeof documentsAPI.uploadDocument).toBe('function')
    expect(typeof documentsAPI.getDocuments).toBe('function')
  })

  it('exports teamAPI', () => {
    expect(teamAPI).toBeDefined()
    expect(typeof teamAPI.getTeamMembers).toBe('function')
    expect(typeof teamAPI.inviteTeamMember).toBe('function')
  })

  it('exports aiAPI', () => {
    expect(aiAPI).toBeDefined()
    expect(typeof aiAPI.chatWithReferences).toBe('function')
    expect(typeof aiAPI.getAIStatus).toBe('function')
    expect(typeof aiAPI.summarizeText).toBe('function')
  })

  it('exports project sub-APIs', () => {
    expect(projectDiscussionAPI).toBeDefined()
    expect(projectReferencesAPI).toBeDefined()
    expect(projectDiscoveryAPI).toBeDefined()
    expect(projectMeetingsAPI).toBeDefined()
    expect(projectNotificationsAPI).toBeDefined()
    expect(projectAIAPI).toBeDefined()
  })

  it('exports utility APIs', () => {
    expect(tagsAPI).toBeDefined()
    expect(latexAPI).toBeDefined()
    expect(referencesAPI).toBeDefined()
    expect(snapshotsAPI).toBeDefined()
    expect(zoteroAPI).toBeDefined()
    expect(subscriptionAPI).toBeDefined()
    expect(conversionAPI).toBeDefined()
    expect(streamAPI).toBeDefined()
  })
})
