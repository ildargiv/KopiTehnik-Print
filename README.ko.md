[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-Hant.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt.md) | [日本語](README.ja.md) | **한국어** | [Türkçe](README.tr.md) | [Bahasa Indonesia](README.id.md) | [العربية](README.ar.md) | [हिन्दी](README.hi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [Українська](README.uk.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Татарча](README.tt.md)

# PhotoCrop (КопиТехник PRINT)

사진 자르기와 인쇄(10×15 cm 및 기타 규격)를 위한 Windows 프로그램입니다. 스마트 자르기, 색 보정, 색상 프로파일, 인쇄 배치, AI 에이전트 모드를 제공합니다.

**License: [KopiTehnik Print Licence](LICENSE)**

## Screenshots

<p align="center"><img src="docs/promo.gif" alt="PhotoCrop animated overview" width="760"></p>

![PhotoCrop main window: crop frame on a demo photo](docs/screenshots/main-window.png)

![Colour adjustments page](docs/screenshots/color-adjustments.png)

![Print sheet with 4 photos per sheet](docs/screenshots/print-sheet.png)

| Arabic (right-to-left) | Japanese |
|---|---|
| ![Arabic interface](docs/screenshots/main-window-arabic-rtl.png) | ![Japanese interface](docs/screenshots/main-window-japanese.png) |
## 기능

- 인쇄 규격: 10×15, 9×13, 13×18, 15×21, 20×30, 30×40 cm, A5, A4, A3, A3+, A2 (용지를 가득 채우도록 자르기 또는 사진 전체 맞추기).
- 스마트 자르기: 얼굴 감지(YuNet), 사람과 반려동물(YOLOX), 포즈 모델. 프레임을 직접 지정할 수도 있습니다.
- 사진별 색 보정: 밝기, 대비, 감마, 그림자/하이라이트, 채도, 색온도/색조, RGB, 자동, 흑백, 세피아, 노이즈 제거, 선명도.
- 색상 관리: 프린터 ICC 프로파일과 Windows ICM 스위치.
- 인쇄 계획: 시트당 여러 장의 사진, 변별 재단 여유, 시트마다 별도 작업(작업 사이 대기), 인쇄 전 점검(dpi, 맞춤).
- JPEG, TIFF, PNG, PDF로 내보내기.
- AI 에이전트 모드: 모든 단계가 JSON을 반환하는 명령입니다(명령줄 또는 Claude Desktop용 MCP 서버). [AGENT.md](AGENT.md)(러시아어)를 참조하세요.
- Qt 버전의 인터페이스 언어: Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча (설정에서 선택, 기본값은 시스템 언어, 아랍어는 오른쪽에서 왼쪽). 번역은 주요 화면을 다루며 기계 번역이고 원어민 검수는 거치지 않았습니다. 번역되지 않은 문구는 영어로 표시됩니다.

## 설치

- Windows와 Python 3.9+(“Add python.exe to PATH” 선택) 또는 `install.bat` 실행: Python(없는 경우)과 패키지를 설치하고 바로가기를 만듭니다. 인터넷이 필요합니다.
- 수동 설치: `pip install -r requirements.txt`.

## Qt 버전 실행

`run_qt.bat`를 두 번 클릭합니다(Pillow, pillow-heif, PySide6를 설치하고 `photo_crop_qt.py` 실행). 자체 테스트: `selftest_qt.bat`. 이전 Tkinter 창: `python photo_crop.py`.

### 감지 모델

YuNet / YOLOX 모델(약 36 MB)은 저장소에 포함되지 않으며, 처음 사용할 때(또는 `python smart_crop.py setup`) `%APPDATA%\PhotoCrop\models`로 다운로드됩니다.

## 에이전트 모드와 MCP

`mcp_config.bat`(또는 `python photo_crop.py mcp-config`)을 실행해 설정 블록을 얻고, `claude_desktop_config.json`(`%APPDATA%\Claude\`)에 추가한 뒤 Claude Desktop을 다시 시작하세요. 빌드된 exe의 `mcpServers.photocrop` 블록은 다음과 같습니다:

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

주요 명령: `open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`.

명령줄: `python photo_crop.py agent set_format format=10x15`; `python photo_crop.py agent --list`로 모든 명령을 봅니다. 상태는 `%APPDATA%\PhotoCrop\agent_state.json`에 저장됩니다. `PHOTOCROP_AGENT_DRYRUN=1`을 설정하면 실제 인쇄가 금지됩니다.

## exe 빌드

`build_exe.bat`는 PyInstaller로 `PhotoCrop.exe`(Tkinter 창)와 `PhotoCropAgent.exe`(콘솔, MCP용)를 빌드합니다. 주의: 스크립트가 끝나면 `build\`와 `.spec` 파일을 삭제합니다. Qt 버전은 `pyinstaller PhotoCropQt.spec` → `dist\PhotoCropQt.exe`로 빌드합니다. `v*` 태그를 푸시하면 GitHub Actions 워크플로(`.github/workflows/build.yml`)가 `PhotoCropQt.exe`와 `PhotoCropAgent.exe`를 빌드해 GitHub Release에 첨부합니다.

## 라이선스

License: [KopiTehnik Print Licence](LICENSE)
