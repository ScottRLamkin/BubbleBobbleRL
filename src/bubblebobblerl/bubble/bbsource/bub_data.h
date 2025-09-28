#IFNDEF APP

;Information About 'Level':
;==============================
;   384 bytes, 1 byte>tile
;
;   0=wall, 1-4 = airspace
;1= Up, 2=Left, 3=Right, 4=Down
;==============================

#ifdef CRASH
Level: .fill 384,0
#else
level = saferam2
#endif
map = level

;Background Graphics:
Tile:
	.db %11111111
	.db %10001000
	.db %10011001
	.db %10111011

	.db %11111111
	.db %10001111
	.db %10011111
	.db %10111111

	.db %11111111
	.db %11111000
	.db %11111001
	.db %11111011

	.db %11111111
	.db %11111111 
	.db %11111111
	.db %11111111


;Information about sprite table:
;===============================================\
; 0   | 1   | 2   | 3   | 4   | 5   | 6   | 7   |
;-----+-----+-----+-----+-----+-----+-----+-----|
; Xpos| Ypos| Gfx | Obj | VarA| VarB| VarC|Flags|
;===============================================/
;                   Flags                      |
;===============================================\
; 0   | 1   | 2   | 3   | 4   | 5   | 6   | 7   |
;-----+-----+-----+-----+-----+-----+-----+-----|
;     |Right|Left |Down |Up   |Pop/L|Fast |Death|
;===============================================/

SpriteTable: .fill SpriteTotal*8,0
BigspriteY:  .db 0
BigspriteX:  .db 0
BigSprite: .fill 32,0
EndOfSprites:

;Keys Pressed Table
Keys:
jJumpPress:   .db 0
jBubblePress: .db 0	
jLeft:        .db 0
jRight:       .db 0
jJump:        .db 0
jBubble:      .db 0
JLR:          .db 0

P2Keys: .db 0,0,0,0,0,0,0

SavedFlag:		.db 0

StartLevel:   .db 0
ContinueLevel: .db 0
TodaysRecord:	.db 0

Unused1: .dw 0

Vars:

ScoreUpdateFlag: .db 0

Score:        .dw 0,0
Lives:        .db 0

Extend:       .db 0
ExtendFlags:  .db 0

PopUpScore:		.dw 0
PopUpX:   .db 0
PopUpY:		.db 0
PopUpLife: .db 0

Credits:      .db 0

Timer:        .db 0
Timer2:       .db 0
Enemycount:   .db 0

CurBonusFruit:   .db 0

PlayerInvincible: .db 0

PopCount:     .db 0
FruitCount:   .db 0

PopTime: .db 0

OnLevel:      .db 0
LinkGame: .db 0

BonusFlags:   .db %00000000
BonusCounter: .db $00
b_candy = 0
b_shoes = 1
b_cane = 2
b_cross = 3
b_potion = 4
b_umbrella = 5
b_door = 6
b_thunderpotion = 7
b_levmask =   %00100011
b_deathmask = %00111100

MonsterTime:  .db 0

Holes:        .db 0
Ammo:         .db 0

Hurry:        .db 0
Barron:       .db 0

backuphl = op1

EndOfVars:
Halts: .db 0
SuperGame: .db 0

#ENDIF

#IFDEF HIGHSCORE
#IFDEF APP\DefaultHighscoreTable:\#ELSE\HighscoreTable:\#ENDIF
	.db "Bub   ", 0,$90,$D0,$03,$00,50
	.db "Bob   ", 0,$A0,$86,$01,$00,40
	.db "Skel  ", 0,$50,$C3,$00,$00,30
	.db "Monsta", 0,$A8,$61,$00,$00,20
	.db "Dwedit", 0,$88,$13,$00,$00,10
#IFNDEF APP\EndOfHighScores:\#ENDIF
#ENDIF

tGameOver: .db "Game Over!",0
tCredits:  .db "Credits: ",0
tContinue: .db "Continue",0
tEnd:      .db "End",0

;;;;;;;;;;;;;;;;0123456789012345678901234

tBadEnd1:  .db "BAD END!",0
tBadEnd2:  .db "This is not a true ending!",0
#IFDEF ENDING
tBadEnd3:  .db "Try again with your FRIEND.",0
tBadEnd4:  .db "Cheating is bad, mmmkay?",0
tHappyEnd: .db "HAPPY END!",0

tSuperUnlocked: .db "Super Mode unlocked!",0

#ENDIF



tSelect:   .db "Select a round:",0
tGameMode:   .db "Game Mode:",0
tNormal:   .db "Normal",0
tSuper:   .db "Super",0


#IFDEF LINK
#IFNDEF LESSTEXT
;            012345678901234567890123
tLink0: .db "Link Game",0

tLink1: .db "Waiting for the other player",0
tLink2: .db "to join the game...",0
tLink2b: .db "to rejoin the game...",0

tLink3: .db "Note: If the game 'freezes'",0
tLink4: .db "during linkplay, just hold",0
tLink5: .db "CLEAR to return to the main",0
tLink6: .db "menu.",0

tLink7: .db "Connection successful.",0
tLink8: .db "Now waiting for Player 1",0
tLink9: .db "to select a level.",0

tHi1: .db "Waiting for both players",0
tHi2: .db "to enter high scores...",0
#ELSE
tLink0: .db "Waiting for other player...",0
tLink7: .db "Waiting for level selection",0
tHi1: .db "player entering hiscore...",0
#ENDIF


;tWaitLevel: .db "Waiting for level selection",0
;tPleaseWait: .db "Please Wait...",0

tLinkError: .db "Link Error",0
#ENDIF

#IFNDEF NOINFO
tAbout1: .db "Game by Dan Weiss (Dwedit)",0
tAbout2: .db "(c) 2001, 2002 - ",GAMEVERSION,0
tEmail1: .db "Email:",0
tEmail2: .db "bubble@dwedit.cjb.net",0
tURL:    .db "Web:  http://www.bub83.tk",0
tAIM:    .db "AIM: Dwedit403",0

tInstructions1: .db "Instructions:",0

tInstructions2: .db "- Use arrow keys to move.",0
tInstructions3: .db "- Press Alpha or Up to jump.",0
tInstructions4: .db "- Press 2nd to blow bubbles.",0
tInstructions5: .db "- Trap the enemies inside",0
tInstructions6: .db "bubbles and pop them!",0

tInstructions8: .db "- Pop at least 3 enemies",0
tInstructions9: .db "simultaneously for EXTEND",0
tInstructionsA: .db "letters.  Spell EXTEND and",0
tInstructionsB: .db "get an extra life!",0
tInstructions7: .db "- Press CLEAR to save & quit.",0

tCast:   .db "--Cast--",0

tEnemy1: .db "Bubble Buster",0
tEnemy2: .db "Stoner",0
tEnemy3: .db "Beluga",0
tEnemy4: .db "Hullaballoon",0
tEnemy5: .db "Banebou",0
tEnemy6: .db "Hidegonzu",0
tEnemy9: .db "Super"
tEnemy7: .db "Drunk",0
tEnemy8: .db "Invader",0
tBub:    .db "Bub",0

#ENDIF

tSpeed1: .db "Select Game Speed:",0
tSpeed2: .db "(0 is fastest, normal speed)",0
tSpeed3: .db "Speed:",0

;tTodaysRecord: .db "Today's record is: LV",0

;tStory: .db "Now it is beginning",0
;        .db "of a fantastic story!",0
;        .db "Let us make a journey",0
;        .db "to the cave of monsters!",0
;        .db "GOOD LUCK!",0