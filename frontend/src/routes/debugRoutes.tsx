import { RouteObject } from 'react-router-dom'
import PublisherProbe from '../pages/debug/PublisherProbe'
import PDFResolverDebug from '../pages/debug/PDFResolverDebug'

export const debugRoutes: RouteObject[] = [
  {
    path: 'publisher-probe',
    element: <PublisherProbe />,
  },
  {
    path: 'pdf-resolver-debug',
    element: <PDFResolverDebug />,
  },
]
