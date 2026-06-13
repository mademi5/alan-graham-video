@echo off
setlocal
cd /d "%~dp0"

echo Installing build dependencies...
python -m pip install -r requirements.txt pyinstaller imageio-ffmpeg --quiet
if errorlevel 1 (
    echo Failed to install dependencies.
    exit /b 1
)

echo Building Alan Graham Video Editor.exe ...
python -m PyInstaller --noconfirm alan_graham_video_editor.spec
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

echo.
echo Done. Executable:
echo   dist\Alan Graham Video Editor.exe
echo.
echo Copy that single .exe file to the client PC. No Python install required.
echo.
echo For macOS: run build_mac.sh on a Mac to create the .app bundle.
endlocal
