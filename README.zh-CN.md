[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | **简体中文** | [繁體中文](README.zh-Hant.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [Bahasa Indonesia](README.id.md) | [العربية](README.ar.md) | [हिन्दी](README.hi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [Українська](README.uk.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Татарча](README.tt.md)

# PhotoCrop (КопиТехник PRINT)

一款 Windows 照片裁剪与打印程序（10×15 厘米及其他规格），支持智能裁剪、色彩校正、色彩配置文件、打印排版和 AI 代理模式。

**License: [KopiTehnik Print Licence](LICENSE)**

## Screenshots

<p align="center"><img src="docs/promo.gif" alt="PhotoCrop animated overview" width="760"></p>

![PhotoCrop main window: crop frame on a demo photo](docs/screenshots/main-window.png)

![Colour adjustments page](docs/screenshots/color-adjustments.png)

![Print sheet with 4 photos per sheet](docs/screenshots/print-sheet.png)

| Arabic (right-to-left) | Japanese |
|---|---|
| ![Arabic interface](docs/screenshots/main-window-arabic-rtl.png) | ![Japanese interface](docs/screenshots/main-window-japanese.png) |
## 功能

- 打印规格：10×15、9×13、13×18、15×21、20×30、30×40 厘米，A5、A4、A3、A3+、A2（裁剪铺满纸张或完整适应）。
- 智能裁剪：人脸检测（YuNet）、人物与宠物（YOLOX）、姿态模型；也可手动设置裁剪框。
- 逐张照片色彩校正：亮度、对比度、伽马、阴影/高光、饱和度、色温/色调、RGB、自动、黑白、棕褐色、降噪、锐化。
- 色彩管理：打印机 ICC 配置文件和 Windows ICM 开关。
- 打印规划：每张纸多张照片、四边出血、每张纸一个打印任务并可设间隔、打印前检查（dpi、适配）。
- 导出为 JPEG、TIFF、PNG 和 PDF。
- AI 代理模式：每一步都是返回 JSON 的命令（命令行或用于 Claude Desktop 的 MCP 服务器）。详见 [AGENT.md](AGENT.md)（俄文）。
- Qt 版本的界面语言：Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча（在设置中选择；默认跟随系统语言；阿拉伯语为从右到左）。翻译涵盖主要界面，为机器翻译，尚未经母语者审校；未翻译的文字显示为英文。

## 安装

- Windows 与 Python 3.9+（勾选 “Add python.exe to PATH”），或运行 `install.bat`：它会安装 Python（如缺失）、依赖包并创建快捷方式。需要联网。
- 手动安装：`pip install -r requirements.txt`。

## 运行 Qt 版本

双击 `run_qt.bat`（安装 Pillow、pillow-heif、PySide6 并启动 `photo_crop_qt.py`）。自检：`selftest_qt.bat`。旧的 Tkinter 窗口：`python photo_crop.py`。

### 检测模型

YuNet / YOLOX 模型（约 36 MB）不包含在仓库中；首次使用时下载（或运行 `python smart_crop.py setup`）到 `%APPDATA%\PhotoCrop\models`。

## 代理模式与 MCP

运行 `mcp_config.bat`（或 `python photo_crop.py mcp-config`）获取配置块，将其加入 `claude_desktop_config.json`（`%APPDATA%\Claude\`），然后重启 Claude Desktop。对于已构建的 exe，`mcpServers.photocrop` 块如下：

```json
{
  "mcpServers": {
    "photocrop": {
      "command": "C:\\path\\to\\PhotoCropAgent.exe",
      "args": ["mcp"]
    }
  }
}
```

主要命令：`open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`.

命令行用法：`python photo_crop.py agent set_format format=10x15`；`python photo_crop.py agent --list` 列出所有命令。状态保存在 `%APPDATA%\PhotoCrop\agent_state.json`。设置 `PHOTOCROP_AGENT_DRYRUN=1` 将禁止真实打印。

## 构建 exe

`build_exe.bat` 使用 PyInstaller 构建 `PhotoCrop.exe`（Tkinter 窗口）和 `PhotoCropAgent.exe`（控制台，用于 MCP）。注意：脚本之后会删除 `build\` 和 `.spec` 文件。Qt 版本使用 `pyinstaller PhotoCropQt.spec` 构建 → `dist\PhotoCropQt.exe`。推送 `v*` 标签会触发 GitHub Actions 工作流（`.github/workflows/build.yml`），构建 `PhotoCropQt.exe` 和 `PhotoCropAgent.exe` 并附加到 GitHub Release。

## 许可证

License: [KopiTehnik Print Licence](LICENSE)
