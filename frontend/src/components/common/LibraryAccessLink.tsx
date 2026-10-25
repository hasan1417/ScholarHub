import type { MouseEvent } from 'react'
import { Landmark } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import { usersAPI } from '../../services/api'

export const LIBRARY_PRESETS = [
  { name: 'KFUPM', prefix: 'https://login.kfupm.idm.oclc.org/login?url=' },
]

export const libraryName = (prefix: string) =>
  LIBRARY_PRESETS.find((p) => p.prefix === prefix)?.name ?? 'library'

interface LibraryAccessLinkProps {
  doi?: string | null
  url?: string | null
  className?: string
  iconClassName?: string
}

/** "Via <library>" button for a paper; renders nothing until the user sets a library proxy. */
export const LibraryAccessLink = ({ doi, url, className, iconClassName = 'h-3 w-3' }: LibraryAccessLinkProps) => {
  const { user } = useAuth()
  const prefix = user?.library_proxy_prefix
  const httpUrl = url && /^https?:\/\//i.test(url) ? url : null
  if (!prefix || (!doi && !httpUrl)) return null

  const handleClick = async (e: MouseEvent) => {
    e.stopPropagation()
    // Open the tab inside the click so popup blockers allow it, then navigate once the link resolves
    const tab = window.open('', '_blank')
    if (!tab) return
    tab.opener = null
    try {
      const res = await usersAPI.getLibraryLink({ doi, url: httpUrl })
      tab.location.href = res.data.url
    } catch {
      tab.close()
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      title={`Open through your ${libraryName(prefix)} subscription`}
      className={className ?? 'inline-flex items-center gap-1 text-emerald-700 hover:underline dark:text-emerald-400'}
    >
      <Landmark className={iconClassName} />
      Via {libraryName(prefix)}
    </button>
  )
}
