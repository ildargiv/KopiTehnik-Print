[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-Hant.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [Bahasa Indonesia](README.id.md) | [العربية](README.ar.md) | [हिन्दी](README.hi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [Українська](README.uk.md) | **Tiếng Việt** | [ไทย](README.th.md) | [Татарча](README.tt.md)

# PhotoCrop (КопиТехник PRINT)

Chương trình Windows để cắt và in ảnh (10×15 cm và các khổ khác), có cắt thông minh, chỉnh màu, hồ sơ màu, bố cục in và chế độ tác tử AI.

**License: not selected (chưa chọn giấy phép).**

## Screenshots

![PhotoCrop main window: crop frame on a demo photo](docs/screenshots/main-window.png)

![Colour adjustments page](docs/screenshots/color-adjustments.png)

![Print sheet with 4 photos per sheet](docs/screenshots/print-sheet.png)

| Arabic (right-to-left) | Japanese |
|---|---|
| ![Arabic interface](docs/screenshots/main-window-arabic-rtl.png) | ![Japanese interface](docs/screenshots/main-window-japanese.png) |
## Tính năng

- Khổ in: 10×15, 9×13, 13×18, 15×21, 20×30, 30×40 cm, A5, A4, A3, A3+, A2 (cắt để lấp đầy tờ giấy hoặc đặt vừa cả ảnh).
- Cắt thông minh: nhận diện khuôn mặt (YuNet), người và thú cưng (YOLOX), mô hình tư thế; cũng có thể đặt khung thủ công.
- Chỉnh màu từng ảnh: độ sáng, tương phản, gamma, vùng tối/sáng, độ bão hòa, nhiệt độ/sắc thái, RGB, tự động, đen trắng, sepia, giảm nhiễu, làm nét.
- Quản lý màu: hồ sơ ICC của máy in và công tắc Windows ICM.
- Lập kế hoạch in: nhiều ảnh trên một tờ, tràn lề theo từng cạnh, mỗi tờ một tác vụ in có khoảng nghỉ, kiểm tra trước khi in (dpi, độ vừa khít).
- Xuất ra JPEG, TIFF, PNG và PDF.
- Chế độ tác tử AI: mỗi bước là một lệnh trả về JSON (dòng lệnh hoặc máy chủ MCP cho Claude Desktop). Xem [AGENT.md](AGENT.md) (tiếng Nga).
- Ngôn ngữ giao diện của bản Qt: Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча (chọn trong Cài đặt; mặc định theo ngôn ngữ hệ thống; tiếng Ả Rập viết từ phải sang trái). Bản dịch bao phủ các màn hình chính, do máy dịch và chưa được người bản ngữ rà soát; chuỗi chưa dịch hiển thị bằng tiếng Anh.

## Cài đặt

- Windows với Python 3.9+ ("Add python.exe to PATH") hoặc chạy `install.bat`: cài Python (nếu thiếu), các gói và tạo lối tắt. Cần Internet.
- Cài thủ công: `pip install -r requirements.txt`.

## Chạy bản Qt

Nhấp đúp `run_qt.bat` (cài Pillow, pillow-heif, PySide6 và chạy `photo_crop_qt.py`). Tự kiểm tra: `selftest_qt.bat`. Cửa sổ Tkinter cũ: `python photo_crop.py`.

### Mô hình nhận diện

Các mô hình YuNet / YOLOX (~36 MB) không có trong kho mã; chúng được tải về khi dùng lần đầu (hoặc bằng `python smart_crop.py setup`) vào `%APPDATA%\PhotoCrop\models`.

## Chế độ tác tử và MCP

Chạy `mcp_config.bat` (hoặc `python photo_crop.py mcp-config`) để lấy khối cấu hình, thêm vào `claude_desktop_config.json` (`%APPDATA%\Claude\`) rồi khởi động lại Claude Desktop. Với exe đã build, khối `mcpServers.photocrop` như sau:

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

Các lệnh chính: `open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`.

Dòng lệnh: `python photo_crop.py agent set_format format=10x15`; `python photo_crop.py agent --list` liệt kê mọi lệnh. Trạng thái lưu tại `%APPDATA%\PhotoCrop\agent_state.json`. `PHOTOCROP_AGENT_DRYRUN=1` cấm in thật.

## Build file exe

`build_exe.bat` dùng PyInstaller để build `PhotoCrop.exe` (cửa sổ Tkinter) và `PhotoCropAgent.exe` (console, cho MCP). Lưu ý: sau đó script xóa `build\` và các file `.spec`. Bản Qt build bằng `pyinstaller PhotoCropQt.spec` → `dist\PhotoCropQt.exe`. Đẩy tag `v*` sẽ chạy workflow GitHub Actions (`.github/workflows/build.yml`), build `PhotoCropQt.exe` và `PhotoCropAgent.exe` rồi đính kèm vào GitHub Release.

## Giấy phép

License: not selected (chưa chọn giấy phép).
