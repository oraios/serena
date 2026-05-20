; helpers.s -- scope, nested procs, macro, struct
;
; Exercises:
;   .scope ... .endscope     (named scope)
;   .proc nested inside scope
;   .macro definition and invocation
;   .struct with field access (Struct::field syntax)
;   cheap-local labels (@foo)

.include "zp.inc"

.struct S
        flags   .byte
        count   .word
.endstruct

.macro mac1 arg
        lda     #arg
        sta     ptr1
.endmacro

.segment "CODE"

.scope helpers

.proc foo
        mac1    $42                 ; macro invocation
        jsr     bar                 ; intra-scope call -> helpers::bar
@inner:                             ; cheap local, scoped to foo
        lda     #S::flags           ; struct field reference
        bne     @inner
        rts
.endproc

.proc bar
@inner:                             ; cheap local @inner here is DISTINCT from foo's @inner
        lda     #$02
        sta     tmp1
        rts
.endproc

.endscope

; Re-export the scoped names under shorter aliases so other modules can .import
; them without needing the helpers:: prefix on the import side.
.export helpers_foo := helpers::foo
.export helpers_bar := helpers::bar
