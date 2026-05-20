; main.s -- entry point exercising cross-module .import and anonymous labels

.include "zp.inc"

.import helpers_foo
.import helpers_bar
.import lib_export
.import lib_buffer
.import lib_const

.segment "STARTUP"
.export _start

.proc _start
        jsr     lib_export
        jsr     helpers_foo
        lda     #<lib_const
        sta     ptr1
        lda     #>lib_const
        sta     ptr1+1

@retry:                                 ; cheap local in _start scope
        lda     lib_buffer
        bne     @retry

:       lda     #$00                    ; anonymous label
        cmp     ptr1
        bne     :-                      ; back-reference to the anonymous label above
        jmp     :+                      ; forward-reference to the next anonymous label
        nop
:       jsr     helpers_bar             ; second anonymous label, target of :+
        rts
.endproc
