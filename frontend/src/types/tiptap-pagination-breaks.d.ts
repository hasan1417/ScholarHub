declare module 'tiptap-pagination-breaks' {
  import { Extension } from '@tiptap/core'

  interface PaginationOptions {
    pageHeight?: number
    pageWidth?: number
    pageMargin?: number
  }

  export const Pagination: Extension<PaginationOptions>
}
