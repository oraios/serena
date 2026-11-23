// SPDX-License-Identifier: MIT
export interface Shape {
  area(): number
}

export class Square implements Shape {
  constructor(private side: number) {}

  area(): number {
    return this.side * this.side
  }
}

export interface CrossFileShape {
  perimeter(): number
}

export interface UnimplementedShape {
  missing(): void
}
