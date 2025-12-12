<script setup lang="ts">
import { computed, ref } from 'vue'

/**
 * Props interface for CalculatorButton.
 * Demonstrates: defineProps with TypeScript interface
 */
interface Props {
  label: string | number
  variant?: 'digit' | 'operation' | 'equals' | 'clear'
  disabled?: boolean
  active?: boolean
  size?: 'small' | 'medium' | 'large'
}

/**
 * Emits interface for CalculatorButton.
 * Demonstrates: defineEmits with TypeScript
 */
interface Emits {
  click: [value: string | number]
  hover: [isHovering: boolean]
  focus: []
  blur: []
}

// Define props with defaults
const props = withDefaults(defineProps<Props>(), {
  variant: 'digit',
  disabled: false,
  active: false,
  size: 'medium'
})

// Define emits
const emit = defineEmits<Emits>()

// Local state
const isHovered = ref(false)
const isFocused = ref(false)
const pressCount = ref(0)

// Computed classes based on props and state
const buttonClass = computed(() => {
  const classes = ['calc-button', `calc-button--${props.variant}`, `calc-button--${props.size}`]

  if (props.active) classes.push('calc-button--active')
  if (props.disabled) classes.push('calc-button--disabled')
  if (isHovered.value) classes.push('calc-button--hovered')
  if (isFocused.value) classes.push('calc-button--focused')

  return classes.join(' ')
})

// Computed aria label for accessibility
const ariaLabel = computed(() => {
  const variantText = {
    digit: 'Number',
    operation: 'Operation',
    equals: 'Equals',
    clear: 'Clear'
  }[props.variant]

  return `${variantText}: ${props.label}`
})

// Event handlers that emit events
const handleClick = () => {
  if (!props.disabled) {
    pressCount.value++
    emit('click', props.label)
  }
}

const handleMouseEnter = () => {
  isHovered.value = true
  emit('hover', true)
}

const handleMouseLeave = () => {
  isHovered.value = false
  emit('hover', false)
}

const handleFocus = () => {
  isFocused.value = true
  emit('focus')
}

const handleBlur = () => {
  isFocused.value = false
  emit('blur')
}

// Expose internal state for parent access via template refs
// Demonstrates: defineExpose
defineExpose({
  pressCount,
  isHovered,
  isFocused,
  simulateClick: handleClick
})
</script>

<template>
  <button
    :class="buttonClass"
    :disabled="disabled"
    :aria-label="ariaLabel"
    @click="handleClick"
    @mouseenter="handleMouseEnter"
    @mouseleave="handleMouseLeave"
    @focus="handleFocus"
    @blur="handleBlur"
  >
    <span class="calc-button__label">{{ label }}</span>
    <span v-if="pressCount > 0" class="calc-button__badge">{{ pressCount }}</span>
  </button>
</template>

<style scoped>
.calc-button {
  position: relative;
  padding: 1rem;
  font-size: 1.2rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  font-weight: 500;
}

.calc-button--small {
  padding: 0.5rem;
  font-size: 1rem;
}

.calc-button--medium {
  padding: 1rem;
  font-size: 1.2rem;
}

.calc-button--large {
  padding: 1.5rem;
  font-size: 1.5rem;
}

.calc-button--digit {
  background: white;
  color: #333;
}

.calc-button--digit:hover:not(:disabled) {
  background: #e0e0e0;
}

.calc-button--operation {
  background: #2196f3;
  color: white;
}

.calc-button--operation:hover:not(:disabled) {
  background: #1976d2;
}

.calc-button--operation.calc-button--active {
  background: #1565c0;
}

.calc-button--equals {
  background: #4caf50;
  color: white;
}

.calc-button--equals:hover:not(:disabled) {
  background: #45a049;
}

.calc-button--clear {
  background: #f44336;
  color: white;
}

.calc-button--clear:hover:not(:disabled) {
  background: #da190b;
}

.calc-button--disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.calc-button--hovered {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
}

.calc-button--focused {
  outline: 2px solid #2196f3;
  outline-offset: 2px;
}

.calc-button__label {
  display: block;
}

.calc-button__badge {
  position: absolute;
  top: -5px;
  right: -5px;
  background: #ff5722;
  color: white;
  border-radius: 50%;
  width: 20px;
  height: 20px;
  font-size: 0.7rem;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
