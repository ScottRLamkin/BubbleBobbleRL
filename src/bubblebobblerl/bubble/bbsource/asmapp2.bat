@echo off
if "%1"=="" goto usage

set ASM83DIR=%cd%\

if "%TI83PLUSDIR%" == "" goto notdefined
goto alreadydefined
:notdefined
echo Defining Environment Variable TI83PLUSDIR=%cd%
set TI83PLUSDIR=%cd%
:alreadydefined

cd %2

call %ASM83DIR%_getall.bat

echo ----- Assembling %1 for TI-83 Plus APP...

echo #define TI83P >temp.z80
echo #define APP >>temp.z80
if exist %1.z80 echo #include "%1.z80" >>temp.z80
if exist %1.asm echo #include "%1.asm" >>temp.z80
%ASM83DIR%tasm -80 -i -b -l temp.z80 %1.bin
if errorlevel 1 goto ERRORS

echo #define TI83P >temp.z80
echo #define APP >>temp.z80
if exist %1.z80 echo #include "%12.z80" >>temp.z80
if exist %1.asm echo #include "%12.asm" >>temp.z80
%ASM83DIR%tasm -80 -i -b -l temp.z80 %12.bin
if errorlevel 1 goto ERRORS

del %1.8xk

%ASM83DIR%bintointelhex -o %1.hex -p0 %1.bin -p1 %12.bin -e
call %TI83PLUSDIR%\utils\appsign.bat %TI83PLUSDIR%\utils\0104.key %1.hex

echo ----- Success!
echo TI-83 Plus APP version is %1.8xk
goto DONE
:ERRORS
echo ----- There were errors.
:DONE

rem If you want to keep any of the intermediate files, comment out these deletions

del temp.lst > nul
del temp.z80 > nul
del %1.hex > nul
del %1.app > nul
del testing.txt > nul
del %1.bin > nul
del %12.bin > nul

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
echo   This .bat file is for 2 PAGE apps only.
echo.
:Done2