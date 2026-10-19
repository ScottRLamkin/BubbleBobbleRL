;-----> Draw a picture
;Input:	ix->sprite
;	a=x
;	l=y
;	b=height	(in pixels)
;	c=width		(in bytes, e.g. 2 would be 16)
;Output: nothing
; All registers are destroyed except bc', de', hl'
largeSprite:
	di
	ex	af,af'
	ld	a,c
	push	af
	ex	af,af'
	ld	e,l
	ld	h,$00
	ld	d,h
	add	hl,de
	add	hl,de
	add	hl,hl
	add	hl,hl
	ld	e,a
	and	$07
	ld	c,a
	srl	e
	srl	e
	srl	e
	add	hl,de
	ld	de,graph_mem
	add	hl,de
largeSpriteLoop1:
	push	hl
largeSpriteLoop2:
	ld	d,(ix)
	ld	e,$00
	ld	a,c
	or	a
	jr	z,largeSpriteSkip1
largeSpriteLoop3:
	srl	d
	rr	e
	dec	a
	jr	nz,largeSpriteLoop3
largeSpriteSkip1:
	ld	a,(hl)
	xor	d
	ld	(hl),a
	inc	hl
	ld	a,(hl)
	xor	e
	ld	(hl),a
	inc	ix
	ex	af,af'
	dec	a
	push	af
	ex	af,af'
	pop	af
	jr	nz,largeSpriteLoop2
	pop	hl
	pop	af
	push	af
	ex	af,af'
	ld	de,$0C
	add	hl,de
	djnz	largeSpriteLoop1
	pop	af
	ret
