@echo off
if "%1"=="" goto usage

set ASM83DIR=%cd%\
cd %2
call %ASM83DIR%_getall.bat

echo ----- Assembling %1 for the TI-83 Plus...

echo #define TI83P >temp.z80
echo #define ION >>temp.z80
if exist %1.z80 echo #include "%1.z80" >>temp.z80
if exist %1.asm echo #include "%1.asm" >>temp.z80

%ASM83DIR%tasm -80 -i -b -l temp.z80 %1.bin
if errorlevel 1 goto ERRORS
%ASM83DIR%devpac8x %1

echo ----- Assembling %1 for TI-83 ION...

echo #define TI83 >temp.z80
echo #define ION >>temp.z80
if exist %1.z80 echo #include "%1.z80" >>temp.z80
if exist %1.asm echo #include "%1.asm" >>temp.z80

%ASM83DIR%tasm -80 -i -b -l temp.z80 %1.bin
if errorlevel 1 goto ERRORS
%ASM83DIR%devpac83 %1

echo ----- Success!
echo TI-83 ION version is %1.83p
echo TI-83 Plus version is %1.8xp
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
echo   This .bat builds TI83+ and TI83 ion programs.
echo.
:Done2