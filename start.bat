@echo off
rem 阅读伴侣 —— 兜底启动器（run.vbs 不行时用这个）
setlocal
cd /d "%~dp0"

set "PYW=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe"
if exist "%PYW%" goto run

where pythonw.exe >nul 2>nul
if errorlevel 1 (
  echo 没找到 pythonw.exe，请先运行 DeepSeek Harness 或安装 Python 3.10+
  pause
  exit /b 1
)
set "PYW=pythonw.exe"

:run
start "" "%PYW%" "%~dp0app.py"
