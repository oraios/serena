; lib.s -- exports a routine, a constant, and a BSS buffer

.include "zp.inc"

.export lib_export
.export lib_buffer
.export lib_const := $1234

.segment "BSS"
lib_buffer:
        .res 256

.segment "CODE"
.proc lib_export
        lda     #$00
        sta     tmp1
        rts
.endproc
