@echo off
rem 0104.key

echo ----- Assembling %1 for the TI-83 Plus...
echo #define TI83P >temp.z80
echo #define APP >>temp.z80
if exist %1.z80 type %1.z80 >>temp.z80
if exist %1.asm type %1.asm >>temp.z80
tasm -80 -i -b -l temp.z80 %1.bin
if errorlevel 1 goto ERRORS
del temp.z80
hexconv2 %1.bin %1.hex

echo #define TI83P >temp.z80
echo #define APP >>temp.z80
if exist %12.z80 type %12.z80 >>temp.z80
if exist %12.asm type %12.asm >>temp.z80
tasm -80 -i -b -l temp.z80 %12.bin
if errorlevel 1 goto ERRORS
del temp.z80
hexconv %12.bin %12.hex

copy %1.hex + %12.hex %1.hex

del %1.8xk
del %1.app

call appsign.bat 0104.key %1.hex
echo ----- Success!
echo TI-83 Plus APP version is %1.8xk
goto DONE
:ERRORS
echo ----- There were errors.
:DONE
del temp.z80 > nul
rem del %1.bin > nul
