@echo off
setlocal EnableExtensions
rem ============================================================
rem  PhotoCrop - automatic setup on a new Windows PC
rem  Installs: Python 3.12 (if missing), Pillow, pi-heif,
rem  PySide6 (window), numpy / opencv / onnxruntime (Smart frame),
rem  downloads detection models (~42 MB), creates desktop shortcuts.
rem  Run: double-click. Internet is required. Admin rights are NOT needed.
rem  Options:  install.bat /nosmart   - skip Smart frame components
rem            install.bat /nolink    - do not create shortcuts
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
set "LOG=%~dp0install.log"
set "PYVER=3.12.10"
set "SMART=1"
set "LINKS=1"
if /i "%~1"=="/nosmart" set "SMART=0"
if /i "%~2"=="/nosmart" set "SMART=0"
if /i "%~1"=="/nolink" set "LINKS=0"
if /i "%~2"=="/nolink" set "LINKS=0"

echo PhotoCrop setup, %DATE% %TIME% > "%LOG%"
echo.
echo  ===== PhotoCrop: automatic setup =====
echo  Log: %LOG%
echo.

rem ---------- 0. program files
if not exist "photo_crop.py" goto :nofiles
if not exist "photo_crop_qt.py" goto :nofiles
if "%SMART%"=="1" if not exist "smart_crop.py" goto :nofiles

rem ---------- 1. Python
echo [1/6] Looking for Python 3.9+ ...
call :findpython
if defined PY goto :pyok

echo       Python not found. Installing Python %PYVER% for the current user ...
where winget >nul 2>&1
if errorlevel 1 goto :pydownload
winget install --id Python.Python.3.12 -e --scope user --silent --accept-package-agreements --accept-source-agreements >>"%LOG%" 2>&1
call :findpython
if defined PY goto :pyok

:pydownload
echo       Downloading the installer from python.org ...
set "PYEXE=%TEMP%\python-%PYVER%-amd64.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe' -OutFile '%PYEXE%' } catch { Write-Host $_.Exception.Message; exit 1 }" >>"%LOG%" 2>&1
if errorlevel 1 goto :pyfail
"%PYEXE%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0 Include_doc=0 >>"%LOG%" 2>&1
del /q "%PYEXE%" >nul 2>&1
call :findpython
if defined PY goto :pyok

:pyfail
echo.
echo  [!] Could not install Python automatically.
echo      Install it by hand: https://www.python.org/downloads/  (tick "Add python.exe to PATH"),
echo      then run install.bat again.
goto :fail

:pyok
echo       Python: %PY%
"%PY%" --version
"%PY%" --version >>"%LOG%" 2>&1

rem ---------- 2. pip
echo.
echo [2/6] Updating pip ...
"%PY%" -m ensurepip --upgrade >>"%LOG%" 2>&1
"%PY%" -m pip install --disable-pip-version-check --upgrade pip >>"%LOG%" 2>&1
if errorlevel 1 echo       (pip was not updated - continuing)

rem ---------- 3. core packages
echo.
echo [3/6] Installing the main components: Pillow, pi-heif, PySide6 (about 200 MB, may take a few minutes) ...
"%PY%" -m pip install --disable-pip-version-check --upgrade pillow pi-heif PySide6 >>"%LOG%" 2>&1
if errorlevel 1 goto :pipfail
echo       done.

rem ---------- 4. smart frame
echo.
if "%SMART%"=="0" goto :skipsmart
echo [4/6] Installing Smart frame components: numpy, opencv-python, onnxruntime ...
"%PY%" -m pip install --disable-pip-version-check --upgrade numpy opencv-python onnxruntime >>"%LOG%" 2>&1
if errorlevel 1 goto :smartfail
echo       done.
echo       Downloading detection models (faces + people, about 42 MB, once) ...
"%PY%" smart_crop.py setup >>"%LOG%" 2>&1
if errorlevel 1 echo       [!] Models were not downloaded. You can do it later in the program: tab "Smart frame" - "Download models".
if not errorlevel 1 echo       done.
goto :afterSmart
:smartfail
echo       [!] Smart frame components were not installed (see install.log). The program works without them.
goto :afterSmart
:skipsmart
echo [4/6] Smart frame skipped (/nosmart).
:afterSmart

