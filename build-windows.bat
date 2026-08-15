@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
python -m pip install "pyinstaller>=6,<7"
python -m PyInstaller --noconfirm --clean --windowed --name "Aizen Auto Editor" --icon "assets\aizen-stream-control.ico" --add-data "app\web;app\web" --add-data "config;config" --add-data "assets;assets" --collect-all webview --hidden-import app.main app\desktop.py
echo Executavel criado em: dist\Aizen Auto Editor\Aizen Auto Editor.exe
