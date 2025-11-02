import React from 'react'
import { useParams } from 'react-router-dom'
import DocumentShell from '../../components/editor/DocumentShell'
import OOAdapter from '../../components/editor/adapters/OOAdapter'

const OnlyOfficePrototype: React.FC = () => {
  const { paperId } = useParams()
  const id = paperId || 'demo-paper'
  const title = `OnlyOffice • ${id}`

  return (
    <div className="min-h-screen bg-gray-50">
      <DocumentShell
        paperId={id}
        paperTitle={title}
        initialContent=""
        Adapter={OOAdapter as any}
        fullBleed
        initialPaperRole="admin"
      />
    </div>
  )
}

export default OnlyOfficePrototype
