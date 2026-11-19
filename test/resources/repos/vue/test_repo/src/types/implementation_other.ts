// SPDX-License-Identifier: MIT
import type { CrossFileShape, Shape } from './implementation_sample'

export class Circle implements Shape {
  constructor(private radius: number) {}

  area(): number {
    return Math.PI * this.radius * this.radius
  }
}

export class Rectangle implements CrossFileShape {
  perimeter(): number {
    return 6
  }
}
