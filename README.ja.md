[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-Hant.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt.md) | **日本語** | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [Bahasa Indonesia](README.id.md) | [العربية](README.ar.md) | [हिन्दी](README.hi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [Українська](README.uk.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Татарча](README.tt.md)

# PhotoCrop (КопиТехник PRINT)

写真のトリミングと印刷（10×15 cmほか各種サイズ）を行う Windows 用プログラム。スマートトリミング、色補正、カラープロファイル、印刷レイアウト、AI エージェントモードを備えています。

**License: [PolyForm Noncommercial 1.0.0](LICENSE)**

## Screenshots

<p align="center"><img src="docs/promo.gif" alt="PhotoCrop animated overview" width="760"></p>

![PhotoCrop main window: crop frame on a demo photo](docs/screenshots/main-window.png)

![Colour adjustments page](docs/screenshots/color-adjustments.png)

![Print sheet with 4 photos per sheet](docs/screenshots/print-sheet.png)

| Arabic (right-to-left) | Japanese |
|---|---|
| ![Arabic interface](docs/screenshots/main-window-arabic-rtl.png) | ![Japanese interface](docs/screenshots/main-window-japanese.png) |
## 機能

- 印刷サイズ：10×15、9×13、13×18、15×21、20×30、30×40 cm、A5、A4、A3、A3+、A2（用紙いっぱいにトリミング、または写真全体をフィット）。
- スマートトリミング：顔検出（YuNet）、人物・ペット（YOLOX）、姿勢モデル。枠は手動でも指定できます。
- 写真ごとの色補正：明るさ、コントラスト、ガンマ、シャドウ/ハイライト、彩度、色温度/色合い、RGB、自動、白黒、セピア、ノイズ除去、シャープ。
- カラーマネジメント：プリンターの ICC プロファイルと Windows ICM の切り替え。
- 印刷計画：1 枚に複数の写真、辺ごとの裁ち落とし、1 枚ごとに 1 ジョブ（ジョブ間に待機）、印刷前チェック（dpi、収まり）。
- JPEG、TIFF、PNG、PDF への書き出し。
- AI エージェントモード：各工程が JSON を返すコマンドとして利用できます（コマンドライン、または Claude Desktop 用 MCP サーバー）。[AGENT.md](AGENT.md)（ロシア語）を参照。
- Qt 版の表示言語：Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча（設定で選択。既定はシステムの言語。アラビア語は右から左）。翻訳は主要な画面を対象とした機械翻訳で、ネイティブによる確認は未実施です。未翻訳の文字列は英語で表示されます。

## インストール

- Windows と Python 3.9+（「Add python.exe to PATH」を有効に）、または `install.bat` を実行：Python（未導入の場合）とパッケージをインストールし、ショートカットを作成します。インターネット接続が必要です。
- 手動：`pip install -r requirements.txt`。

## Qt 版の起動

`run_qt.bat` をダブルクリック（Pillow、pillow-heif、PySide6 をインストールして `photo_crop_qt.py` を起動）。セルフテスト：`selftest_qt.bat`。従来の Tkinter ウィンドウ：`python photo_crop.py`。

### 検出モデル

YuNet / YOLOX モデル（約 36 MB）はリポジトリに含まれません。初回利用時（または `python smart_crop.py setup`）に `%APPDATA%\PhotoCrop\models` へダウンロードされます。

## エージェントモードと MCP

`mcp_config.bat`（または `python photo_crop.py mcp-config`）で設定ブロックを取得し、`claude_desktop_config.json`（`%APPDATA%\Claude\`）に追加して Claude Desktop を再起動します。ビルド済み exe では `mcpServers.photocrop` ブロックは次のとおりです：

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

主なコマンド：`open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`.

コマンドライン：`python photo_crop.py agent set_format format=10x15`、`python photo_crop.py agent --list` で全コマンドを表示。状態は `%APPDATA%\PhotoCrop\agent_state.json` に保存されます。`PHOTOCROP_AGENT_DRYRUN=1` で実際の印刷を禁止できます。

## exe のビルド

`build_exe.bat` は PyInstaller で `PhotoCrop.exe`（Tkinter ウィンドウ）と `PhotoCropAgent.exe`（コンソール、MCP 用）をビルドします。注意：スクリプトは終了後に `build\` と `.spec` ファイルを削除します。Qt 版は `pyinstaller PhotoCropQt.spec` でビルド → `dist\PhotoCropQt.exe`。タグ `v*` をプッシュすると GitHub Actions（`.github/workflows/build.yml`）が `PhotoCropQt.exe` と `PhotoCropAgent.exe` をビルドし、GitHub Release に添付します。

## ライセンス

License: [PolyForm Noncommercial 1.0.0](LICENSE)
