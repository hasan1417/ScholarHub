declare global {
  interface Window {
    JitsiMeetExternalAPI?: new (
      domain: string,
      options: {
        roomName: string
        parentNode: HTMLElement
        jwt?: string
        userInfo?: {
          displayName?: string
          email?: string
        }
        configOverwrite?: Record<string, unknown>
        interfaceConfigOverwrite?: Record<string, unknown>
      }
    ) => {
      dispose: () => void
      addListener: (event: string, handler: (...args: any[]) => void) => void
      removeListener: (event: string, handler: (...args: any[]) => void) => void
      executeCommand: (command: string, ...args: any[]) => void
    }
  }
}

export {}
