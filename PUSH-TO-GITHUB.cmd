@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo.
echo  ============================================================
echo    PUSH  Home Energy Copilot  to  GitHub
echo  ============================================================
echo.
echo    Repo: wuyifenxiang/home-energy-copilot
echo.
echo    What will happen:
echo      1. This window shows what is being uploaded.
echo      2. A browser window opens so you can sign in to GitHub.
echo         Pick "Sign in with your browser" and log in.
echo      3. The upload finishes by itself.
echo.
echo    If no browser window appears, read the messages below.
echo.
pause

echo.
echo  ---- pushing now, please wait ----
echo.
git push -u origin main --force
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" goto SUCCESS
goto FAILURE

:SUCCESS
echo  ============================================================
echo    SUCCESS - your code is now on GitHub
echo  ============================================================
echo.
echo    Open this page to see it:
echo    https://github.com/wuyifenxiang/home-energy-copilot
echo.
echo    LAST STEP, must be done by hand:
echo      On the repo page, click the gear icon next to "About".
echo      In the "License" dropdown choose "MIT License".
echo      Click "Save changes".
echo.
goto END

:FAILURE
echo  ============================================================
echo    FAILED  -  error code %RC%
echo  ============================================================
echo.
echo    Take a screenshot of the red error text above and send it
echo    to your AI assistant so it can tell you what went wrong.
echo.
echo    Common causes:
echo      - You cancelled the GitHub sign-in window.
echo      - No internet connection.
echo.

:END
echo.
pause
endlocal
