@echo off
rem PhotoCrop - build standalone exe files (no Python needed on target PCs)
cd /d "%~dp0"
python -m pip install --upgrade pillow pyinstaller numpy opencv-python onnxruntime
rem 1) window program
python -m PyInstaller --noconfirm --onefile --windowed --name PhotoCrop --hidden-import smart_crop --hidden-import i18n --hidden-import i18n_more --collect-all onnxruntime photo_crop.py
rem 2) console twin for AI agents (JSON on stdin/stdout, MCP): a windowed exe has no stdio
python -m PyInstaller --noconfirm --onefile --console --name PhotoCropAgent --hidden-import smart_crop --hidden-import i18n --hidden-import i18n_more --collect-all onnxruntime photo_crop.py
rem Note: models (~36 MB) are NOT bundled: downloaded once on first use to %APPDATA%\PhotoCrop\models
rem 3) remove intermediate files (build\ is ~50 MB, *.spec) - only dist\*.exe is needed
if exist build rmdir /s /q build
del /q PhotoCrop.spec PhotoCropAgent.spec 2>nul
echo.
echo Done: dist\PhotoCrop.exe  and  dist\PhotoCropAgent.exe
pause
