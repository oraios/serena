import { ref, computed } from 'vue'
import type { Ref, ComputedRef } from 'vue'
import type { FormatOptions } from '@/types'

/**
 * Composable for formatting numbers with various options.
 * Demonstrates: composable pattern, refs, computed, type imports
 */
export function useFormatter(initialPrecision: number = 2) {
  // State
  const precision = ref<number>(initialPrecision)
  const useGrouping = ref<boolean>(true)
  const locale = ref<string>('en-US')

  // Computed properties
  const formatOptions = computed((): FormatOptions => ({
    maxDecimals: precision.value,
    useGrouping: useGrouping.value
  }))

  // Methods
  const formatNumber = (value: number): string => {
    return value.toLocaleString(locale.value, {
      minimumFractionDigits: precision.value,
      maximumFractionDigits: precision.value,
      useGrouping: useGrouping.value
    })
  }

  const formatCurrency = (value: number, currency: string = 'USD'): string => {
    return value.toLocaleString(locale.value, {
      style: 'currency',
      currency,
      minimumFractionDigits: precision.value,
      maximumFractionDigits: precision.value
    })
  }

  const formatPercentage = (value: number): string => {
    return `${(value * 100).toFixed(precision.value)}%`
  }

  const setPrecision = (newPrecision: number): void => {
    if (newPrecision >= 0 && newPrecision <= 10) {
      precision.value = newPrecision
    }
  }

  const toggleGrouping = (): void => {
    useGrouping.value = !useGrouping.value
  }

  const setLocale = (newLocale: string): void => {
    locale.value = newLocale
  }

  // Return composable API
  return {
    // State (readonly)
    precision: computed(() => precision.value),
    useGrouping: computed(() => useGrouping.value),
    locale: computed(() => locale.value),
    formatOptions,

    // Methods
    formatNumber,
    formatCurrency,
    formatPercentage,
    setPrecision,
    toggleGrouping,
    setLocale
  }
}

/**
 * Composable for time formatting.
 * Demonstrates: simpler composable, pure functions
 */
export function useTimeFormatter() {
  const formatTime = (date: Date): string => {
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  }

  const formatDate = (date: Date): string => {
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    })
  }

  const formatDateTime = (date: Date): string => {
    return `${formatDate(date)} ${formatTime(date)}`
  }

  const getRelativeTime = (date: Date): string => {
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffSecs = Math.floor(diffMs / 1000)
    const diffMins = Math.floor(diffSecs / 60)
    const diffHours = Math.floor(diffMins / 60)
    const diffDays = Math.floor(diffHours / 24)

    if (diffSecs < 60) return 'just now'
    if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`
    return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`
  }

  return {
    formatTime,
    formatDate,
    formatDateTime,
    getRelativeTime
  }
}

/**
 * Type definitions for return types
 */
export type UseFormatterReturn = ReturnType<typeof useFormatter>
export type UseTimeFormatterReturn = ReturnType<typeof useTimeFormatter>
