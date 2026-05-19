; zp.s -- defines the zero-page allocations declared in zp.inc

.segment "ZEROPAGE"

.exportzp ptr1, ptr2, tmp1

ptr1:   .res 2
ptr2:   .res 2
tmp1:   .res 1
