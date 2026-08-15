@echo off
cd /d "%~dp0"
where ISCC >nul 2>nul
if errorlevel 1 (
  echo Instale o Inno Setup 6 para gerar o instalador.
  exit /b 1
)
call build-windows.bat
if errorlevel 1 exit /b 1
ISCC installer\AizenAutoEditor.iss
