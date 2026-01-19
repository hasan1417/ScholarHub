import { RouteObject, Navigate, Outlet } from 'react-router-dom'
import ProtectedRoute from '../components/auth/ProtectedRoute'
import PublicRoute from '../components/auth/PublicRoute'
import Layout from '../components/layout/Layout'
import Landing from '../pages/Landing'
import { authRoutes } from './authRoutes'
import { referenceRoutes } from './referenceRoutes'
import { discoveryRoutes } from './discoveryRoutes'
import { profileRoutes } from './profileRoutes'
import { projectRoutes } from './projectRoutes'
import PaperRedirect from '../pages/projects/PaperRedirect'

export const appRouteConfig: RouteObject[] = [
  {
    element: (
      <PublicRoute>
        <Outlet />
      </PublicRoute>
    ),
    children: [
      {
        index: true,
        element: <Landing />,
      },
    ],
  },
  ...authRoutes,
  {
    element: (
      <ProtectedRoute>
        <Layout />
      </ProtectedRoute>
    ),
    children: [
      ...projectRoutes,
      {
        path: 'papers/:paperId/*',
        element: <PaperRedirect />,
      },
      {
        path: 'dashboard',
        element: <Navigate to="/projects" replace />,
      },
      ...referenceRoutes,
      ...discoveryRoutes,
      ...profileRoutes,
      {
        path: '*',
        element: <Navigate to="/projects" replace />,
      },
    ],
  },
]
