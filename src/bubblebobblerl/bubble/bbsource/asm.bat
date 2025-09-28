@echo off
echo ----- Assembling %1 for the TI-83 Plus...
echo #define TI83P >temp.z80
echo #define ION >>temp.z80
if exist %1.z80 type %1.z80 >>temp.z80
if exist %1.asm type %1.asm >>temp.z80
tasm -80 -i -b -l temp.z80 %1.bin
if errorlevel 1 goto ERRORS
if %os%==Windows_NT goto NT1
devpac8x %1
goto NT1b
:NT1
devpac8x %1
:NT1b
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
echo TI-83 ION version is %1.83p
echo TI-83 Plus version is %1.8xp
goto DONE
:ERRORS
echo ----- There were errors.
:DONE
del temp.z80 > nul
del %1.bin > nul
