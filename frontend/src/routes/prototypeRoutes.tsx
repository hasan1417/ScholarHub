import { RouteObject } from 'react-router-dom'
import OnlyOfficePrototype from '../pages/prototypes/OnlyOfficePrototype'
import DocumentShellOOPrototype from '../pages/prototypes/DocumentShellOOPrototype'

export const prototypeRoutes: RouteObject[] = [
  {
    path: 'prototypes/onlyoffice/:paperId',
    element: <OnlyOfficePrototype />,
  },
  {
    path: 'prototypes/onlyoffice',
    element: <OnlyOfficePrototype />,
  },
  {
    path: 'prototypes/docshell-oo/:paperId',
    element: <DocumentShellOOPrototype />,
  },
  {
    path: 'prototypes/docshell-oo',
    element: <DocumentShellOOPrototype />,
  },
]
