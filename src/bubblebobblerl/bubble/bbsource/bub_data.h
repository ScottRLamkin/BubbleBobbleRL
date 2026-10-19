#IFDEF WIDE16
#define QUIT_BUTTON "EXIT"
#else
#define QUIT_BUTTON "CLEAR"
#endif

#IFNDEF APP

;Information About 'Level':
;==============================
;   384 bytes, 1 byte>tile
;
;   0=wall, 1-4 = airspace
;1= Up, 2=Left, 3=Right, 4=Down
;==============================

#ifdef CRASH
#define ALLOC_LEVEL
#endif
#ifdef TI85
#define ALLOC_LEVEL
#endif
#ifdef TI86
#define ALLOC_LEVEL
#endif

#ifdef ALLOC_LEVEL
level: .ds 384
#else
level = saferam2
#endif
map = level

;Background Graphics:
Tile:
	.ds 16
;	.db %11111111
;	.db %10001000
;	.db %10011001
;	.db %10111011
;
;	.db %11111111
;	.db %10001111
;	.db %10011111
;	.db %10111111
;
;	.db %11111111
;	.db %11111000
;	.db %11111001
;	.db %11111011
;
;	.db %11111111
;	.db %11111111 
;	.db %11111111
;	.db %11111111


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

SAVE_START86:
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
TodaysRecordSuper: .db 0
SuperUnlocked: .db 0
SuperGame: .db 0

RandSeed: .dw 0

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
Baron:       .db 0


backuphl = op1

EndOfVars:

#IFDEF EXTERNAL
WorldCount: .db 0
OnWorld: .db 0
oldmaproot = worldcount
MapRoot: .dw 0
levelpage: .db 0
LevelCount: .db 0
LoadedMap: .db 0,0,0,0,0,0,0,0,0,0

#ENDIF
#IFDEF SENDLEVELS
#IFNDEF EXTERNAL
levelcount: .db 0
#endif
#endif

Halts: .db 0

#ENDIF

#IFDEF TI86
 .ds 32  ;reserved
#endif


#IFDEF HIGHSCORE
#IFDEF APP\DefaultHighscoreTable:\#ELSE\HighscoreTable:\#ENDIF
#IFDEF WIDESCORES
	.db "Bub        ", 0,$90,$D0,$03,$00,90
	.db "Bob        ", 0,$A0,$86,$01,$00,50
	.db "SuperDrunk ", 0,$50,$C3,$00,$00,30
	.db "Hullabaloon", 0,$A8,$61,$00,$00,20
	.db "Dwedit     ", 0,$88,$13,$00,$00,05
#ELSE
	.db "Bub   ", 0,$90,$D0,$03,$00,50
	.db "Bob   ", 0,$A0,$86,$01,$00,40
	.db "Skel  ", 0,$50,$C3,$00,$00,30
	.db "Monsta", 0,$A8,$61,$00,$00,20
	.db "Dwedit", 0,$88,$13,$00,$00,10
#ENDIF
#IFNDEF APP\EndOfHighScores:\#ENDIF
#ENDIF
SAVE_END86:

#IFDEF WIDE16
XOFF = 16
#else
XOFF = 0
#endif ;wide16



tGameOver: .db 30+XOFF,27,"Game Over!",0,255
tCredits:  .db 26+XOFF,37,"Credits: ",0,255
tContinue: .db 33+XOFF,47,"Continue",0
tEnd:      .db 33+XOFF,55,"End",0,255

;;;;;;;;;;;;;;;;0123456789012345678901234

tBadEnd1:  .db 30+XOFF,10,"BAD END!",0
tBadEnd2:  .db 8+XOFF,21,"This is not a true ending!",0,255
#IFDEF ENDING
tBadEnd3:  .db "Try again with your FRIEND.",0
tBadEnd4:  .db "Cheating is bad, mmmkay?",0
tHappyEnd: .db "HAPPY END!",0

tSuperUnlocked: .db "Super Mode unlocked!",0

#ENDIF



tSelect:   .db 24+XOFF,23,"Select a round",0,255
tGameMode: .db 4+XOFF,38,"Game Mode:",0
tNormal:   .db 15+XOFF,49,"Normal",0
tSuper:    .db 57+XOFF,49,"Super",0,255


#IFDEF LINK
#IFNDEF LESSTEXT
;            012345678901234567890123
tLink0: .db 31+XOFF,2,"Link Game",0

