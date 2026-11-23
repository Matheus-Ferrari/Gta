@echo off
chcp 65001 >nul
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=D:\Cortes\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo O Vice Clips ainda nao foi instalado neste PC. Rode instalar.cmd primeiro.
  pause
  exit /b 1
)
"%PY%" "%~dp0cortar.py" %*
