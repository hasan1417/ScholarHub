import { RouteObject } from 'react-router-dom'
import EditProfile from '../pages/profile/EditProfile'

export const profileRoutes: RouteObject[] = [
  {
    path: 'profile',
    element: <EditProfile />,
  },
]
