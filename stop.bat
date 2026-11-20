@echo off
rem 停止所有「阅读伴侣」实例（万一重复启动、窗口反复弹出时用）
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
pause
