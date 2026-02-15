import { Navigate, RouteObject } from 'react-router-dom'
import ProjectsHome from '../pages/projects/ProjectsHome'
import ProjectLayout from '../pages/projects/ProjectLayout'
import ProjectOverview from '../pages/projects/ProjectOverview'
import ProjectDiscussion from '../pages/projects/ProjectDiscussion'
import ProjectPapers from '../pages/projects/ProjectPapers'
import ProjectDiscovery from '../pages/projects/ProjectDiscovery'
import ProjectReferences from '../pages/projects/ProjectReferences'
import PaperDetail from '../pages/projects/PaperDetail'
import PaperEditor from '../pages/projects/PaperEditor'
import ViewPaper from '../pages/projects/ViewPaper'
import CreatePaperWithTemplate from '../pages/projects/CreatePaperWithTemplate'
import ProjectLibrary from '../pages/projects/ProjectLibrary'

export const projectRoutes: RouteObject[] = [
  {
    index: true,
    element: <ProjectsHome />,
  },
  {
    path: 'projects',
    children: [
      {
        index: true,
        element: <ProjectsHome />,
      },
      {
        path: ':projectId',
        element: <ProjectLayout />,
        children: [
          {
            index: true,
            element: <Navigate to="overview" replace />,
          },
          {
            path: 'overview/*',
            element: <ProjectOverview />,
          },
          {
            path: 'discussion',
            element: <ProjectDiscussion />,
          },
          {
            path: 'library/*',
            element: <ProjectLibrary />,
          },
          // SHARED ROUTES (papers)
          {
            path: 'papers',
            element: <ProjectPapers />,
          },
          {
            path: 'papers/new',
            element: <CreatePaperWithTemplate />,
          },
          {
            path: 'papers/:paperId',
            children: [
              {
                index: true,
                element: <PaperDetail />,
              },
              {
                path: 'view',
                element: <ViewPaper />,
              },
              {
                path: 'editor',
                element: <PaperEditor />,
              },
              {
                path: 'collaborate',
                element: <PaperEditor />,
              },
            ],
          },
          // OLD NAVIGATION backward-compat routes
          {
            path: 'discovery',
            element: <ProjectDiscovery />,
          },
          {
            path: 'related-papers',
            element: <ProjectReferences />,
          },
          // Backward-compat redirects for old Collaborate routes
          {
            path: 'collaborate/chat-beta',
            element: <Navigate to="../discussion" replace />,
          },
          {
            path: 'collaborate/chat',
            element: <Navigate to="../discussion" replace />,
          },
          {
            path: 'collaborate/meetings',
            element: <Navigate to="../overview/meetings" replace />,
          },
          {
            path: 'collaborate',
            element: <Navigate to="../discussion" replace />,
          },
          {
            path: 'sync-space',
            element: <Navigate to="../overview/meetings" replace />,
          },
        ],
      },
    ],
  },
]
