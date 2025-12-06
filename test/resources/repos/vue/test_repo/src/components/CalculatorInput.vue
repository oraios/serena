<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useCalculatorStore } from '@/stores/calculator'
import { useFormatter } from '@/composables/useFormatter'
import CalculatorButton from './CalculatorButton.vue'
import type { Operation } from '@/types'

// Get the calculator store
const store = useCalculatorStore()

// Use composable for formatting
const formatter = useFormatter(2)

// Local refs for component state
const isOperationPending = ref(false)
const lastOperation = ref<Operation>(null)
const keyboardEnabled = ref(true)
const operationHistory = ref<string[]>([])

// Template refs - demonstrates template ref pattern
const displayRef = ref<HTMLDivElement | null>(null)
const equalsButtonRef = ref<InstanceType<typeof CalculatorButton> | null>(null)

// Computed property for button styling
const getOperationClass = computed(() => (op: Operation) => {
  return lastOperation.value === op ? 'active' : ''
})

// Computed formatted display value using composable
const formattedDisplay = computed(() => {
  const value = parseFloat(store.display)
  return isNaN(value) ? store.display : formatter.formatNumber(value)
})

// Watch for operation changes - demonstrates watch
watch(lastOperation, (newOp, oldOp) => {
  if (newOp !== oldOp && newOp) {
    operationHistory.value.push(newOp)
    // Keep only last 10 operations
    if (operationHistory.value.length > 10) {
      operationHistory.value.shift()
    }
  }
})

// Watch store display changes - demonstrates watch with callback
watch(
  () => store.display,
  (newDisplay) => {
    if (displayRef.value) {
      // Trigger animation on display change
      displayRef.value.classList.add('display-updated')
      setTimeout(() => {
        displayRef.value?.classList.remove('display-updated')
      }, 300)
    }
  }
)

// Lifecycle hook - demonstrates onMounted
onMounted(() => {
  console.log('CalculatorInput mounted')
  // Add keyboard event listener
  window.addEventListener('keydown', handleKeyboard)

  // Focus on the display element
  if (displayRef.value) {
    displayRef.value.focus()
  }
})

// Lifecycle hook - demonstrates onBeforeUnmount
onBeforeUnmount(() => {
  console.log('CalculatorInput unmounting')
  // Clean up keyboard event listener
  window.removeEventListener('keydown', handleKeyboard)
})

// Handle number button clicks
const handleDigit = (digit: number) => {
  store.appendDigit(digit)
  isOperationPending.value = false
}

// Handle operation button clicks
const handleOperation = (operation: Operation) => {
  isOperationPending.value = true
  lastOperation.value = operation

  switch (operation) {
    case 'add':
      store.add()
      break
    case 'subtract':
      store.subtract()
      break
    case 'multiply':
      store.multiply()
      break
    case 'divide':
      store.divide()
      break
  }
}

// Handle equals button
const handleEquals = () => {
  store.equals()
  isOperationPending.value = false
  lastOperation.value = null

  // Access exposed method from child component
  if (equalsButtonRef.value) {
    console.log('Equals button press count:', equalsButtonRef.value.pressCount)
  }
}

// Handle clear button
const handleClear = () => {
  store.clear()
  isOperationPending.value = false
  lastOperation.value = null
  operationHistory.value = []
}

// Keyboard handler - demonstrates event handling
const handleKeyboard = (event: KeyboardEvent) => {
  if (!keyboardEnabled.value) return

  const key = event.key

  if (key >= '0' && key <= '9') {
    handleDigit(parseInt(key))
  } else if (key === '+') {
    handleOperation('add')
  } else if (key === '-') {
    handleOperation('subtract')
  } else if (key === '*') {
    handleOperation('multiply')
  } else if (key === '/') {
    event.preventDefault()
    handleOperation('divide')
  } else if (key === 'Enter' || key === '=') {
    handleEquals()
  } else if (key === 'Escape' || key === 'c' || key === 'C') {
    handleClear()
  }
}

// Toggle keyboard input
const toggleKeyboard = () => {
  keyboardEnabled.value = !keyboardEnabled.value
}

// Array of digits for rendering
const digits = [7, 8, 9, 4, 5, 6, 1, 2, 3, 0]
</script>

<template>
  <div class="calculator-input">
    <div ref="displayRef" class="display" tabindex="0">
      {{ formattedDisplay }}
    </div>

    <div class="keyboard-toggle">
      <label>
        <input type="checkbox" v-model="keyboardEnabled" @change="toggleKeyboard" />
        Enable Keyboard Input
      </label>
    </div>

    <div class="buttons">
      <CalculatorButton
        v-for="digit in digits"
        :key="digit"
        :label="digit"
        variant="digit"
        @click="handleDigit"
      />

      <CalculatorButton
        label="+"
        variant="operation"
        :active="lastOperation === 'add'"
        @click="() => handleOperation('add')"
      />

      <CalculatorButton
        label="-"
        variant="operation"
        :active="lastOperation === 'subtract'"
        @click="() => handleOperation('subtract')"
      />

      <CalculatorButton
        label="×"
        variant="operation"
        :active="lastOperation === 'multiply'"
        @click="() => handleOperation('multiply')"
      />

      <CalculatorButton
        label="÷"
        variant="operation"
        :active="lastOperation === 'divide'"
        @click="() => handleOperation('divide')"
      />

      <CalculatorButton
        ref="equalsButtonRef"
        label="="
        variant="equals"
        size="large"
        @click="handleEquals"
      />

      <CalculatorButton
        label="C"
        variant="clear"
        @click="handleClear"
      />
    </div>

    <div v-if="isOperationPending" class="pending-indicator">
      Operation pending: {{ lastOperation }}
    </div>

    <div v-if="operationHistory.length > 0" class="operation-history">
      Recent operations: {{ operationHistory.join(', ') }}
    </div>
  </div>
</template>

<style scoped>
.calculator-input {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1rem;
  background: #f5f5f5;
  border-radius: 8px;
}

.display {
  font-size: 2rem;
  text-align: right;
  padding: 1rem;
  background: white;
  border-radius: 4px;
  min-height: 3rem;
  transition: background-color 0.3s;
  outline: none;
}

.display:focus {
  box-shadow: 0 0 0 2px #2196f3;
}

.display.display-updated {
  background-color: #e3f2fd;
}

.keyboard-toggle {
  display: flex;
  justify-content: center;
  padding: 0.5rem;
}

.keyboard-toggle label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-size: 0.9rem;
}

.buttons {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.5rem;
}

.pending-indicator {
  font-size: 0.9rem;
  color: #666;
  text-align: center;
  font-style: italic;
}

.operation-history {
  font-size: 0.8rem;
  color: #999;
  text-align: center;
  padding: 0.5rem;
  background: white;
  border-radius: 4px;
  max-height: 3rem;
  overflow: auto;
}
</style>
