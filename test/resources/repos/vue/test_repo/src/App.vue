<script setup lang="ts">
import { ref, computed, watch, watchEffect, onMounted } from 'vue'
import { useCalculatorStore } from '@/stores/calculator'
import { useThemeProvider } from '@/composables/useTheme'
import { useTimeFormatter } from '@/composables/useFormatter'
import CalculatorInput from '@/components/CalculatorInput.vue'
import CalculatorDisplay from '@/components/CalculatorDisplay.vue'

// Get the calculator store
const store = useCalculatorStore()

// Use theme composable with provide/inject - provides theme to all child components
const themeManager = useThemeProvider()

// Use time formatter composable
const timeFormatter = useTimeFormatter()

// Local ref for app title
const appTitle = ref('Vue Calculator')

// Computed property for app version
const appVersion = computed((): string => {
  return '1.0.0'
})

// Computed property for greeting message
const greetingMessage = computed((): string => {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
})

// Get statistics from store
const totalCalculations = computed((): number => {
  return store.history.length
})

// Check if calculator is active
const isCalculatorActive = computed((): boolean => {
  return store.currentValue !== 0 || store.previousValue !== null
})

// Get last calculation time
const lastCalculationTime = computed((): string => {
  if (store.history.length === 0) return 'No calculations yet'
  const lastEntry = store.history[store.history.length - 1]
  return timeFormatter.getRelativeTime(lastEntry.timestamp)
})

// Watch for calculation count changes - demonstrates watchEffect
watchEffect(() => {
  document.title = `Calculator (${totalCalculations.value} calculations)`
})

// Watch for theme changes - demonstrates watch
watch(
  () => themeManager.isDarkMode.value,
  (isDark) => {
    console.log(`Theme changed to ${isDark ? 'dark' : 'light'} mode`)
  }
)

// Lifecycle hook
onMounted(() => {
  console.log('App component mounted')
  console.log(`Initial calculations: ${totalCalculations.value}`)
})

// Toggle theme method
const toggleTheme = () => {
  themeManager.toggleDarkMode()
}

<template>
  <div :class="['app', { 'dark-mode': themeManager.isDarkMode }]">
    <header class="app-header">
      <h1>{{ appTitle }}</h1>
      <div class="header-info">
        <span class="greeting">{{ greetingMessage }}!</span>
        <span class="version">v{{ appVersion }}</span>
        <button @click="toggleTheme" class="btn-theme">
          {{ themeManager.isDarkMode ? '☀️' : '🌙' }}
        </button>
      </div>
    </header>

    <main class="app-main">
      <div class="calculator-container">
        <div class="stats-bar">
          <span>Total Calculations: {{ totalCalculations }}</span>
          <span :class="{ 'active-indicator': isCalculatorActive }">
            {{ isCalculatorActive ? 'Active' : 'Idle' }}
          </span>
          <span class="last-calc-time">{{ lastCalculationTime }}</span>
        </div>

        <div class="calculator-grid">
          <CalculatorInput />
          <CalculatorDisplay />
        </div>
      </div>
    </main>

    <footer class="app-footer">
      <p>Built with Vue 3 + Pinia + TypeScript</p>
    </footer>
  </div>
</template>

<style scoped>
.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  transition: background 0.3s ease;
}

.app.dark-mode {
  background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
}

.app-header {
  padding: 2rem;
  color: white;
  text-align: center;
}

.app-header h1 {
  margin: 0 0 1rem 0;
  font-size: 2.5rem;
}

.header-info {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 1rem;
}

.greeting {
  font-size: 1.1rem;
}

.version {
  font-size: 0.9rem;
  opacity: 0.8;
}

.btn-theme {
  background: rgba(255, 255, 255, 0.2);
  border: none;
  border-radius: 50%;
  width: 40px;
  height: 40px;
  font-size: 1.2rem;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-theme:hover {
  background: rgba(255, 255, 255, 0.3);
}

.app-main {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 2rem;
}

.calculator-container {
  width: 100%;
  max-width: 1200px;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.stats-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 8px;
  font-weight: 500;
}

.last-calc-time {
  font-size: 0.9rem;
  color: #666;
  font-style: italic;
}

.active-indicator {
  color: #4caf50;
  font-weight: bold;
}

.active-indicator:not(.active-indicator) {
  color: #999;
}

.calculator-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2rem;
}

@media (max-width: 768px) {
  .calculator-grid {
    grid-template-columns: 1fr;
  }
}

.app-footer {
  padding: 1rem;
  text-align: center;
  color: white;
  opacity: 0.8;
}

.app-footer p {
  margin: 0;
}
</style>
