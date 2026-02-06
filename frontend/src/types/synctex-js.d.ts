declare module 'synctex-js' {
  export const parser: {
    parseSyncTex(body: string): {
      blockNumberLine: Record<string, Record<number, Record<number, any[]>>>
      hBlocks: any[]
      pages: Record<string, any>
      files: Record<string, { path: string; name: string }>
      numberPages: number
      offset: { x: number; y: number }
      version: string
    }
  }
}
