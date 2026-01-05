import { RouteObject } from 'react-router-dom'
import PublisherProbe from '../pages/debug/PublisherProbe'
import PDFResolverDebug from '../pages/debug/PDFResolverDebug'
import AgentTestPage from '../pages/AgentTestPage'

export const debugRoutes: RouteObject[] = [
  {
    path: 'publisher-probe',
    element: <PublisherProbe />,
  },
  {
    path: 'pdf-resolver-debug',
    element: <PDFResolverDebug />,
  },
  {
    path: 'agent-test',
    element: <AgentTestPage />,
  },
]
