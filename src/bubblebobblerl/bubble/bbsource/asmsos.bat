@echo off
if "%1"=="" goto usage

set ASM83DIR=%cd%\
cd %2
call %ASM83DIR%_getall.bat

echo ----- Assembling %1 for TI-83 SOS...
echo #define TI83 >temp.z80
echo #define SOS >>temp.z80
if exist %1.z80 echo #include "%1.z80" >>temp.z80
if exist %1.asm echo #include "%1.asm" >>temp.z80
%ASM83DIR%tasm -80 -i -b -l temp.z80 %1.bin
if errorlevel 1 goto ERRORS
%ASM83DIR%devpac83 %1
copy %1.83p %1s.83p > nul
del %1.83p > nul

echo ----- Assembling %1 for TI-83 ZES...
echo #define TI83 >temp.z80
echo #define ZES >>temp.z80
echo #define SOS >>temp.z80
if exist %1.z80 echo #include "%1.z80" >>temp.z80
if exist %1.asm echo #include "%1.asm" >>temp.z80
%ASM83DIR%tasm -80 -i -b -l temp.z80 %1.bin
if errorlevel 1 goto ERRORS
%ASM83DIR%devpac83 %1
copy %1.83p %1z.83p > nul
del %1.83p > nul

echo ----- Assembling %1 for TI-83 ION...
echo #define TI83 >temp.z80
echo #define ION >>temp.z80
if exist %1.z80 echo #include "%1.z80" >>temp.z80
if exist %1.asm echo #include "%1.asm" >>temp.z80
%ASM83DIR%tasm -80 -i -b -l temp.z80 %1.bin
if errorlevel 1 goto ERRORS
%ASM83DIR%devpac83 %1

echo ----- Success!
echo TI-83 SOS version is %1s.83p
echo TI-83 ZES version is %1z.83p
echo TI-83 ION version is %1z.83p
goto DONE
:ERRORS
echo ----- There were errors.
:DONE
del temp.z80 > nul
del %1.bin > nul

call %ASM83DIR%_cleanall.bat
cd %ASM83DIR%
set ASM83DIR=

goto Done2
:usage
echo Usage:
echo -----------------------------------------------------------------------------
echo   %0 progname [progpath]
echo.
echo   Progname is the base filename of the program, leave off the file extension.
echo   Progpath is a path to the program, so you can compile a project located in
echo   in a different folder.  Run this .bat file from the TASM folder.
echo.
echo   This .bat builds TI83 SOS, ZES, and ION programs.
echo.
:Done2