[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-Hant.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | **Bahasa Indonesia** | [العربية](README.ar.md) | [हिन्दी](README.hi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [Українська](README.uk.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Татарча](README.tt.md)

# PhotoCrop (КопиТехник PRINT)

Program Windows untuk memangkas dan mencetak foto (10×15 cm dan format lain), dengan pemangkasan pintar, koreksi warna, profil warna, tata letak cetak, dan mode agen AI.

**License: [KopiTehnik Print Licence](LICENSE)**

## Screenshots

<p align="center"><img src="docs/promo.gif" alt="PhotoCrop animated overview" width="760"></p>

![PhotoCrop main window: crop frame on a demo photo](docs/screenshots/main-window.png)

![Colour adjustments page](docs/screenshots/color-adjustments.png)

![Print sheet with 4 photos per sheet](docs/screenshots/print-sheet.png)

| Arabic (right-to-left) | Japanese |
|---|---|
| ![Arabic interface](docs/screenshots/main-window-arabic-rtl.png) | ![Japanese interface](docs/screenshots/main-window-japanese.png) |
## Fitur

- Format cetak: 10×15, 9×13, 13×18, 15×21, 20×30, 30×40 cm, A5, A4, A3, A3+, A2 (pangkas untuk memenuhi lembar atau pasangkan seluruh foto).
- Pemangkasan pintar: deteksi wajah (YuNet), orang dan hewan peliharaan (YOLOX), model pose; bingkai juga dapat diatur manual.
- Koreksi warna per foto: kecerahan, kontras, gamma, bayangan/sorotan, saturasi, suhu/rona, RGB, otomatis, hitam-putih, sepia, pengurangan derau, penajaman.
- Manajemen warna: profil ICC printer dan sakelar Windows ICM.
- Perencanaan cetak: beberapa foto per lembar, bleed per sisi, satu pekerjaan per lembar dengan jeda, pemeriksaan sebelum cetak (dpi, kecocokan).
- Ekspor ke JPEG, TIFF, PNG, dan PDF.
- Mode agen AI: setiap langkah adalah perintah yang mengembalikan JSON (baris perintah atau server MCP untuk Claude Desktop). Lihat [AGENT.md](AGENT.md) (bahasa Rusia).
- Bahasa antarmuka versi Qt: Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча (dipilih di Pengaturan; bawaan mengikuti bahasa sistem; bahasa Arab dari kanan ke kiri). Terjemahan mencakup layar utama, dibuat secara mesin, dan belum ditinjau penutur asli; teks yang belum diterjemahkan tampil dalam bahasa Inggris.

## Instalasi

- Windows dengan Python 3.9+ ("Add python.exe to PATH"), atau jalankan `install.bat`: memasang Python (jika belum ada), paket, dan membuat pintasan. Perlu internet.
- Instalasi manual: `pip install -r requirements.txt`.

## Menjalankan versi Qt

Klik dua kali `run_qt.bat` (memasang Pillow, pillow-heif, PySide6 dan menjalankan `photo_crop_qt.py`). Uji mandiri: `selftest_qt.bat`. Jendela Tkinter lama: `python photo_crop.py`.

### Model deteksi

Model YuNet / YOLOX (~36 MB) tidak disertakan dalam repositori; diunduh saat pertama kali digunakan (atau dengan `python smart_crop.py setup`) ke `%APPDATA%\PhotoCrop\models`.

## Mode agen dan MCP

Jalankan `mcp_config.bat` (atau `python photo_crop.py mcp-config`) untuk mendapatkan blok konfigurasi, tambahkan ke `claude_desktop_config.json` (`%APPDATA%\Claude\`), lalu mulai ulang Claude Desktop. Untuk exe hasil build, blok `mcpServers.photocrop` berbentuk:

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

Perintah utama: `open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`.

Baris perintah: `python photo_crop.py agent set_format format=10x15`; `python photo_crop.py agent --list` menampilkan semua perintah. Status disimpan di `%APPDATA%\PhotoCrop\agent_state.json`. `PHOTOCROP_AGENT_DRYRUN=1` melarang pencetakan sungguhan.

## Membangun file exe

`build_exe.bat` membangun `PhotoCrop.exe` (jendela Tkinter) dan `PhotoCropAgent.exe` (konsol, untuk MCP) dengan PyInstaller. Catatan: skrip kemudian menghapus `build\` dan file `.spec`. Versi Qt dibangun dengan `pyinstaller PhotoCropQt.spec` → `dist\PhotoCropQt.exe`. Mendorong tag `v*` menjalankan alur kerja GitHub Actions (`.github/workflows/build.yml`) yang membangun `PhotoCropQt.exe` dan `PhotoCropAgent.exe` lalu melampirkannya ke GitHub Release.

## Lisensi

License: [KopiTehnik Print Licence](LICENSE)
