@echo off
echo ============================================
echo  SlideshowMaker - Windows Build Script
echo  Builds two EXEs:
echo    SlideshowMaker.exe    (GUI, no console)
echo    SlideshowMakerCLI.exe (CLI, console visible)
echo ============================================
echo.

REM Check Python
python --version > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Please install Python 3.9+ and add it to PATH.
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
python -m pip install --upgrade pip --quiet
python -m pip install PyQt5 mutagen pyinstaller --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install packages.
    pause
    exit /b 1
)
echo     Done.

echo.
echo [2/3] Building exe (GUI + CLI)...
python -m PyInstaller --noconfirm slideshow_maker.spec
if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)
echo     Done.

echo.
echo [3/3] Checking ffmpeg.exe...
if exist "ffmpeg.exe" (
    echo     ffmpeg.exe found. Copying to dist folder...
    copy /Y "ffmpeg.exe" "dist\ffmpeg.exe" > nul 2>&1
    if exist "ffprobe.exe" (
        copy /Y "ffprobe.exe" "dist\ffprobe.exe" > nul 2>&1
    )
    echo     Copied.
) else (
    echo     [NOTE] ffmpeg.exe not found.
    echo     Please download ffmpeg.exe from https://ffmpeg.org/download.html
    echo     and place it in the same folder as SlideshowMaker.exe
)

echo.
echo ============================================
echo  Build complete!
echo.
echo  GUI mode (no console):
echo    dist\SlideshowMaker.exe
echo.
echo  CLI mode (console visible):
echo    dist\SlideshowMakerCLI.exe --help
echo    dist\SlideshowMakerCLI.exe --list-presets
echo    dist\SlideshowMakerCLI.exe --input C:\Music --output C:\out.mp4
echo    dist\SlideshowMakerCLI.exe --input C:\Songs --bgm C:\bgm.mp3
echo ============================================
echo.
pause
