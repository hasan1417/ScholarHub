import { RouteObject } from 'react-router-dom'
import ProjectsHome from '../pages/projects/ProjectsHome'
import ProjectLayout from '../pages/projects/ProjectLayout'
import ProjectOverview from '../pages/projects/ProjectOverview'
import ProjectDiscussion from '../pages/projects/ProjectDiscussion'
import ProjectSyncSpace from '../pages/projects/ProjectSyncSpace'
import ProjectPapers from '../pages/projects/ProjectPapers'
import ProjectDiscovery from '../pages/projects/ProjectDiscovery'
import ProjectReferences from '../pages/projects/ProjectReferences'
import PaperDetail from '../pages/projects/PaperDetail'
import PaperEditor from '../pages/projects/PaperEditor'
import ViewPaper from '../pages/projects/ViewPaper'
import CreatePaperWithTemplate from '../pages/projects/CreatePaperWithTemplate'
import ProjectCollaborate from '../pages/projects/ProjectCollaborate'
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
            element: <ProjectOverview />,
          },
          // OLD NAVIGATION ROUTES (kept for backward compatibility)
          {
            path: 'discussion',
            element: <ProjectDiscussion />,
          },
          {
            path: 'sync-space',
            element: <ProjectSyncSpace />,
          },
          {
            path: 'discovery',
            element: <ProjectDiscovery />,
          },
          {
            path: 'related-papers',
            element: <ProjectReferences />,
          },
          // NEW NAVIGATION ROUTES
          {
            path: 'collaborate/*',
            element: <ProjectCollaborate />,
          },
          {
            path: 'library/*',
            element: <ProjectLibrary />,
          },
          // SHARED ROUTES (work with both navigation modes)
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
        ],
      },
    ],
  },
]
