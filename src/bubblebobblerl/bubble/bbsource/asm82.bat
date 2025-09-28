@echo off
IF %1.==. GOTO Usage
echo ----- Assembling %1 for TI-82 ACE...
echo #define TI82 >temp.z80
echo #define ACE >>temp.z80
if exist %1.z80 type %1.z80 >>temp.z80
if exist %1.asm type %1.asm >>temp.z80
tasm -80 -i -b -l temp.z80 %1.bin
if errorlevel 1 goto ERRORS
ACE82 %1.bin
copy %1.82p %1A.82p

echo ----- Assembling %1 for TI-82 CrASH...
echo #define TI82 >temp.z80
echo #define CRASH >>temp.z80
if exist %1.z80 type %1.z80 >>temp.z80
if exist %1.asm type %1.asm >>temp.z80
tasm -80 -i -b -l temp.z80 %1.bin
if errorlevel 1 goto ERRORS
CRPRGM82 %1.bin

echo ----- Success!
echo TI-82 CrASH version is %1.82p
echo TI-82 ACE version is %1A.82p
goto done
:Usage
ECHO CrASH/ACE Assembly File compiler
ECHO.
ECHO Usage:
ECHO   %0 [FileName]
ECHO.
ECHO [FileName] is the CrASH/ACE ASM source file.  Leave off the ASM extension.
GOTO Done
:ERRORS
echo ----- There were errors.
:DONE
del temp.z80 >nul
del %1.bin >nul
