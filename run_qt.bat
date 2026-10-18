@echo off
rem PhotoCrop (new Qt interface) - run from source. Needs Python 3.9+ with "Add python.exe to PATH".
cd /d "%~dp0"
python -m pip install --quiet --upgrade pillow pillow-heif PySide6
start "" pythonw photo_crop_qt.py
