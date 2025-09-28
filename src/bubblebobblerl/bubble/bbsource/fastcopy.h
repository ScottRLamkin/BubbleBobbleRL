;-----> Copy the gbuf to the screen (fast)
;Input:	nothing
;Output:graph buffer is copied to the screen
fastCopy:
	di
	ld	a,$80				; 7
	nop
	out	($10),a				; 11
	ld	hl,gbuf-12-(-(12*64)+1)		; 10
	ld	a,$20				; 7
	ld	c,a				; 4
	inc	hl				; 6 waste
	dec	hl				; 6 waste
fastCopyAgain:
	ld	b,64				; 7
	inc	c				; 4
	ld	de,-(12*64)+1			; 10
	nop
	out	($10),a				; 11
	add	hl,de				; 11
	ld	de,10				; 10
fastCopyLoop:
	add	hl,de				; 11
	inc	hl				; 6 waste
	inc	hl				; 6 waste
	inc	de				; 6
	ld	a,(hl)				; 7
	nop
	out	($11),a				; 11
	dec	de				; 6
	djnz	fastCopyLoop			; 13/8
	ld	a,c				; 4
	cp	$2B+1				; 7
	jr	nz,fastCopyAgain		; 10/1
	ret					; 10
; Critical timings:
;	command->command: 65
;	command->value  : 68
;	value  ->value  : 66
;	value  ->command: 67
