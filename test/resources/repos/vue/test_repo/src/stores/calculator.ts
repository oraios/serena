import { defineStore } from 'pinia'
import type { HistoryEntry, Operation, CalculatorState } from '@/types'

export const useCalculatorStore = defineStore('calculator', {
  state: (): CalculatorState => ({
    currentValue: 0,
    previousValue: null,
    operation: null,
    history: [],
    displayValue: '0'
  }),

  getters: {
    /**
     * Get the most recent history entries (last 10)
     */
    recentHistory: (state): HistoryEntry[] => {
      return state.history.slice(-10).reverse()
    },

    /**
     * Check if calculator has any history
     */
    hasHistory: (state): boolean => {
      return state.history.length > 0
    },

    /**
     * Get the current display text
     */
    display: (state): string => {
      return state.displayValue
    }
  },

  actions: {
    /**
     * Set a number value
     */
    setNumber(value: number) {
      this.currentValue = value
      this.displayValue = value.toString()
    },

    /**
     * Append a digit to the current value
     */
    appendDigit(digit: number) {
      if (this.displayValue === '0') {
        this.displayValue = digit.toString()
      } else {
        this.displayValue += digit.toString()
      }
      this.currentValue = parseFloat(this.displayValue)
    },

    /**
     * Add two numbers
     */
    add() {
      if (this.previousValue !== null && this.operation) {
        this.executeOperation()
      }
      this.previousValue = this.currentValue
      this.operation = 'add'
      this.displayValue = '0'
    },

    /**
     * Subtract two numbers
     */
    subtract() {
      if (this.previousValue !== null && this.operation) {
        this.executeOperation()
      }
      this.previousValue = this.currentValue
      this.operation = 'subtract'
      this.displayValue = '0'
    },

    /**
     * Multiply two numbers
     */
    multiply() {
      if (this.previousValue !== null && this.operation) {
        this.executeOperation()
      }
      this.previousValue = this.currentValue
      this.operation = 'multiply'
      this.displayValue = '0'
    },

    /**
     * Divide two numbers
     */
    divide() {
      if (this.previousValue !== null && this.operation) {
        this.executeOperation()
      }
      this.previousValue = this.currentValue
      this.operation = 'divide'
      this.displayValue = '0'
    },

    /**
     * Execute the pending operation
     */
    executeOperation() {
      if (this.previousValue === null || this.operation === null) {
        return
      }

      let result = 0
      const prev = this.previousValue
      const current = this.currentValue
      let expression = ''

      switch (this.operation) {
        case 'add':
          result = prev + current
          expression = `${prev} + ${current}`
          break
        case 'subtract':
          result = prev - current
          expression = `${prev} - ${current}`
          break
        case 'multiply':
          result = prev * current
          expression = `${prev} × ${current}`
          break
        case 'divide':
          if (current === 0) {
            this.displayValue = 'Error'
            this.clear()
            return
          }
          result = prev / current
          expression = `${prev} ÷ ${current}`
          break
      }

      // Add to history
      this.history.push({
        expression,
        result,
        timestamp: new Date()
      })

      this.currentValue = result
      this.displayValue = result.toString()
      this.previousValue = null
      this.operation = null
    },

    /**
     * Calculate the equals operation
     */
    equals() {
      this.executeOperation()
    },

    /**
     * Clear the calculator state
     */
    clear() {
      this.currentValue = 0
      this.previousValue = null
      this.operation = null
      this.displayValue = '0'
    },

    /**
     * Clear all history
     */
    clearHistory() {
      this.history = []
    }
  }
})
