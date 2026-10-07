@echo off
REM ---------------------------------------------------------------------------
REM  Run the PowerShell setup script without fighting the execution policy.
REM
REM  Windows ships with an execution policy that blocks unsigned .ps1 files, so
REM  double-clicking setup_git_and_push.ps1 fails with "not digitally signed".
REM  This wrapper invokes it with -ExecutionPolicy Bypass, scoped to this single
REM  process only. It does not change any system or user-wide setting.
REM
REM  Usage:
REM    scripts\setup_git_and_push.cmd -Email you@example.com -Name yourname ^
REM        -RepoUrl https://github.com/yourname/home-energy-copilot.git -ConfigureIdentity
REM ---------------------------------------------------------------------------
setlocal

set "SCRIPT=%~dp0setup_git_and_push.ps1"

if not exist "%SCRIPT%" (
    echo ERROR: cannot find "%SCRIPT%"
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
exit /b %ERRORLEVEL%
