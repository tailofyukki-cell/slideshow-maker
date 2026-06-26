@echo off
echo ============================================
echo  SlideshowMaker - Windows Build Script
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
echo [2/3] Building exe...
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
    copy /Y "ffmpeg.exe" "dist\SlideshowMaker\ffmpeg.exe" > nul 2>&1
    copy /Y "ffmpeg.exe" "dist\ffmpeg.exe" > nul 2>&1
    if exist "ffprobe.exe" (
        copy /Y "ffprobe.exe" "dist\SlideshowMaker\ffprobe.exe" > nul 2>&1
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
echo  GUI mode : dist\SlideshowMaker.exe
echo  CLI mode : dist\SlideshowMaker.exe --cli --help
echo  Presets  : dist\SlideshowMaker.exe --cli --list-presets
echo  Example  : dist\SlideshowMaker.exe --cli --input C:\Music --output C:\out.mp4
echo ============================================
echo.
pause
