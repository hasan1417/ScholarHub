import { useEffect, useRef, useCallback } from 'react'
import { isFeatureEnabled, getFeatureConfig } from '../config/featureFlags'

interface PerformanceMetrics {
  memoryUsage: number
  renderTime: number
  syncLatency: number
  errors: string[]
}

interface UsePerformanceMonitorOptions {
  onMemoryWarning?: (usage: number) => void
  onPerformanceIssue?: (metric: string, value: number) => void
  logMetrics?: boolean
}

export const usePerformanceMonitor = (options: UsePerformanceMonitorOptions = {}) => {
  const metricsRef = useRef<PerformanceMetrics>({
    memoryUsage: 0,
    renderTime: 0,
    syncLatency: 0,
    errors: []
  })
  
  const startTimeRef = useRef<number>(0)
  const intervalRef = useRef<number | undefined>(undefined)

  const logMetric = useCallback((metric: string, value: number) => {
    if (options.logMetrics && isFeatureEnabled('DEBUG_MODE.logPerformance')) {
      console.log(`📊 Performance: ${metric} = ${value}`)
    }
  }, [options.logMetrics])

  const checkMemoryUsage = useCallback(() => {
    if (!isFeatureEnabled('PERFORMANCE_MONITORING.enabled')) return

    try {
      if ('memory' in performance) {
        const memoryInfo = (performance as any).memory
        const usedMemory = memoryInfo.usedJSHeapSize
        metricsRef.current.memoryUsage = usedMemory
        
        const config = getFeatureConfig('PERFORMANCE_MONITORING')
        const memoryMB = Math.round(usedMemory / 1024 / 1024)
        
        logMetric('Memory Usage (MB)', memoryMB)
        
        if (usedMemory > config.memoryThreshold) {
          const warning = `Memory usage high: ${memoryMB}MB`
          metricsRef.current.errors.push(warning)
          options.onMemoryWarning?.(usedMemory)
          
          if (isFeatureEnabled('DEBUG_MODE.logPerformance')) {
            console.warn(`⚠️ ${warning}`)
          }
        }
      }
    } catch (error) {
      const errorMsg = `Memory monitoring failed: ${error}`
      metricsRef.current.errors.push(errorMsg)
    }
  }, [options.onMemoryWarning, logMetric])

  const measureRenderTime = useCallback(() => {
    if (!isFeatureEnabled('PERFORMANCE_MONITORING.enabled')) return

    const endTime = performance.now()
    const renderTime = endTime - startTimeRef.current
    
    metricsRef.current.renderTime = renderTime
    logMetric('Render Time (ms)', renderTime)
    
    // Warn if render time is too high
    if (renderTime > 100) { // 100ms threshold
      const warning = `Slow render detected: ${renderTime.toFixed(2)}ms`
      metricsRef.current.errors.push(warning)
      options.onPerformanceIssue?.('renderTime', renderTime)
    }
  }, [options.onPerformanceIssue, logMetric])

  const measureSyncLatency = useCallback((latency: number) => {
    if (!isFeatureEnabled('PERFORMANCE_MONITORING.enabled')) return

    metricsRef.current.syncLatency = latency
    logMetric('Sync Latency (ms)', latency)
    
    const config = getFeatureConfig('PERFORMANCE_MONITORING')
    if (latency > config.syncTimeout) {
      const warning = `Slow sync detected: ${latency}ms`
      metricsRef.current.errors.push(warning)
      options.onPerformanceIssue?.('syncLatency', latency)
    }
  }, [options.onPerformanceIssue, logMetric])

  const startMonitoring = useCallback(() => {
    if (!isFeatureEnabled('PERFORMANCE_MONITORING.enabled')) return

    startTimeRef.current = performance.now()
    
    // Monitor memory every 5 seconds
    intervalRef.current = window.setInterval(checkMemoryUsage, 5000)
    
    if (isFeatureEnabled('DEBUG_MODE.logPerformance')) {
      console.log('🔍 Performance monitoring started')
    }
  }, [checkMemoryUsage])

  const stopMonitoring = useCallback(() => {
    if (intervalRef.current) {
      window.clearInterval(intervalRef.current)
      intervalRef.current = undefined
    }
    
    if (isFeatureEnabled('DEBUG_MODE.logPerformance')) {
      console.log('🔍 Performance monitoring stopped')
    }
  }, [])

  const getMetrics = useCallback(() => {
    return { ...metricsRef.current }
  }, [])

  const clearErrors = useCallback(() => {
    metricsRef.current.errors = []
  }, [])

  // Start monitoring on mount
  useEffect(() => {
    startMonitoring()
    return () => stopMonitoring()
  }, [startMonitoring, stopMonitoring])

  return {
    startMonitoring,
    stopMonitoring,
    measureRenderTime,
    measureSyncLatency,
    getMetrics,
    clearErrors,
    isMonitoring: isFeatureEnabled('PERFORMANCE_MONITORING.enabled')
  }
}
