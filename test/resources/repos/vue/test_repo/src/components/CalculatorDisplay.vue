<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useCalculatorStore } from '@/stores/calculator'
import type { HistoryEntry } from '@/types'

// Get the calculator store
const store = useCalculatorStore()

// Use storeToRefs to get reactive references to store state
const { recentHistory, hasHistory, currentValue, operation } = storeToRefs(store)

// Local ref for display options
const showFullHistory = ref(false)
const maxHistoryItems = ref(5)

// Computed property for filtered history
const displayedHistory = computed((): HistoryEntry[] => {
  if (showFullHistory.value) {
    return recentHistory.value
  }
  return recentHistory.value.slice(0, maxHistoryItems.value)
})

// Format date for display
const formatDate = (date: Date): string => {
  return new Date(date).toLocaleTimeString()
}

// Format the current calculation status
const currentCalculation = computed((): string => {
  if (operation.value && store.previousValue !== null) {
    const opSymbol = {
      add: '+',
      subtract: '-',
      multiply: '×',
      divide: '÷'
    }[operation.value]
    return `${store.previousValue} ${opSymbol} ${currentValue.value}`
  }
  return currentValue.value.toString()
})

// Toggle history view
const toggleHistoryView = () => {
  showFullHistory.value = !showFullHistory.value
}

// Clear history handler
const clearHistory = () => {
  store.clearHistory()
}

// Check if history is empty
const isHistoryEmpty = computed((): boolean => {
  return !hasHistory.value
})
</script>

<template>
  <div class="calculator-display">
    <div class="current-calculation">
      <h3>Current Calculation</h3>
      <div class="calculation-value">
        {{ currentCalculation }}
      </div>
    </div>

    <div class="history-section">
      <div class="history-header">
        <h3>History</h3>
        <button
          v-if="hasHistory"
          @click="toggleHistoryView"
          class="btn-toggle"
        >
          {{ showFullHistory ? 'Show Less' : 'Show All' }}
        </button>
        <button
          v-if="hasHistory"
          @click="clearHistory"
          class="btn-clear-history"
        >
          Clear History
        </button>
      </div>

      <div v-if="isHistoryEmpty" class="empty-history">
        No calculations yet
      </div>

      <div v-else class="history-list">
        <div
          v-for="(entry, index) in displayedHistory"
          :key="`${entry.timestamp}-${index}`"
          class="history-item"
        >
          <span class="expression">{{ entry.expression }}</span>
          <span class="result">= {{ entry.result }}</span>
          <span class="timestamp">{{ formatDate(entry.timestamp) }}</span>
        </div>
      </div>

      <div v-if="!showFullHistory && recentHistory.length > maxHistoryItems" class="history-count">
        Showing {{ maxHistoryItems }} of {{ recentHistory.length }} entries
      </div>
    </div>
  </div>
</template>

<style scoped>
.calculator-display {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding: 1rem;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.current-calculation {
  padding: 1rem;
  background: #e3f2fd;
  border-radius: 4px;
}

.current-calculation h3 {
  margin: 0 0 0.5rem 0;
  font-size: 1rem;
  color: #1976d2;
}

.calculation-value {
  font-size: 1.5rem;
  font-weight: bold;
  color: #333;
}

.history-section {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.history-header {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.history-header h3 {
  margin: 0;
  flex: 1;
}

.btn-toggle,
.btn-clear-history {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9rem;
}

.btn-toggle {
  background: #2196f3;
  color: white;
}

.btn-toggle:hover {
  background: #1976d2;
}

.btn-clear-history {
  background: #f44336;
  color: white;
}

.btn-clear-history:hover {
  background: #da190b;
}

.empty-history {
  padding: 2rem;
  text-align: center;
  color: #999;
  font-style: italic;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.history-item {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  gap: 1rem;
  padding: 0.75rem;
  background: #f5f5f5;
  border-radius: 4px;
  align-items: center;
}

.expression {
  font-weight: 500;
}

.result {
  font-weight: bold;
  color: #4caf50;
}

.timestamp {
  font-size: 0.8rem;
  color: #666;
  text-align: right;
}

.history-count {
  text-align: center;
  font-size: 0.9rem;
  color: #666;
  padding: 0.5rem;
}
</style>
