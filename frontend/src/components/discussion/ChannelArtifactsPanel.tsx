import { useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { FileText, Download, Trash2, Loader2, FileCode, File } from 'lucide-react'
import { projectDiscussionAPI } from '../../services/api'

interface Artifact {
  id: string
  title: string
  filename: string
  format: string
  artifact_type: string
  mime_type: string
  file_size?: string
  created_at: string
  created_by?: string
}

interface ChannelArtifactsPanelProps {
  projectId: string
  channelId: string
  refreshKey?: number
}

const formatIcon = (format: string) => {
  switch (format) {
    case 'pdf':
      return <FileText className="h-4 w-4 text-red-500" />
    case 'latex':
      return <FileCode className="h-4 w-4 text-green-500" />
    case 'markdown':
      return <FileText className="h-4 w-4 text-blue-500" />
    default:
      return <File className="h-4 w-4 text-gray-500" />
  }
}

const formatDate = (dateStr: string) => {
  const date = new Date(dateStr)
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function ChannelArtifactsPanel({ projectId, channelId, refreshKey }: ChannelArtifactsPanelProps) {
  const queryClient = useQueryClient()

  const { data: artifacts, isLoading, error } = useQuery({
    queryKey: ['channel-artifacts', projectId, channelId],
    queryFn: async () => {
      const response = await projectDiscussionAPI.listArtifacts(projectId, channelId)
      return response.data
    },
    enabled: !!projectId && !!channelId,
  })

  // Refetch when refreshKey changes (triggered after artifact creation)
  useEffect(() => {
    if (refreshKey && refreshKey > 0) {
      queryClient.invalidateQueries({ queryKey: ['channel-artifacts', projectId, channelId] })
    }
  }, [refreshKey, projectId, channelId, queryClient])

  const deleteMutation = useMutation({
    mutationFn: async (artifactId: string) => {
      await projectDiscussionAPI.deleteArtifact(projectId, channelId, artifactId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['channel-artifacts', projectId, channelId] })
    },
  })

  const handleDownload = async (artifact: Artifact) => {
    try {
      const response = await projectDiscussionAPI.getArtifact(projectId, channelId, artifact.id)
      const { content_base64, filename, mime_type } = response.data

      // Properly decode base64 to binary
      const binaryString = atob(content_base64)
      const bytes = new Uint8Array(binaryString.length)
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i)
      }
      const blob = new Blob([bytes], { type: mime_type })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Failed to download artifact:', err)
    }
  }

  const handleDelete = (artifactId: string) => {
    if (confirm('Are you sure you want to delete this artifact?')) {
      deleteMutation.mutate(artifactId)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-8 text-red-500">
        Failed to load artifacts
      </div>
    )
  }

  if (!artifacts || artifacts.length === 0) {
    return (
      <div className="text-center py-8">
        <FileText className="mx-auto h-12 w-12 text-gray-300 dark:text-slate-600" />
        <p className="mt-2 text-sm text-gray-500 dark:text-slate-400">
          No artifacts yet
        </p>
        <p className="mt-1 text-xs text-gray-400 dark:text-slate-500">
          Ask the AI to generate downloadable content
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {artifacts.map((artifact) => (
        <div
          key={artifact.id}
          className="flex items-center justify-between rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3 hover:bg-gray-50 dark:hover:bg-slate-700/50 transition-colors"
        >
          <div className="flex items-center gap-3 min-w-0 flex-1">
            {formatIcon(artifact.format)}
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-gray-900 dark:text-slate-100 truncate">
                {artifact.title}
              </p>
              <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-slate-400">
                <span className="uppercase">{artifact.format}</span>
                {artifact.file_size && (
                  <>
                    <span>•</span>
                    <span>{artifact.file_size}</span>
                  </>
                )}
                <span>•</span>
                <span>{formatDate(artifact.created_at)}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1 ml-2">
            <button
              onClick={() => handleDownload(artifact)}
              className="p-1.5 rounded-md text-gray-500 hover:text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-500/10 transition-colors"
              title="Download"
            >
              <Download className="h-4 w-4" />
            </button>
            <button
              onClick={() => handleDelete(artifact.id)}
              disabled={deleteMutation.isPending}
              className="p-1.5 rounded-md text-gray-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors disabled:opacity-50"
              title="Delete"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