rem ---------- 5. self-check
echo.
echo [5/6] Checking the installation ...
"%PY%" -c "import PIL, PySide6; print('       Pillow', PIL.__version__, '| PySide6', PySide6.__version__)" 2>>"%LOG%"
if errorlevel 1 goto :pipfail
"%PY%" -c "import pi_heif; print('       HEIC/HEIF (iPhone): OK')" 2>>"%LOG%"
if errorlevel 1 echo       HEIC/HEIF: not available (iPhone photos will not open)
if "%SMART%"=="1" "%PY%" -c "import numpy, cv2, onnxruntime as o; print('       Smart frame: OK,', ', '.join(o.get_available_providers()))" 2>>"%LOG%"
if "%SMART%"=="1" if errorlevel 1 echo       Smart frame: not available
"%PY%" photo_crop_qt.py --selftest >>"%LOG%" 2>&1
if errorlevel 1 (echo       Program self-test: FAILED, see install.log) else (echo       Program self-test: OK)

rem ---------- 6. shortcuts
echo.
if "%LINKS%"=="0" goto :nolinks
echo [6/6] Creating shortcuts on the desktop ...
set "PYW=%PY:python.exe=pythonw.exe%"
if not exist "%PYW%" set "PYW=%PY%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $s=New-Object -ComObject WScript.Shell; $l=$s.CreateShortcut((Join-Path $d 'PhotoCrop.lnk')); $l.TargetPath='%PYW%'; $l.Arguments='\"%~dp0photo_crop_qt.py\"'; $l.WorkingDirectory='%~dp0'; $l.Description='PhotoCrop'; $l.Save(); $l=$s.CreateShortcut((Join-Path $d 'PhotoCrop classic.lnk')); $l.TargetPath='%PYW%'; $l.Arguments='\"%~dp0photo_crop.py\"'; $l.WorkingDirectory='%~dp0'; $l.Save()" >>"%LOG%" 2>&1
if errorlevel 1 (echo       Shortcuts were not created. Use run_qt.bat to start.) else (echo       done: "PhotoCrop" and "PhotoCrop classic" on the desktop.)
goto :finish
:nolinks
echo [6/6] Shortcuts skipped (/nolink).

:finish
echo.
echo  ===== Ready. Start the program with the desktop shortcut or run_qt.bat =====
echo  Printing: install the printer driver (Epson etc.) in Windows as usual.
echo.
pause
exit /b 0

:nofiles
echo.
echo  [!] Program files not found next to install.bat (photo_crop.py, photo_crop_qt.py, smart_crop.py).
echo      Put install.bat into the PhotoCrop folder and run it again.
goto :fail

:pipfail
echo.
echo  [!] Package installation failed. See install.log (last lines below):
powershell -NoProfile -Command "Get-Content -Tail 12 '%LOG%'"
echo      Check the internet connection / antivirus / proxy and run install.bat again.
goto :fail

:fail
echo.
pause
exit /b 1

rem ---------- find a working Python >= 3.9 (skips the Microsoft Store stub)
:findpython
set "PY="
for %%C in ("py -3.12" "py -3.13" "py -3.11" "py -3.10" "py -3.9" "py -3" "python") do (
  if not defined PY call :trypy %%~C
)
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" call :trypy "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
exit /b 0

:trypy
set "CAND="
for /f "usebackq delims=" %%P in (`%* -c "import sys; sys.exit(1) if sys.version_info<(3,9) else print(sys.executable)" 2^>nul`) do set "CAND=%%P"
if defined CAND set "PY=%CAND%"
exit /b 0
