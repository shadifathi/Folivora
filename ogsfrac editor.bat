@echo off
rem Launch the ogsfrac case editor in WSL and open it in the browser.
title ogsfrac editor

set REPO=/home/fathi/miniforge/FilesShadi/DesignModel1/ogsfrac-0.2.0/ogsfrac

echo Starting the ogsfrac editor...
echo Close this window to stop the server.
echo.

rem Give the server a few seconds, then open the browser.
start "" /min cmd /c "timeout /t 6 >nul & start """" http://localhost:8501"

wsl.exe -e bash -lc "%REPO%/gui.sh %*"

echo.
echo Server stopped.
pause
