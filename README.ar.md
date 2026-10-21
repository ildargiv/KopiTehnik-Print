[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-Hant.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [Bahasa Indonesia](README.id.md) | **العربية** | [हिन्दी](README.hi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [Українська](README.uk.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Татарча](README.tt.md)

<div dir="rtl">

# PhotoCrop (КопиТехник PRINT)

برنامج لنظام Windows لاقتصاص الصور وطباعتها (10×15 سم وقياسات أخرى) مع اقتصاص ذكي وتصحيح للألوان وملفات تعريف الألوان وتخطيط للطباعة ووضع وكيل الذكاء الاصطناعي.

**License: [PolyForm Noncommercial 1.0.0](LICENSE)**

## Screenshots

<p align="center"><img src="docs/promo.gif" alt="PhotoCrop animated overview" width="760"></p>

![PhotoCrop main window: crop frame on a demo photo](docs/screenshots/main-window.png)

![Colour adjustments page](docs/screenshots/color-adjustments.png)

![Print sheet with 4 photos per sheet](docs/screenshots/print-sheet.png)

| Arabic (right-to-left) | Japanese |
|---|---|
| ![Arabic interface](docs/screenshots/main-window-arabic-rtl.png) | ![Japanese interface](docs/screenshots/main-window-japanese.png) |
## المزايا

- قياسات الطباعة: 10×15، 9×13، 13×18، 15×21، 20×30، 30×40 سم، A5، A4، A3، A3+، A2 (اقتصاص لملء الورقة أو ملاءمة الصورة كاملة).
- اقتصاص ذكي: كشف الوجوه (YuNet) والأشخاص والحيوانات الأليفة (YOLOX) ونموذج الوضعية؛ ويمكن أيضًا ضبط الإطار يدويًا.
- تصحيح ألوان لكل صورة: السطوع والتباين وغاما والظلال/الإضاءات والتشبع ودرجة الحرارة/الصبغة وRGB والتلقائي والأبيض والأسود والبني الداكن وإزالة الضجيج والحدة.
- إدارة الألوان: ملف ICC للطابعة ومفتاح Windows ICM.
- تخطيط الطباعة: عدة صور في الورقة، وتجاوز الحافة لكل جانب، ومهمة طباعة لكل ورقة مع فاصل، وفحوصات قبل الطباعة (dpi والملاءمة).
- التصدير إلى JPEG وTIFF وPNG وPDF.
- وضع وكيل الذكاء الاصطناعي: كل خطوة أمر يعيد JSON (سطر الأوامر أو خادم MCP لـ Claude Desktop). راجع [AGENT.md](AGENT.md) (بالروسية).
- لغات واجهة إصدار Qt: Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча (تُختار من الإعدادات؛ الافتراضي لغة النظام؛ العربية من اليمين إلى اليسار). تغطي الترجمات الشاشات الرئيسية وهي آلية ولم يراجعها ناطقون أصليون بعد؛ وتظهر النصوص غير المترجمة بالإنجليزية.

## التثبيت

- Windows مع Python 3.9+ (فعّل "Add python.exe to PATH")، أو شغّل `install.bat`: يثبّت Python (إن لزم) والحزم وينشئ الاختصارات. يتطلب الإنترنت.
- التثبيت اليدوي: `pip install -r requirements.txt`.

## تشغيل إصدار Qt

انقر مرتين على `run_qt.bat` (يثبّت Pillow وpillow-heif وPySide6 ويشغّل `photo_crop_qt.py`). الاختبار الذاتي: `selftest_qt.bat`. نافذة Tkinter القديمة: `python photo_crop.py`.

### نماذج الكشف

نماذج YuNet / YOLOX (حوالي 36 ميغابايت) غير مضمّنة في المستودع؛ تُنزَّل عند أول استخدام (أو بالأمر `python smart_crop.py setup`) إلى `%APPDATA%\PhotoCrop\models`.

## وضع الوكيل وMCP

شغّل `mcp_config.bat` (أو `python photo_crop.py mcp-config`) للحصول على كتلة الإعداد، وأضفها إلى `claude_desktop_config.json` (`%APPDATA%\Claude\`) ثم أعد تشغيل Claude Desktop. بالنسبة إلى exe المبني تبدو كتلة `mcpServers.photocrop` هكذا:

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

الأوامر الرئيسية: `open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`.

سطر الأوامر: `python photo_crop.py agent set_format format=10x15`؛ الأمر `python photo_crop.py agent --list` يعرض كل الأوامر. تُحفظ الحالة في `%APPDATA%\PhotoCrop\agent_state.json`. ضبط `PHOTOCROP_AGENT_DRYRUN=1` يمنع الطباعة الفعلية.

## بناء ملفات exe

يبني `build_exe.bat` الملفين `PhotoCrop.exe` (نافذة Tkinter) و`PhotoCropAgent.exe` (وحدة تحكم، لـ MCP) باستخدام PyInstaller. تنبيه: يحذف البرنامج النصي بعد ذلك المجلد `build\` وملفات `.spec`. يُبنى إصدار Qt بالأمر `pyinstaller PhotoCropQt.spec` → `dist\PhotoCropQt.exe`. دفع وسم `v*` يشغّل سير عمل GitHub Actions (`.github/workflows/build.yml`) الذي يبني `PhotoCropQt.exe` و`PhotoCropAgent.exe` ويرفقهما بإصدار GitHub Release.

## الترخيص

License: [PolyForm Noncommercial 1.0.0](LICENSE)

</div>
