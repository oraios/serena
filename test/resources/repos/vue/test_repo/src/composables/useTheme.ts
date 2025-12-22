import { ref, computed, watch, inject, provide, type InjectionKey, type Ref } from 'vue'

/**
 * Theme configuration type
 */
export interface ThemeConfig {
  isDark: boolean
  primaryColor: string
  fontSize: number
}

/**
 * Injection key for theme - demonstrates provide/inject pattern
 */
export const ThemeKey: InjectionKey<Ref<ThemeConfig>> = Symbol('theme')

/**
 * Composable for theme management with watchers.
 * Demonstrates: watch, provide/inject, localStorage interaction
 */
export function useThemeProvider() {
  // Initialize theme from localStorage or defaults
  const loadThemeFromStorage = (): ThemeConfig => {
    const stored = localStorage.getItem('app-theme')
    if (stored) {
      try {
        return JSON.parse(stored)
      } catch {
        // Fall through to defaults
      }
    }
    return {
      isDark: false,
      primaryColor: '#667eea',
      fontSize: 16
    }
  }

  const theme = ref<ThemeConfig>(loadThemeFromStorage())

  // Computed properties
  const isDarkMode = computed(() => theme.value.isDark)
  const themeClass = computed(() => theme.value.isDark ? 'dark-theme' : 'light-theme')

  // Watch for theme changes and persist to localStorage
  watch(
    theme,
    (newTheme) => {
      localStorage.setItem('app-theme', JSON.stringify(newTheme))
      document.documentElement.className = newTheme.isDark ? 'dark' : 'light'
    },
    { deep: true }
  )

  // Methods
  const toggleDarkMode = (): void => {
    theme.value.isDark = !theme.value.isDark
  }

  const setPrimaryColor = (color: string): void => {
    theme.value.primaryColor = color
  }

  const setFontSize = (size: number): void => {
    if (size >= 12 && size <= 24) {
      theme.value.fontSize = size
    }
  }

  const resetTheme = (): void => {
    theme.value = {
      isDark: false,
      primaryColor: '#667eea',
      fontSize: 16
    }
  }

  // Provide theme to child components
  provide(ThemeKey, theme)

  return {
    theme,
    isDarkMode,
    themeClass,
    toggleDarkMode,
    setPrimaryColor,
    setFontSize,
    resetTheme
  }
}

/**
 * Composable for consuming theme in child components.
 * Demonstrates: inject pattern
 */
export function useTheme() {
  const theme = inject(ThemeKey)

  if (!theme) {
    throw new Error('useTheme must be used within a component that provides ThemeKey')
  }

  const isDark = computed(() => theme.value.isDark)
  const primaryColor = computed(() => theme.value.primaryColor)
  const fontSize = computed(() => theme.value.fontSize)

  return {
    theme,
    isDark,
    primaryColor,
    fontSize
  }
}
