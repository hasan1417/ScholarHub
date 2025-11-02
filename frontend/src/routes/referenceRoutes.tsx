import { RouteObject } from 'react-router-dom'
import MyReferences from '../pages/references/MyReferences'

export const referenceRoutes: RouteObject[] = [
  {
    path: 'my-references',
    element: <MyReferences />,
  },
]
