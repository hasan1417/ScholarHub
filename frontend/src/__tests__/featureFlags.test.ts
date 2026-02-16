import { describe, it, expect } from 'vitest'
import { isFeatureEnabled, getFeatureConfig, FEATURE_FLAGS } from '../config/featureFlags'

describe('isFeatureEnabled', () => {
  it('returns false for non-existent feature path', () => {
    expect(isFeatureEnabled('NON_EXISTENT_FEATURE')).toBe(false)
  })

  it('returns false for deeply non-existent path', () => {
    expect(isFeatureEnabled('PERFORMANCE_MONITORING.nonExistentKey.deep')).toBe(false)
  })

  it('resolves nested boolean values', () => {
    // PERFORMANCE_MONITORING.logMetrics is true
    expect(isFeatureEnabled('PERFORMANCE_MONITORING.logMetrics')).toBe(true)
  })

  it('resolves enabled field on feature objects', () => {
    // PERFORMANCE_MONITORING has { enabled: true, ... }
    const result = isFeatureEnabled('PERFORMANCE_MONITORING')
    expect(result).toBe(FEATURE_FLAGS.PERFORMANCE_MONITORING.enabled)
  })
})

describe('getFeatureConfig', () => {
  it('returns full config object for a feature', () => {
    const config = getFeatureConfig('PERFORMANCE_MONITORING')
    expect(config).toBeDefined()
    expect(config).toHaveProperty('enabled')
    expect(config).toHaveProperty('memoryThreshold')
    expect(config).toHaveProperty('syncTimeout')
  })

  it('returns specific nested value', () => {
    const memThreshold = getFeatureConfig('PERFORMANCE_MONITORING.memoryThreshold')
    expect(memThreshold).toBe(50 * 1024 * 1024)
  })

  it('returns null for non-existent path', () => {
    expect(getFeatureConfig('DOES_NOT_EXIST')).toBeNull()
  })

  it('returns null for deeply non-existent path', () => {
    expect(getFeatureConfig('PERFORMANCE_MONITORING.foo.bar')).toBeNull()
  })
})
