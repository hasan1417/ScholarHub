import { useEffect } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { researchPapersAPI } from '../../services/api'

const legacySegmentMap: Record<string, string> = {
  '/edit': '/editor',
  '/collaborate': '/editor',
}

const PaperRedirect = () => {
  const { paperId } = useParams<{ paperId: string }>()
  const location = useLocation()
  const navigate = useNavigate()

  const { data, isLoading, isError } = useQuery({
    queryKey: ['legacy-paper-redirect', paperId],
    queryFn: async () => {
      if (!paperId) throw new Error('Missing paper id')
      const response = await researchPapersAPI.getPaper(paperId)
      return response.data
    },
    enabled: Boolean(paperId),
  })

  useEffect(() => {
    if (!data) return
    const projectId = data.project_id
    const basePath = projectId ? `/projects/${projectId}/papers/${data.id}` : '/projects'
    const suffix = location.pathname.replace(`/papers/${data.id}`, '')
    const mappedSuffix = legacySegmentMap[suffix] ?? suffix
    const target = `${basePath}${mappedSuffix || ''}${location.search || ''}`
    navigate(target, { replace: true })
  }, [data, location.pathname, location.search, navigate])

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-sm text-gray-500">Redirecting to the new paper workspace…</p>
      </div>
    )
  }

  useEffect(() => {
    if (isError) {
      navigate('/projects', { replace: true })
    }
  }, [isError, navigate])

  return null
}

export default PaperRedirect