tLink1: .db 2+XOFF,14,"Waiting for the " \ .db "other player",0,255
tLink2: .db 2+XOFF,20,"to join the game...",0
tLink3: .db 2+XOFF,35,"Note: If the game 'freezes'",0
tLink4: .db 2+XOFF,41,"during linkplay, just hold",0
tLink5: .db 2+XOFF,47,QUIT_BUTTON," to return to the main",0
tLink6: .db 2+XOFF,53,"menu.",0,255
tLink2b: .db 2+XOFF,20,"to rejoin the game...",0,255



tLink7: .db 0+XOFF,0,"Connection successful.",0
tLink8: .db 0+XOFF,8,"Now waiting for Player 1",0
tLink9: .db 0+XOFF,14,"to select a level.",0,255

tHi1: .db 0+XOFF,0,"Waiting for both players",0
tHi2: .db 0+XOFF,7,"to enter high scores...",0,255
#ELSE
tLink0: .db 1+XOFF,0,"Waiting for other player...",0,255
tLink7: .db 0+XOFF,0,"Waiting for level selection",0,255
tHi1: .db 0+XOFF,0,"player entering hiscore...",0,255
#ENDIF

#ifdef LINK
#IFDEF TI83P

tNoWorky: .db 3,2,"Linkplay is currently",0
          .db 3,9,"incompatible with the",0
          .db 3,16,"TI83+SE.",0,255

#endif
#endif


;tWaitLevel: .db "Waiting for level selection",0
;tPleaseWait: .db "Please Wait...",0

tLinkError: .db "Link Error",0
#ENDIF

#IFNDEF NOINFO
tAbout1: .db 1+XOFF,20,"Game by Dan Weiss (Dwedit)",0
tAbout2: .db 9+XOFF,26,"(c) 2001-2004 - "
         .db GAMEVERSION,0
tEmail1: .db 1+XOFF,34,"Email:",0
tEmail2: .db 5+XOFF,40,"bubble@dwedit.cjb.net",0
tAIM:    .db 1+XOFF,48,"AIM: Dwedit403",0
tURL:    .db 1+XOFF,56,"Web:  http://www.bub83.tk",0,255

tInstructions1: .db 27+XOFF,19,"Instructions:",0

tInstructions2: .db 1+XOFF,28,"- Use arrow keys to move.",0
tInstructions3: .db 1+XOFF,35,"- Press Alpha or Up to jump.",0
tInstructions4: .db 1+XOFF,42,"- Press 2nd to blow bubbles.",0
tInstructions5: .db 1+XOFF,49,"- Trap the enemies inside",0
tInstructions6: .db 6+XOFF,56,"bubbles and pop them!",0,255

tInstructions8: .db 1+XOFF,28,"- Pop at least 3 enemies",0
tInstructions9: .db 6+XOFF,35,"simultaneously for EXTEND",0
tInstructionsA: .db 6+XOFF,42,"letters.  Spell EXTEND and",0
tInstructionsB: .db 6+XOFF,49,"get an extra life!",0
tInstructions7: .db 1+XOFF,56,"- Press ",QUIT_BUTTON," to "\ .db "save & quit.",0,255

tCast:   .db 34+XOFF,18,"--Cast--",0

#ifndef WIDE16
tEnemy1: .db 28,26,"Bubble Buster",0
tEnemy2: .db 28,36,"Stoner",0
tEnemy3: .db 28,46,"Beluga",0
tEnemy4: .db 28,56,"Hullaballoon",0,255
tEnemy5: .db 36,26,"Banebou",0
tEnemy6: .db 36,36,"Hidegonzu",0
tEnemy7: .db 36,46,"Drunk",0
tEnemy8: .db 36,56,"Invader",0,255
#else ;fit them all on one screen for TI85/86 version
tEnemy1: .db 20,26,"Bubble Buster",0
tEnemy2: .db 20,36,"Stoner",0
tEnemy3: .db 20,46,"Beluga",0
tEnemy4: .db 20,56,"Hullaballoon",0
tEnemy5: .db 84,26,"Banebou",0
tEnemy6: .db 84,36,"Hidegonzu",0
tEnemy7: .db 84,46,"Drunk",0
tEnemy8: .db 84,56,"Invader",0,255
#endif ;wide16
tEnemy9: .db 29+XOFF,48,"SuperDrunk",0,255

;tBub:    .db "Bub",0

#ENDIF

tSpeed1: .db 15+XOFF,22,"Select Game Speed:",0
tSpeed2: .db 3+XOFF,29,"(0 is fastest, normal speed)",0
tSpeed3: .db 31+XOFF,43,"Speed:",0,255

#IFDEF EXTERNAL
tSelectWorld:	.db 0,0,"Select World",0,255
tNoWorlds: .db 2+XOFF,0,"No worlds found.",0
           .db 2+XOFF,7,"Please install some!",0,255
