[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-Hant.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | **Türkçe** | [Bahasa Indonesia](README.id.md) | [العربية](README.ar.md) | [हिन्दी](README.hi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [Українська](README.uk.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Татарча](README.tt.md)

# PhotoCrop (КопиТехник PRINT)

Fotoğrafları kırpmak ve yazdırmak (10×15 cm ve diğer boyutlar) için bir Windows programı: akıllı kırpma, renk düzeltme, renk profilleri, baskı düzeni ve yapay zekâ ajanı modu.

**License: not selected (lisans seçilmedi).**

## Özellikler

- Baskı boyutları: 10×15, 9×13, 13×18, 15×21, 20×30, 30×40 cm, A5, A4, A3, A3+, A2 (sayfayı dolduracak şekilde kırp veya fotoğrafın tamamını sığdır).
- Akıllı kırpma: yüz algılama (YuNet), insanlar ve evcil hayvanlar (YOLOX), poz modeli; çerçeve elle de ayarlanabilir.
- Fotoğraf başına renk düzeltme: parlaklık, kontrast, gama, gölgeler/parlak alanlar, doygunluk, sıcaklık/ton, RGB, otomatik, siyah-beyaz, sepya, gürültü azaltma, keskinleştirme.
- Renk yönetimi: yazıcı ICC profili ve Windows ICM anahtarı.
- Baskı planlama: sayfada birden fazla fotoğraf, kenar başına taşma, sayfa başına bir iş (işler arasında bekleme), baskı öncesi kontroller (dpi, sığma).
- JPEG, TIFF, PNG ve PDF olarak dışa aktarma.
- Yapay zekâ ajanı modu: her adım JSON döndüren bir komuttur (komut satırı veya Claude Desktop için MCP sunucusu). Bkz. [AGENT.md](AGENT.md) (Rusça).
- Qt sürümünün arayüz dilleri: Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча (Ayarlar'dan seçilir; varsayılan sistem dilidir; Arapça sağdan sola). Çeviriler ana ekranları kapsar, makine çevirisidir ve anadili konuşanlarca henüz gözden geçirilmemiştir; çevrilmemiş metinler İngilizce görünür.

## Kurulum

- Windows ve Python 3.9+ (“Add python.exe to PATH”) ya da `install.bat` çalıştırın: Python'u (yoksa), paketleri kurar ve kısayollar oluşturur. İnternet gerekir.
- Elle kurulum: `pip install -r requirements.txt`.

## Qt sürümünü çalıştırma

`run_qt.bat` dosyasına çift tıklayın (Pillow, pillow-heif, PySide6 kurar ve `photo_crop_qt.py` başlatır). Kendi kendine test: `selftest_qt.bat`. Eski Tkinter penceresi: `python photo_crop.py`.

### Algılama modelleri

YuNet / YOLOX modelleri (~36 MB) depoda yoktur; ilk kullanımda (veya `python smart_crop.py setup` ile) `%APPDATA%\PhotoCrop\models` klasörüne indirilir.

## Ajan modu ve MCP

Yapılandırma bloğunu almak için `mcp_config.bat` (veya `python photo_crop.py mcp-config`) çalıştırın, `claude_desktop_config.json` (`%APPDATA%\Claude\`) dosyasına ekleyin ve Claude Desktop'ı yeniden başlatın. Derlenmiş exe için `mcpServers.photocrop` bloğu şöyledir:

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

Ana komutlar: `open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`.

Komut satırı: `python photo_crop.py agent set_format format=10x15`; `python photo_crop.py agent --list` tüm komutları listeler. Durum `%APPDATA%\PhotoCrop\agent_state.json` içinde saklanır. `PHOTOCROP_AGENT_DRYRUN=1` gerçek yazdırmayı engeller.

## exe dosyalarını derleme

`build_exe.bat`, PyInstaller ile `PhotoCrop.exe` (Tkinter penceresi) ve `PhotoCropAgent.exe` (konsol, MCP için) derler. Not: betik sonra `build\` klasörünü ve `.spec` dosyalarını siler. Qt sürümü `pyinstaller PhotoCropQt.spec` → `dist\PhotoCropQt.exe` ile derlenir. `v*` etiketi gönderildiğinde GitHub Actions iş akışı (`.github/workflows/build.yml`) `PhotoCropQt.exe` ve `PhotoCropAgent.exe` dosyalarını derleyip bir GitHub Release'e ekler.

## Lisans

License: not selected (lisans seçilmedi).
