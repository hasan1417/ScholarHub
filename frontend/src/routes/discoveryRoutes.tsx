import { RouteObject } from 'react-router-dom'
import DiscoveryHub from '../pages/discovery/DiscoveryHub'
import DiscoveryDebug from '../pages/debug/DiscoveryDebug'

export const discoveryRoutes: RouteObject[] = [
  {
    path: 'discovery',
    element: <DiscoveryHub />,
  },
  {
    path: 'discovery-debug',
    element: <DiscoveryDebug />,
  },
]
