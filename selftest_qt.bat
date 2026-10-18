@echo off
rem PhotoCrop (new Qt interface) - self-test: builds the window, saves screenshots and a report.
cd /d "%~dp0"
python -m pip install --quiet --upgrade pillow pillow-heif PySide6
python photo_crop_qt.py --selftest
echo.
echo Report and screenshots: %APPDATA%\PhotoCrop  (selftest_report.txt, selftest_*.png)
start "" "%APPDATA%\PhotoCrop"
pause
