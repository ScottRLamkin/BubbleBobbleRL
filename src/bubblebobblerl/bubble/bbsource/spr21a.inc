;----------------------------------------------------------------------------
;[ PutSprClpAND ] [ABCDEFIX]                      [ 139 bytes ] [ CrASH_Man ]
;----------------------------------------------------------------------------
; Draws a sprite using only AND data, with clipping
;
; parameters: HL -> sprite, (B,C) = coordinates
; returns:    Puts sprite in GRAPH_MEM
;
PutSprClpAND:   XOR  A
__XChange_1:    LD   DE, DefaultXSpriteHeight     ; D = 0, E = Height

                OR   C                            ; If C < 0
                JP   M, _SCX_NoBotClp             ; No bottom clip.

                LD   A, $3F                       ; Is C is offscreen?
                SUB  C
                RET  C

__XChange_2:    CP   DefaultXSpriteHeight-1       ; If C + 7 < 64
                JR   NC, _SCX_NoVertClp           ; No vertical clip.
                INC  A
                LD   E, A
                JR   _SCX_NoVertClp               ; Height = 64 - C

_SCX_NoBotClp:
__XChange_3:    CP   -(DefaultXSpriteHeight-1)    ; Is C is offscreen?
                RET  C

                ADD  A, E                         ; Find how many lines
                LD   C, A                         ; to actually draw
                SUB  E

                NEG
                LD   E, A
                ADD  HL, DE                       ; Move HL down
                LD   E, C                         ; by -C lines
                LD   C, D

_SCX_NoVertClp: PUSH HL                           ; IX -> Sprite
                POP  IX

                LD   A, $77                       ; OP code for
                LD   (_SCX_OPchg_1), A            ;   LD   (HL), A
                LD   (_SCX_OPchg_2), A

                 XOR  A                            ; Is B > 0?
                 OR   B
                JP   M, _SCX_NoRightClp

                CP   89                           ; Is B < 89?
                JR   C, _SCX_ClpDone
                CP   96
                RET  NC

                LD   HL, _SCX_OPchg_1             ; Modify LD to NOP
                JR   _SCX_ClpModify

_SCX_NoRightClp:CP   -7                           ; Is B is offscreen?
                RET  C

                LD   HL, _SCX_OPchg_2             ; Modify LD to NOP
_SCX_ClpModify: LD   (HL), D

_SCX_ClpDone:   LD   B, D
                LD   H, B
                LD   L, C
                ADD  HL, BC                       ; HL = Y * 12
                ADD  HL, BC
                ADD  HL, HL
                ADD  HL, HL

                LD   C, A                         ; HL = Y*12 + X/8
                SRA  C
                SRA  C
                SRA  C
                INC  C

                ADD  HL, BC
                LD   BC, GRAPH_MEM
                ADD  HL, BC

                LD   B, E                         ; B = number of rows

                CPL
                AND  %00000111                    ; find number of
                LD   E, A                         ; instructions to jump
                ADD  A, E
                ADD  A, E
                LD   (_SCX_OPchg_3 + 1), A        ; 3 * (7 - number)

                LD   DE, 13

_SCX_LineLoop:  LD   C, (IX)
                ld a,255
                scf
_SCX_OPchg_3:   JR   _SCX_OPchg_3                 ; modify

                RR   C
                RRA
                RR   C
                RRA
                RR   C
                RRA
                RR   C
                RRA
                RR   C
                RRA
                RR   C
                RRA
                RR   C
                RRA

                and  (HL)                         ; AND with background
_SCX_OPchg_1:   LD   (HL), A                      ; Write
                DEC  HL                           ; HL -> next 8 pixels

                LD   A, C
                and  (HL)                         ; AND with background
_SCX_OPchg_2:   LD   (HL), A                      ; Write
                ADD  HL, DE                       ; HL -> next row

                INC  IX                           ; Increment to next data
                DJNZ _SCX_LineLoop
                RET

#IFNDEF NO_MOD_X
;----------------------------------------------------------------------------
;[ SetHeightAND ] [A]                              [ 13 bytes ] [ CrASH_Man ]
;----------------------------------------------------------------------------
; Changes the default sprite size for the AND routine
;
; parameters: A = New Sprite Height
; returns:    Self modified routine.
;
SetHeightAND:   LD   (__XChange_1+1), A
                DEC  A
                LD   (__XChange_2+1), A
                NEG
                LD   (__XChange_3+1), A
                RET
#ENDIF
