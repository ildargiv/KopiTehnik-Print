@echo off
setlocal
rem PhotoCrop - connect the AI agent (MCP server) to Claude Desktop.
rem Uses dist\PhotoCropAgent.exe if it is built, otherwise python + photo_crop.py.
cd /d "%~dp0"
if exist "dist\PhotoCropAgent.exe" (set "RUN=dist\PhotoCropAgent.exe") else (set "RUN=python photo_crop.py")
echo.
echo  Config block for Claude Desktop:
echo.
%RUN% mcp-config
echo.
choice /C YN /M "Write it into %%APPDATA%%\Claude\claude_desktop_config.json automatically (a .bak copy is kept)"
if errorlevel 2 goto :end
%RUN% mcp-install
:end
echo.
pause
