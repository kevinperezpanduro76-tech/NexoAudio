@echo off
rem Compila NexoAudio.exe en tu PC (necesita Python 3.11+). Opcional: GitHub Actions ya lo hace por ti.
py -m pip install -r requirements.txt pyinstaller || exit /b 1
py -m PyInstaller --noconfirm --onefile --console --name NexoAudio --add-data "index.html;." --collect-all pyaudiowpatch server.py
echo.
echo Listo: dist\NexoAudio.exe
pause
