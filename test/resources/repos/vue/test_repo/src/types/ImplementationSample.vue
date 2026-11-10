<!-- SPDX-License-Identifier: MIT -->
<script lang="ts">
import type { CrossFileShape } from './implementation_sample'

export interface EmbeddedShape {
  area(): number
}

export class EmbeddedSquare implements EmbeddedShape {
  area(): number {
    return 4
  }
}

export class VueRectangle implements CrossFileShape {
  perimeter(): number {
    return 8
  }
}

export default {}
</script>

<template>
  <div />
</template>
