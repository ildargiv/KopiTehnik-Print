[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-Hant.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [Bahasa Indonesia](README.id.md) | [العربية](README.ar.md) | [हिन्दी](README.hi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [Українська](README.uk.md) | [Tiếng Việt](README.vi.md) | **ไทย** | [Татарча](README.tt.md)

# PhotoCrop (КопиТехник PRINT)

โปรแกรม Windows สำหรับครอปและพิมพ์รูปภาพ (10×15 ซม. และขนาดอื่น ๆ) พร้อมการครอปอัจฉริยะ การแก้สี โปรไฟล์สี การจัดหน้าพิมพ์ และโหมดเอเจนต์ AI

**License: not selected (ยังไม่ได้เลือกใบอนุญาต)**

## คุณสมบัติ

- ขนาดพิมพ์: 10×15, 9×13, 13×18, 15×21, 20×30, 30×40 ซม., A5, A4, A3, A3+, A2 (ครอปให้เต็มแผ่นหรือใส่รูปทั้งภาพ)
- ครอปอัจฉริยะ: ตรวจจับใบหน้า (YuNet) คนและสัตว์เลี้ยง (YOLOX) โมเดลท่าทาง และตั้งกรอบด้วยมือได้
- แก้สีรายรูป: ความสว่าง คอนทราสต์ แกมมา เงา/ไฮไลต์ ความอิ่มตัว อุณหภูมิ/โทนสี RGB อัตโนมัติ ขาวดำ ซีเปีย ลดสัญญาณรบกวน เพิ่มความคมชัด
- การจัดการสี: โปรไฟล์ ICC ของเครื่องพิมพ์และสวิตช์ Windows ICM
- การวางแผนพิมพ์: หลายรูปต่อแผ่น ส่วนเกินขอบแต่ละด้าน หนึ่งงานพิมพ์ต่อหนึ่งแผ่นพร้อมหน่วงเวลา การตรวจสอบก่อนพิมพ์ (dpi ความพอดี)
- ส่งออกเป็น JPEG, TIFF, PNG และ PDF
- โหมดเอเจนต์ AI: ทุกขั้นตอนเป็นคำสั่งที่คืนค่า JSON (บรรทัดคำสั่งหรือเซิร์ฟเวอร์ MCP สำหรับ Claude Desktop) ดู [AGENT.md](AGENT.md) (ภาษารัสเซีย)
- ภาษาของอินเทอร์เฟซเวอร์ชัน Qt: Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча (เลือกได้ในการตั้งค่า ค่าเริ่มต้นตามภาษาของระบบ ภาษาอาหรับเขียนจากขวาไปซ้าย) คำแปลครอบคลุมหน้าจอหลัก เป็นการแปลด้วยเครื่อง และยังไม่ได้รับการตรวจโดยเจ้าของภาษา ข้อความที่ยังไม่แปลจะแสดงเป็นภาษาอังกฤษ

## การติดตั้ง

- Windows พร้อม Python 3.9+ (เลือก "Add python.exe to PATH") หรือรัน `install.bat`: จะติดตั้ง Python (หากไม่มี) แพ็กเกจ และสร้างทางลัด ต้องใช้อินเทอร์เน็ต
- ติดตั้งเอง: `pip install -r requirements.txt`

## การเรียกใช้เวอร์ชัน Qt

ดับเบิลคลิก `run_qt.bat` (ติดตั้ง Pillow, pillow-heif, PySide6 และเริ่ม `photo_crop_qt.py`) ทดสอบตัวเอง: `selftest_qt.bat` หน้าต่าง Tkinter รุ่นเก่า: `python photo_crop.py`

### โมเดลตรวจจับ

โมเดล YuNet / YOLOX (~36 MB) ไม่ได้รวมอยู่ในรีโพซิทอรี จะดาวน์โหลดเมื่อใช้ครั้งแรก (หรือด้วย `python smart_crop.py setup`) ไปที่ `%APPDATA%\PhotoCrop\models`

## โหมดเอเจนต์และ MCP

รัน `mcp_config.bat` (หรือ `python photo_crop.py mcp-config`) เพื่อรับบล็อกการตั้งค่า เพิ่มลงใน `claude_desktop_config.json` (`%APPDATA%\Claude\`) แล้วรีสตาร์ต Claude Desktop สำหรับ exe ที่บิลด์แล้ว บล็อก `mcpServers.photocrop` เป็นดังนี้:

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

คำสั่งหลัก: `open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`.

บรรทัดคำสั่ง: `python photo_crop.py agent set_format format=10x15`; `python photo_crop.py agent --list` แสดงคำสั่งทั้งหมด สถานะเก็บใน `%APPDATA%\PhotoCrop\agent_state.json` การตั้ง `PHOTOCROP_AGENT_DRYRUN=1` จะห้ามพิมพ์จริง

## การบิลด์ไฟล์ exe

`build_exe.bat` บิลด์ `PhotoCrop.exe` (หน้าต่าง Tkinter) และ `PhotoCropAgent.exe` (คอนโซล สำหรับ MCP) ด้วย PyInstaller หมายเหตุ: สคริปต์จะลบ `build\` และไฟล์ `.spec` ภายหลัง เวอร์ชัน Qt บิลด์ด้วย `pyinstaller PhotoCropQt.spec` → `dist\PhotoCropQt.exe` การพุชแท็ก `v*` จะรันเวิร์กโฟลว์ GitHub Actions (`.github/workflows/build.yml`) ที่บิลด์ `PhotoCropQt.exe` และ `PhotoCropAgent.exe` แล้วแนบไปกับ GitHub Release

## ใบอนุญาต

License: not selected (ยังไม่ได้เลือกใบอนุญาต)
