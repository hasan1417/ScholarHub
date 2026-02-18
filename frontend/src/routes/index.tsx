import { RouteObject, Navigate, Outlet } from 'react-router-dom'
import ProtectedRoute from '../components/auth/ProtectedRoute'
import PublicRoute from '../components/auth/PublicRoute'
import Layout from '../components/layout/Layout'
import Landing from '../pages/Landing'
import OverviewShowcase from '../pages/OverviewShowcase'
import DesignShowcase from '../pages/DesignShowcase'
import EditDetailsShowcase from '../pages/EditDetailsShowcase'
import Pricing from '../pages/Pricing'
import PrivacyPolicy from '../pages/PrivacyPolicy'
import TermsOfService from '../pages/TermsOfService'
import { authRoutes } from './authRoutes'
import { referenceRoutes } from './referenceRoutes'
// Global discovery route removed - discovery is now only accessible within project context
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
  {
    path: 'privacy',
    element: <PrivacyPolicy />,
  },
  {
    path: 'terms',
    element: <TermsOfService />,
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
      {
        path: 'overview-showcase',
        element: <OverviewShowcase />,
      },
      {
        path: 'design-showcase',
        element: <DesignShowcase />,
      },
      {
        path: 'edit-details-showcase',
        element: <EditDetailsShowcase />,
      },
      {
        path: 'pricing',
        element: <Pricing />,
      },
      ...referenceRoutes,
      // discoveryRoutes removed - discovery only within project context
      ...profileRoutes,
      {
        path: '*',
        element: <Navigate to="/projects" replace />,
      },
    ],
  },
]
