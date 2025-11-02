declare module '@hocuspocus/provider' {
  export interface HocuspocusProviderOptions {
    url: string
    name: string
    token?: string
    document?: any
  }

  export class HocuspocusProvider {
    constructor(options: HocuspocusProviderOptions)
    awareness: any
    configuration?: any
    on(event: string, listener: (...args: any[]) => void): void
    off(event: string, listener: (...args: any[]) => void): void
    destroy(): void
  }
}
