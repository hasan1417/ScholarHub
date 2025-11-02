declare module 'y-codemirror.next' {
  import type { Extension } from '@codemirror/state'
  import type { Text, UndoManager } from 'yjs'
  import type { Awareness } from 'y-protocols/awareness'

  export function yCollab(
    yText: Text,
    awareness?: Awareness | null,
    opts?: {
      undoManager?: UndoManager
      awarenessField?: string
      field?: string
      updateOnSelectionChange?: boolean
    }
  ): Extension

  export const yUndoManagerKeymap: any
}
