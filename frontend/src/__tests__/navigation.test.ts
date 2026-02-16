import { describe, it, expect } from 'vitest'
import { navigationConfig, getNavigationMode } from '../config/navigation'

describe('navigationConfig', () => {
  it('has USE_NEW_NAVIGATION property', () => {
    expect(navigationConfig).toHaveProperty('USE_NEW_NAVIGATION')
    expect(typeof navigationConfig.USE_NEW_NAVIGATION).toBe('boolean')
  })
})

describe('getNavigationMode', () => {
  it('returns "new" when USE_NEW_NAVIGATION is true', () => {
    // navigationConfig.USE_NEW_NAVIGATION is currently true
    expect(getNavigationMode()).toBe('new')
  })
})
