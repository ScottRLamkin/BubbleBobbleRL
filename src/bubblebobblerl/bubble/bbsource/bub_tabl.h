ScoreTable:
	.dw 70 ;Generic Item
	.dw 500 ;Diamond 1
	.dw 400 ;Diamond 2
HugeItemScoreTable:
	.dw 1000
	.dw 2000
	.dw 3000
	.dw 5000
	.dw 10000
;Cherry:
	.dw 50    ;500
	.dw 100   ;1000
	.dw 200   ;2000
	.dw 300   ;3000
	.dw 400   ;4000
	.dw 500   ;5000
	.dw 600   ;6000
	.dw 700   ;7000
TimeScoreTable:
	.dw 2     ;0
	.dw 15    ;1
	.dw 30    ;2
	.dw 50		;3
	.dw 100   ;4
	.dw 200		;5
	.dw 300		;6
	.dw 400		;7
	.dw 500		;8
	.dw 600		;9
	.dw 700 	;a
	.dw 800 	;b
	.dw 900 	;c
	.dw 1000	;d
	.dw 1250	;e
	.dw 2500	;f
BonusScoreTable:

PopScoreTable:
	.dw 50    ;500
	.dw 100   ;1000
	.dw 200   ;2000
	.dw 400   ;4000
	.dw 800   ;8000
	.dw 1600  ;16000
	.dw 3200  ;32000
	.dw 6400  ;64000

SpecialItemScoreTable:
	.dw 10    ;Candy
	.dw 15    ;Shoes
	.dw 50    ;Cane
	.dw 500   ;Cross
	.dw 0     ;Potion
	.dw 20    ;Umbrella
	.dw 100   ;Door
	.dw 250   ;Thunderpotion

;BonusLifeTable:
;	.db $B8,$0B,0,0
;	.db $10,$27,0,0
;	.db $40,$9C,0,0
;	.db $80,$38,$01,0



DefaultBubTable:	.db  8,52,1,1
DefaultBobTable:	.db 80,52,5,1

ExpTable:
	.db %00000001
	.db %00000010
	.db %00000100
	.db %00001000
	.db %00010000
	.db %00100000
	.db %01000000
	.db %10000000

#ifndef WIDE16
Keytable:
	.db "dlru...." ;dn,lf,rt,up,__,__,__,__
	.db "E+wrmhC." ;en,+ ,- ,* ,/ ,^ ,cl,__
	.db "-[vqlg!." ; -,3 ,6 ,9 ,) ,ta,va,__
	.db ".zupkfc," ;. ,2 ,5 ,8 ,( ,co,pr,st
	.db " ytojebx" ;0 ,1 ,4 ,7 ,, ,si,mx,xt
	.db ".xsnidaA" ;__,> ,ln,lg,x2,x1,mt,AL
	.db "54321",18
	.db       "^D" ;gr,tr,zo,wi,Y=,2n,mo,de
;ALPHA table
	.db "DLRU...." ;dn,lf,rt,up,__,__,__,__
	.db "e",34     ;en,+ ,
	.db   "WRMHc." ;      - ,* ,/ ,^ ,cl,__
	.db "?[VQLG!." ; -,3 ,6 ,9 ,) ,ta,va,__
	.db ":ZUPKFC," ;. ,2 ,5 ,8 ,( ,co,pr,st
	.db " YTOJEBX" ;0 ,1 ,4 ,7 ,, ,si,mx,xt
	.db ".XSNIDAa" ;__,> ,ln,lg,x2,x1,mt,AL
	.db "098762^d" ;gr,tr,zo,wi,Y=,2n,mo,de
#else ;ti85
Keytable:
	.db "dlru...." ;dn,lf,rt,up,__,__,__,__
	.db "ExtojeC." ;en,+ ,- ,* ,/ ,^ ,cl,__
	.db " wsnid!." ; -,3 ,6 ,9 ,) ,ta,va,__
	.db "zvrmhc!." ;. ,2 ,5 ,8 ,( ,co,pr,st
	.db "yuqlgb!x" ;0 ,1 ,4 ,7 ,, ,si,mx,xt
	.db ".=pkfa!A" ;__,> ,ln,lg,x2,x1,mt,AL
	.db "543212^D" ;gr,tr,zo,wi,Y=,2n,mo,de
;ALPHA table
	.db "DLRU...." ;dn,lf,rt,up,__,__,__,__
	.db "eXTOJEc." ;en,+ ,- ,* ,/ ,^ ,cl,__
	.db " WSNID!." ; -,3 ,6 ,9 ,) ,ta,va,__
	.db "ZVRMHC!d" ;. ,2 ,5 ,8 ,( ,co,pr,st
	.db "YUQLGB!X" ;0 ,1 ,4 ,7 ,, ,si,mx,xt
	.db ".=PKFA!a" ;__,> ,ln,lg,x2,x1,mt,AL
	.db "098762^." ;gr,tr,zo,wi,Y=,2n,mo,de
#endif



#IFDEF ENDING
TrappedGrilCircleTable:
	.db 1,0
	.db 1,0
	.db 1,1
	.db 1,1
	.db 0,1
	.db 0,1
	.db -1,1
	.db -1,1
	.db -1,0
	.db -1,0
	.db -1,-1
	.db -1,-1
	.db 0,-1
	.db 0,-1
	.db 1,-1
	.db 1,-1

TrappedGrilCircleTable2:
	.db -1,0
	.db -1,0
	.db -1,1
	.db -1,1
	.db 0,1
	.db 0,1
	.db 1,1
	.db 1,1
	.db 1,0
	.db 1,0
	.db 1,-1
	.db 1,-1
	.db 0,-1
	.db 0,-1
	.db -1,-1
	.db -1,-1

#ENDIF

#IFDEF EXPORT
.export BonusScoreTable
.export DefaultBobTable
.export DefaultBubTable
.export ExpTable
.export HugeItemScoreTable
.export Keytable
.export PopScoreTable
.export ScoreTable
.export SpecialItemScoreTable
.export TimeScoreTable

#IFDEF ENDING
.export TrappedGrilCircleTable
.export TrappedGrilCircleTable2
#ENDIF

#endif ;export