SearchString: .db $D5,$3F,"buB10",0
#ENDIF

;tTodaysRecord: .db "Today's record is: LV",0

;tStory: .db "Now it is beginning",0
;        .db "of a fantastic story!",0
;        .db "Let us make a journey",0
;        .db "to the cave of monsters!",0
;        .db "GOOD LUCK!",0

#IFDEF APP
tMemError:
	.db 2,0,"Memory Error!",0
	.db 2,7,"Not enough free RAM.  Delete",0
	.db 2,14,"or archive some programs.",0,255
#ENDIF

tHurryUp:
	.db "Hurry Up!",0

#ifdef WIDE16
tLevelScoreLives:
	.db 107,3,"Level",0
	.db 108,22,"Lives",0
	.db 107,49,"Score",0,255
#endif


#IFDEF BOUNDCHECKING
tLevelCorrupt:
;;;;;;;0123456789ABCDEF
	.db "Buffer Overflow!",0
#ENDIF


#IFDEF EXPORT
.export level
.export map
.export Tile

.export SpriteTable
.export BigspriteY
.export BigspriteX
.export BigSprite
.export EndOfSprites

.export Keys
.export jJumpPress
.export jBubblePress
.export jLeft
.export jRight
.export jJump
.export jBubble
.export JLR

.export P2Keys

.export SavedFlag

.export StartLevel
.export ContinueLevel
.export TodaysRecord
.export TodaysRecordSuper
.export SuperUnlocked
.export SuperGame

.export RandSeed

.export Vars

.export ScoreUpdateFlag

.export Score
.export Lives

.export Extend
.export ExtendFlags

.export PopUpScore
.export PopUpX
.export PopUpY
.export PopUpLife

.export Credits

.export Timer
.export Timer2
.export Enemycount

.export CurBonusFruit

.export PlayerInvincible

.export PopCount
.export FruitCount

.export PopTime

.export OnLevel
.export LinkGame

.export BonusFlags
.export BonusCounter
.export b_candy
.export b_shoes
.export b_cane
.export b_cross
.export b_potion
.export b_umbrella
.export b_door
.export b_thunderpotion
.export b_levmask
.export b_deathmask

.export MonsterTime

.export Holes
.export Ammo

.export Hurry
.export Baron


.export backuphl

.export EndOfVars

.export Halts

#ifdef APP
.export DefaultHighscoreTable
#endif
.export HighscoreTable
.export EndOfHighScores

.export tGameOver
.export tCredits
.export tContinue
.export tEnd

.export tBadEnd1
.export tBadEnd2



.export tSelect
.export tGameMode
.export tNormal
.export tSuper


#IFDEF LINK
#IFNDEF LESSTEXT
.export tLink0
.export tLink1
.export tLink2
.export tLink3
.export tLink4
.export tLink5
.export tLink6
.export tLink2b
.export tLink7
.export tLink8
.export tLink9
.export tHi1
.export tHi2
#ELSE
.export tLink0
.export tLink7
.export tHi1
#ENDIF

.export tLinkError
#ENDIF ;link

#IFNDEF NOINFO
.export tAbout1
.export tAbout2
.export tEmail1
.export tEmail2
.export tAIM
.export tURL

.export tInstructions1

.export tInstructions2
.export tInstructions3
.export tInstructions4
.export tInstructions5
.export tInstructions6

.export tInstructions8
.export tInstructions9
.export tInstructionsA
.export tInstructionsB
.export tInstructions7

.export tCast

.export tEnemy1
.export tEnemy2
.export tEnemy3
.export tEnemy4
.export tEnemy5
.export tEnemy6
.export tEnemy7
.export tEnemy8
.export tEnemy9
#endif ;noinfo

.export tSpeed1
.export tSpeed2
.export tSpeed3

.export tHurryUp

#IFDEF APP
.export tMemError
#ENDIF

#ifdef WIDE16
.export tLevelScoreLives
#endif

#IFDEF BOUNDCHECKING
.export tLevelCorrupt
#ENDIF

#IFDEF EXTERNAL
.export WorldCount
.export OnWorld
.export MapRoot
.export LevelCount
.export LoadedMap
.export tSelectWorld
.export tNoWorlds
.export SearchString
.export LevelPage
#ENDIF

#IFDEF ENDING
.export tBadEnd3
.export tBadEnd4
.export tHappyEnd
.export tSuperUnlocked
#ENDIF

;.export tBub
;.export tTodaysRecord
;.export tStory
;.export tWaitLevel
;.export tPleaseWait

.export SAVE_START86
.export SAVE_END86
.export oldmaproot

#endif ;export