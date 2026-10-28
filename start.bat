@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "WITH_CNN=0"
set "OPEN_BROWSER=1"
set "RUN_TESTS=0"
set "HELP=0"

:parse
if "%~1"=="" goto :parsed
if /I "%~1"=="--cnn" set "WITH_CNN=1"
if /I "%~1"=="--test" set "RUN_TESTS=1"
if /I "%~1"=="--no-browser" set "OPEN_BROWSER=0"
if /I "%~1"=="--help" set "HELP=1"
shift
goto :parse
:parsed

if "%HELP%"=="1" goto :usage

where python >nul 2>nul
if errorlevel 1 (
    echo [ADISMS] Python 3 was not found on PATH.
    echo Install Python 3.10+ from https://www.python.org/downloads/ and tick
    echo "Add python.exe to PATH", then run this file again.
    goto :fail
)

if not exist ".venv\Scripts\python.exe" (
    echo [ADISMS] Creating virtual environment in .venv ...
    python -m venv .venv
    if errorlevel 1 goto :fail
)

set "VPY=.venv\Scripts\python.exe"

"%VPY%" -c "import flask, werkzeug, numpy, cv2, PIL" >nul 2>nul
if errorlevel 1 (
    echo [ADISMS] Installing core dependencies: Flask, numpy, OpenCV, Pillow ...
    "%VPY%" -m pip install --upgrade pip
    if errorlevel 1 goto :fail
    "%VPY%" -m pip install "Flask>=3.0" "Werkzeug>=3.0" "numpy>=1.26" "opencv-python>=4.9" "Pillow>=10.0"
    if errorlevel 1 goto :fail
)

if "%WITH_CNN%"=="1" (
    "%VPY%" -c "import torch, torchvision" >nul 2>nul
    if errorlevel 1 (
        echo [ADISMS] Installing Alternative C dependencies: PyTorch. This can take a while ...
        "%VPY%" -m pip install "torch>=2.2" "torchvision>=0.17"
        if errorlevel 1 goto :fail
    )
)

if "%RUN_TESTS%"=="1" (
    echo [ADISMS] Running the test suite ...
    "%VPY%" -m unittest discover -s tests -t .
    if errorlevel 1 (
        echo [ADISMS] Tests failed.
        pause
        exit /b 1
    )
    echo [ADISMS] All tests passed.
    pause
    exit /b 0
)

if not defined ADISMS_SECRET_KEY (
    if not exist ".secret_key" (
        "%VPY%" -c "import secrets; open('.secret_key','w').write(secrets.token_hex(32))"
        if errorlevel 1 goto :fail
    )
    for /f "usebackq delims=" %%K in (".secret_key") do set "ADISMS_SECRET_KEY=%%K"
)

if "%OPEN_BROWSER%"=="1" (
    start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:5000'"
)

echo.
echo   ADISMS - Arvid DryGoods
echo   http://127.0.0.1:5000
echo   Press Ctrl+C to stop the server.
echo.
"%VPY%" run.py
goto :end

:usage
echo Usage: start.bat [--cnn] [--test] [--no-browser]
echo.
echo   (no flags)    set up if needed and start the web app
echo   --cnn         also install PyTorch for image recognition alternative C
echo   --test        run the test suite and exit
echo   --no-browser  start without opening the browser
goto :end

:fail
echo.
echo [ADISMS] Setup failed. Fix the message above and try again.
pause
exit /b 1

:end
pause
