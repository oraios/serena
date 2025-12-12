/**
 * Represents a single calculation in the history
 */
export interface HistoryEntry {
  expression: string
  result: number
  timestamp: Date
}

/**
 * Valid calculator operations
 */
export type Operation = 'add' | 'subtract' | 'multiply' | 'divide' | null

/**
 * The complete state of the calculator
 */
export interface CalculatorState {
  currentValue: number
  previousValue: number | null
  operation: Operation
  history: HistoryEntry[]
  displayValue: string
}

/**
 * Format options for displaying numbers
 */
export interface FormatOptions {
  maxDecimals?: number
  useGrouping?: boolean
}
