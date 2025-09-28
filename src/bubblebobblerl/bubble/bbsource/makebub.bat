call asmsos.bat bubble
call asm82.bat bubble
call asmven.bat bubble
call asmapp.bat bubapp
call asm.bat bubble
call makebub86.bat
call makebub85.bat


set curdir=%cd%
cd\projects
call pk7zip %curdir%\bubedit.zip "bubmap2\*.*"
cd %curdir%
set curdir=

zip -0 bbsource.zip bubble.z80 bub_main.z80 bub_ai.z80 bub_draw.z80 spr21a.inc bub_link.z80
zip -0 bbsource.zip bub_gfx.h bub_data.h bub_map.h bub_tabl.h dwedit.inc zrec8x.z80 zsend8x.z80
zip -0 bbsource.zip makebub.bat fastcopy.h bubapp.z80 bubapp2.z80 spr21app.h largespr.h
zip -0 bbsource.zip asmsos.bat asm.bat asm82.bat asmven.bat asmapp2.bat
zip -0 bbsource.zip bub_appd.inc bub_apd2.h miniice.z80 icemaps.h bub_lev.z80
zip -0 bbsource.zip bub_gfx.inc bub_end.z80
zip -0 bbsource.zip detect.h bub85.z80 bub86.z80 bub861.z80 bub862.z80 bub_font.z80 rigel2.h

zip -0 bubble.zip bubble.83p bubble.82p bubblev.83p bubblea.82p bubble_19.006.82p
zip -0 bubble.zip bubble.85s bubble.86p bubprog.86s bubapp.8xk
zip -0 bubble.zip bubworld.83p bubworld.82p bubworld.8xp bubworld.86s
zip -0 bubble.zip bubble.html bubble.swf bbsource.zip bubedit.zip

call pk7zip bub.zip bubble.zip bubble.txt

copy bub.zip C:\site\bubblebobble\bubble.zip
copy bbsource.zip C:\site\bubblebobble
rem copy bubble.8?p C:\site\bubblebobble
