#IFDEF HIGHSCORE
DefaultHighscoreTable:
	.db "Bub   ", 0,$90,$D0,$03,$00,50
	.db "Bob   ", 0,$A0,$86,$01,$00,40
	.db "Skel  ", 0,$50,$C3,$00,$00,30
	.db "Monsta", 0,$A8,$61,$00,$00,20
	.db "Dwedit", 0,$88,$13,$00,$00,10
#ENDIF



tGameOver: .db "Game Over!",0
tCredits:  .db "Credits: ",0
tContinue: .db "Continue",0
tEnd:      .db "End",0
tBadEnd1:  .db "BAD END!",0
tBadEnd2:  .db "This is not a true ending!",0
tSelect:   .db "Select a round:",0
#IFDEF LINK
tLink1:      .db "Waiting for the other player..",0
tWaitLevel:  .db "Waiting for level selection",0
tPleaseWait: .db "Please Wait...",0
tLinkError:  .db "Link Error",0
#ENDIF


;tTodaysRecord: .db "Today's record is: LV",0

;tStory: .db "Now it is beginning",0
;        .db "of a fantastic story!",0
;        .db "Let us make a journey",0
;        .db "to the cave of monsters!",0
;        .db "GOOD LUCK!",0