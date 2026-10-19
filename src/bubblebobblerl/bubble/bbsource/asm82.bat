@echo off
if "%1"=="" goto usage

set ASM83DIR=%cd%\
cd %2
call %ASM83DIR%_getall.bat

echo ----- Assembling %1 for TI-82 ACE...
echo #define TI82 >temp.z80
echo #define ACE >>temp.z80
if exist %1.z80 echo #include "%1.z80" >>temp.z80
if exist %1.asm echo #include "%1.asm" >>temp.z80
%ASM83DIR%tasm -80 -i -b -l temp.z80 %1.bin
if errorlevel 1 goto ERRORS
%ASM83DIR%ACE82 %1.bin
copy %1.82p %1A.82p

echo ----- Assembling %1 for TI-82 CrASH 19.006...
echo #define TI82 >temp.z80
echo #define CRASH19006 >>temp.z80
if exist %1.z80 echo #include "%1.z80" >>temp.z80
if exist %1.asm echo #include "%1.asm" >>temp.z80
%ASM83DIR%tasm -80 -i -b -l temp.z80 %1.bin
if errorlevel 1 goto ERRORS
%ASM83DIR%CRPRGM82 %1.bin
copy %1.82p %1_19.006.82p

echo ----- Assembling %1 for TI-82 CrASH...
echo #define TI82 >temp.z80
echo #define CRASH >>temp.z80
if exist %1.z80 echo #include "%1.z80" >>temp.z80
if exist %1.asm echo #include "%1.asm" >>temp.z80
%ASM83DIR%tasm -80 -i -b -l temp.z80 %1.bin
if errorlevel 1 goto ERRORS
%ASM83DIR%CRPRGM82 %1.bin

echo ----- Success!
echo TI-82 CrASH version is %1.82p
echo TI-82 CrASH 19.006 version is %1_19.006.82p
echo TI-82 ACE version is %1A.82p
goto done
:ERRORS
echo ----- There were errors.
:DONE
del temp.z80 >nul
del %1.bin >nul

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
echo   This .bat builds TI82 CrASH and TI82 ACE programs.
echo.
:Done2