import { RouteObject } from 'react-router-dom'
import DiscoveryHub from '../pages/discovery/DiscoveryHub'

export const discoveryRoutes: RouteObject[] = [
  {
    path: 'discovery',
    element: <DiscoveryHub />,
  },
]
