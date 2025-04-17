@echo off
setlocal enabledelayedexpansion

:: Prompt for speed multiplier
set /p multiplier=Enter timelapse speed multiplier (e.g. 60 for 60x):

:: Loop through all dragged files
for %%F in (%*) do (
    set "input=%%~nxF"
    set "name=%%~nF"
    echo [🎞️] Encoding: %%F
    ffmpeg -i "%%~F" -filter:v "setpts=PTS/!multiplier!" -an -r 30 -c:v libx264 -preset veryfast -crf 20 "%%~dpF!name!_timelapse.mp4"
)

pause
