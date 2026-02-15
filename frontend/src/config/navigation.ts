/**
 * Navigation Configuration
 *
 * Control the project navigation structure.
 * Set USE_NEW_NAVIGATION to false to revert to the original 6-tab layout.
 */

export const navigationConfig = {
  /**
   * Enable new simplified navigation (4 tabs with sub-sections)
   *
   * true  = New: Overview | Papers | Scholar AI | Library
   * false = Old: Overview | Papers | Discussion | Sync Space | Research dropdown
   */
  USE_NEW_NAVIGATION: true,
} as const

export type NavigationMode = 'new' | 'old'

export const getNavigationMode = (): NavigationMode => {
  return navigationConfig.USE_NEW_NAVIGATION ? 'new' : 'old'
}
