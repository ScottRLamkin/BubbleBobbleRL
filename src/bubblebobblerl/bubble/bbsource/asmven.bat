@echo off
echo ----- Assembling %1 for TI-83 Venus...
echo #define TI83 >temp.z80
echo #define VENUS >>temp.z80
if exist %1.z80 type %1.z80 >>temp.z80
if exist %1.asm type %1.asm >>temp.z80
tasm -80 -i -b -l temp.z80 %1.bin
if errorlevel 1 goto ERRORS
if %os%==Windows_NT goto NT1
devpac83 %1
goto NT1b
:NT1
devpac83 %1
:NT1b
copy %1.83p %1v.83p > nul
del %1.83p > nul

echo ----- Assembling %1 for TI-83 ION...
echo #define TI83 >temp.z80
echo #define ION >>temp.z80
if exist %1.z80 type %1.z80 >>temp.z80
if exist %1.asm type %1.asm >>temp.z80
tasm -80 -i -b -l temp.z80 %1.bin
if errorlevel 1 goto ERRORS
if %os%==Windows_NT goto NT2
devpac83 %1
goto NT2b
:NT2
devpac83 %1
:NT2b

echo ----- Success!
echo TI-83 VENUS version is %1v.83p
echo TI-83 ION version is %1.83p
goto DONE
:ERRORS
echo ----- There were errors.
:DONE
del temp.z80 > nul
del %1.bin > nul
