[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-Hant.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [Bahasa Indonesia](README.id.md) | [العربية](README.ar.md) | **हिन्दी** | [Italiano](README.it.md) | [Polski](README.pl.md) | [Українська](README.uk.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Татарча](README.tt.md)

# PhotoCrop (КопиТехник PRINT)

फ़ोटो को क्रॉप और प्रिंट करने (10×15 सेमी व अन्य आकार) के लिए Windows प्रोग्राम: स्मार्ट क्रॉपिंग, रंग सुधार, रंग प्रोफ़ाइल, प्रिंट लेआउट और AI-एजेंट मोड के साथ।

**License: [KopiTehnik Print Licence](LICENSE)**

## Screenshots

<p align="center"><img src="docs/promo.gif" alt="PhotoCrop animated overview" width="760"></p>

![PhotoCrop main window: crop frame on a demo photo](docs/screenshots/main-window.png)

![Colour adjustments page](docs/screenshots/color-adjustments.png)

![Print sheet with 4 photos per sheet](docs/screenshots/print-sheet.png)

| Arabic (right-to-left) | Japanese |
|---|---|
| ![Arabic interface](docs/screenshots/main-window-arabic-rtl.png) | ![Japanese interface](docs/screenshots/main-window-japanese.png) |
## विशेषताएँ

- प्रिंट आकार: 10×15, 9×13, 13×18, 15×21, 20×30, 30×40 सेमी, A5, A4, A3, A3+, A2 (शीट भरने के लिए क्रॉप या पूरी फ़ोटो फ़िट)।
- स्मार्ट क्रॉप: चेहरे की पहचान (YuNet), लोग और पालतू जानवर (YOLOX), पोज़ मॉडल; फ़्रेम हाथ से भी तय किया जा सकता है।
- हर फ़ोटो का रंग सुधार: चमक, कंट्रास्ट, गामा, छायाएँ/हाइलाइट, संतृप्ति, तापमान/टिंट, RGB, ऑटो, श्वेत-श्याम, सेपिया, नॉइज़ घटाना, शार्पनिंग।
- रंग प्रबंधन: प्रिंटर का ICC प्रोफ़ाइल और Windows ICM स्विच।
- प्रिंट योजना: प्रति शीट कई फ़ोटो, हर तरफ़ का ब्लीड, हर शीट के लिए अलग जॉब (जॉब के बीच विराम), प्रिंट से पहले जाँच (dpi, फ़िट)।
- JPEG, TIFF, PNG और PDF में निर्यात।
- AI-एजेंट मोड: हर चरण JSON लौटाने वाला कमांड है (कमांड लाइन या Claude Desktop के लिए MCP सर्वर)। देखें [AGENT.md](AGENT.md) (रूसी में)।
- Qt संस्करण की इंटरफ़ेस भाषाएँ: Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча (सेटिंग में चुनें; डिफ़ॉल्ट सिस्टम की भाषा; अरबी दाएँ से बाएँ)। अनुवाद मुख्य स्क्रीन को कवर करते हैं, मशीन-निर्मित हैं और मूल भाषियों ने अभी जाँचे नहीं हैं; अनूदित न हुए पाठ अंग्रेज़ी में दिखते हैं।

## इंस्टॉलेशन

- Windows और Python 3.9+ ("Add python.exe to PATH") या `install.bat` चलाएँ: यह Python (यदि न हो), पैकेज इंस्टॉल करता है और शॉर्टकट बनाता है। इंटरनेट आवश्यक है।
- मैन्युअल इंस्टॉल: `pip install -r requirements.txt`।

## Qt संस्करण चलाना

`run_qt.bat` पर डबल-क्लिक करें (Pillow, pillow-heif, PySide6 इंस्टॉल करता है और `photo_crop_qt.py` शुरू करता है)। स्व-परीक्षण: `selftest_qt.bat`। पुरानी Tkinter विंडो: `python photo_crop.py`।

### पहचान मॉडल

YuNet / YOLOX मॉडल (~36 MB) रिपॉज़िटरी में शामिल नहीं हैं; वे पहली बार उपयोग पर (या `python smart_crop.py setup` से) `%APPDATA%\PhotoCrop\models` में डाउनलोड होते हैं।

## एजेंट मोड और MCP

कॉन्फ़िग ब्लॉक पाने के लिए `mcp_config.bat` (या `python photo_crop.py mcp-config`) चलाएँ, उसे `claude_desktop_config.json` (`%APPDATA%\Claude\`) में जोड़ें और Claude Desktop को पुनः आरंभ करें। बने हुए exe के लिए `mcpServers.photocrop` ब्लॉक इस तरह दिखता है:

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

मुख्य कमांड: `open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`.

कमांड लाइन: `python photo_crop.py agent set_format format=10x15`; `python photo_crop.py agent --list` सभी कमांड दिखाता है। स्थिति `%APPDATA%\PhotoCrop\agent_state.json` में रहती है। `PHOTOCROP_AGENT_DRYRUN=1` असली प्रिंटिंग रोकता है।

## exe फ़ाइलें बनाना

`build_exe.bat` PyInstaller से `PhotoCrop.exe` (Tkinter विंडो) और `PhotoCropAgent.exe` (कंसोल, MCP के लिए) बनाता है। ध्यान दें: स्क्रिप्ट बाद में `build\` और `.spec` फ़ाइलें हटा देती है। Qt संस्करण `pyinstaller PhotoCropQt.spec` → `dist\PhotoCropQt.exe` से बनता है। `v*` टैग पुश करने पर GitHub Actions वर्कफ़्लो (`.github/workflows/build.yml`) `PhotoCropQt.exe` और `PhotoCropAgent.exe` बनाकर GitHub Release में जोड़ देता है।

## लाइसेंस

License: [KopiTehnik Print Licence](LICENSE)
