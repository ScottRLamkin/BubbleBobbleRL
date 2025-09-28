level = saferam2
map = level

Tile = usermem
SpriteTable = Tile+16
BigSpriteY = SpriteTable + (spritetotal*8)+1
BigSpriteX = BigSpriteY+1
BigSprite = BigSpriteX+1
EndOfSprites = BigSprite + 32

Keys = EndOfSprites
jJumpPress   = Keys+0
jBubblePress = Keys+1
jLeft        = Keys+2
jRight       = Keys+3
jJump        = Keys+4
jBubble      = Keys+5
jLR          = Keys+6
P2Keys = Keys+7
SavedFlag = P2keys+7
StartLevel = SavedFlag+1
ContinueLevel = SavedFlag+2
TodaysRecord = SavedFlag+3
TodaysRecordSuper = SavedFlag+4
SuperUnlocked = SavedFlag+5
SuperGame = SavedFlag+6

RandSeed = SavedFlag+7
Vars = RandSeed+2

ScoreUpdateFlag = Vars

Score = ScoreUpdateFlag+1
Lives = Score+4

Extend = Lives+1
ExtendFlags = Extend+1

PopUpScore = Extend+2
PopUpX = PopUpScore+2
PopUpY = PopUpScore+3
PopUpLife = PopUpScore+4

Credits = PopUpLife+1

Timer = Credits+1
Timer2 = Timer+1
EnemyCount = Timer2+1

BaronTimer = EnemyCount+1
CurBonusFruit = BaronTimer+1

PlayerInvincible = CurBonusFruit+1

PopCount = PlayerInvincible+1
FruitCount = PopCount+1

PopTime = FruitCount+1

OnLevel = PopTime+1
LinkGame = OnLevel+1

BonusFlags = LinkGame+1
BonusCounter = BonusFlags+1
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

MonsterTime = BonusCounter+1

Holes = MonsterTime+1
Ammo = Holes+1

Hurry = Ammo+1
Barron = Hurry+1

backuphl = op1

EndOfVars = Barron+1

#IFDEF EXTERNAL
WorldCount = EndOfVars
OnWorld = WorldCount+1
MapRoot = OnWorld+1
LevelCount = MapRoot+2
LoadedMap = LevelCount+1
Halts = LoadedMap+10
#ELSE
Halts = EndOfVars
#ENDIF


HighScoreTable = EndOfVars+200
#IFDEF WIDESCORES
EndOfHighScores = HighScoreTable + 87
#ELSE
EndOfHighScores = HighScoreTable + 61
#ENDIF

AppVarLen = EndOfHighScores-UserMem

