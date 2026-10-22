[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md) | **繁體中文** | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [Bahasa Indonesia](README.id.md) | [العربية](README.ar.md) | [हिन्दी](README.hi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [Українська](README.uk.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Татарча](README.tt.md)

# PhotoCrop (КопиТехник PRINT)

一款 Windows 照片裁切與列印程式（10×15 公分及其他規格），具備智慧裁切、色彩校正、色彩描述檔、列印排版與 AI 代理模式。

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

- 列印規格：10×15、9×13、13×18、15×21、20×30、30×40 公分，A5、A4、A3、A3+、A2（裁切填滿紙張或完整符合）。
- 智慧裁切：人臉偵測（YuNet）、人物與寵物（YOLOX）、姿態模型；也可手動設定裁切框。
- 逐張照片色彩校正：亮度、對比、Gamma、陰影/亮部、飽和度、色溫/色調、RGB、自動、黑白、復古棕、降噪、銳利化。
- 色彩管理：印表機 ICC 描述檔與 Windows ICM 開關。
- 列印規劃：每張紙多張照片、四邊出血、每張紙一個列印工作並可設定間隔、列印前檢查（dpi、符合度）。
- 匯出為 JPEG、TIFF、PNG 與 PDF。
- AI 代理模式：每個步驟都是回傳 JSON 的指令（命令列或供 Claude Desktop 使用的 MCP 伺服器）。詳見 [AGENT.md](AGENT.md)（俄文）。
- Qt 版本的介面語言：Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча（於設定中選擇；預設為系統語言；阿拉伯文為由右至左）。翻譯涵蓋主要畫面，為機器翻譯，尚未經母語人士審閱；未翻譯的文字會以英文顯示。

## 安裝

- Windows 與 Python 3.9+（勾選 “Add python.exe to PATH”），或執行 `install.bat`：會安裝 Python（若缺少）、套件並建立捷徑。需要網路連線。
- 手動安裝：`pip install -r requirements.txt`。

## 執行 Qt 版本

按兩下 `run_qt.bat`（安裝 Pillow、pillow-heif、PySide6 並啟動 `photo_crop_qt.py`）。自我測試：`selftest_qt.bat`。舊的 Tkinter 視窗：`python photo_crop.py`。

### 偵測模型

YuNet / YOLOX 模型（約 36 MB）不包含在儲存庫中；首次使用時下載（或執行 `python smart_crop.py setup`）至 `%APPDATA%\PhotoCrop\models`。

## 代理模式與 MCP

執行 `mcp_config.bat`（或 `python photo_crop.py mcp-config`）取得設定區塊，加入 `claude_desktop_config.json`（`%APPDATA%\Claude\`），然後重新啟動 Claude Desktop。已建置的 exe 的 `mcpServers.photocrop` 區塊如下：

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

主要指令：`open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`.

命令列用法：`python photo_crop.py agent set_format format=10x15`；`python photo_crop.py agent --list` 列出所有指令。狀態儲存在 `%APPDATA%\PhotoCrop\agent_state.json`。設定 `PHOTOCROP_AGENT_DRYRUN=1` 會禁止實際列印。

## 建置 exe

`build_exe.bat` 以 PyInstaller 建置 `PhotoCrop.exe`（Tkinter 視窗）與 `PhotoCropAgent.exe`（主控台，供 MCP 使用）。注意：腳本之後會刪除 `build\` 與 `.spec` 檔案。Qt 版本以 `pyinstaller PhotoCropQt.spec` 建置 → `dist\PhotoCropQt.exe`。推送 `v*` 標籤會觸發 GitHub Actions 工作流程（`.github/workflows/build.yml`），建置 `PhotoCropQt.exe` 與 `PhotoCropAgent.exe` 並附加到 GitHub Release。

## 授權條款

License: [KopiTehnik Print Licence](LICENSE)
