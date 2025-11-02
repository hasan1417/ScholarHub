const ENV = (typeof import.meta !== 'undefined' ? (import.meta as any).env : {}) as Record<string, any>
const IS_DEV_MODE =
  typeof import.meta !== 'undefined' ? (import.meta as any).env?.MODE === 'development' : true

const readBoolEnv = (key: string, fallback: boolean): boolean => {
  const raw = ENV?.[key]
  if (typeof raw === 'string') {
    const normalized = raw.trim().toLowerCase()
    return ['1', 'true', 'yes', 'on', 'enabled'].includes(normalized)
  }
  if (typeof raw === 'boolean') {
    return raw
  }
  return fallback
}

// Feature Flags for safe testing and gradual rollout
export const FEATURE_FLAGS = {
  // Team chat with slash-assistant (server parses slash)
  CHAT_ASSISTANT_SLASH: {
    enabled: readBoolEnv('VITE_FLAG_CHAT_ASSISTANT_SLASH', false)
  },
  
  // AI Writing Tools - DISABLED FOR SAFE TESTING
  AI_WRITING_TOOLS: {
    enabled: readBoolEnv('VITE_FLAG_AI_WRITING_TOOLS', false), // Start disabled for safe testing
    maxTextLength: 1000, // Start small
    rateLimit: 2000, // 2 seconds between requests
    fallbackMode: true, // Always have fallback
  },

  // Performance Monitoring - ENABLED FOR TESTING
  PERFORMANCE_MONITORING: {
    enabled: readBoolEnv('VITE_FLAG_PERFORMANCE_MONITORING', true),
    logMetrics: true,
    memoryThreshold: 50 * 1024 * 1024, // 50MB (conservative)
    syncTimeout: 15000, // 15 seconds (generous)
  },

  // Debug Mode (for development only)
  DEBUG_MODE: {
    enabled: readBoolEnv('VITE_FLAG_DEBUG_MODE', IS_DEV_MODE),
    logAICalls: false,
    logPerformance: true,
  }
}

// Helper function to check if a feature is enabled
export const isFeatureEnabled = (featurePath: string): boolean => {
  const keys = featurePath.split('.')
  let current: any = FEATURE_FLAGS
  
  for (const key of keys) {
    if (current && typeof current === 'object' && key in current) {
      current = current[key]
    } else {
      return false
    }
  }

  // If we ended on a config object with an 'enabled' flag
  if (current && typeof current === 'object' && 'enabled' in current) {
    return current.enabled === true
  }
  // If we ended on a boolean value (e.g., path included 'enabled')
  if (typeof current === 'boolean') {
    return current === true
  }
  return false
}

// Helper function to get feature configuration
export const getFeatureConfig = (featurePath: string): any => {
  const keys = featurePath.split('.')
  let current: any = FEATURE_FLAGS
  
  for (const key of keys) {
    if (current && typeof current === 'object' && key in current) {
      current = current[key]
    } else {
      return null
    }
  }
  
  return current
}
