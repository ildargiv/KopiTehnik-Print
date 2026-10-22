[English](RELEASE_NOTES.md) | **Русский** | [Español](RELEASE_NOTES.es.md) | [简体中文](RELEASE_NOTES.zh-CN.md) | [繁體中文](RELEASE_NOTES.zh-Hant.md) | [Deutsch](RELEASE_NOTES.de.md) | [Français](RELEASE_NOTES.fr.md) | [Português](RELEASE_NOTES.pt.md) | [日本語](RELEASE_NOTES.ja.md) | [한국어](RELEASE_NOTES.ko.md) | [Türkçe](RELEASE_NOTES.tr.md) | [Bahasa Indonesia](RELEASE_NOTES.id.md) | [العربية](RELEASE_NOTES.ar.md) | [हिन्दी](RELEASE_NOTES.hi.md) | [Italiano](RELEASE_NOTES.it.md) | [Polski](RELEASE_NOTES.pl.md) | [Українська](RELEASE_NOTES.uk.md) | [Tiếng Việt](RELEASE_NOTES.vi.md) | [ไทย](RELEASE_NOTES.th.md) | [Татарча](RELEASE_NOTES.tt.md)

# Заметки о выпуске — v1.3.0

- **Поправка цвета принтера.** На вкладке «Принтер» новый переключатель и кнопка «Настроить поправку…». Оттенок (зелёный ↔ пурпурный), баланс холодный ↔ тёплый, яркость, насыщенность и правка по шести цветам (красный, жёлтый, зелёный, голубой, синий, пурпурный) компенсируют цветовой уклон вашего принтера и бумаги. Работает с профилем ICC и без него, применяется только при печати и сохранении и никогда не показывается на экране: она нужна, чтобы отпечаток совпал с экраном.
- Поправка хранится в профиле печати (принтер + формат листа + тип бумаги) вместе с профилем ICC; при смене профиля ICC она обнуляется. Агент читает и задаёт её через `set_color_profile` (`pcorr_on`, `pcorr`).
- В разделе «О программе» название теперь просто «KopiTehnik Print».
- Исправлена проверка имени пресета во встроенной самопроверке.

Файлы выпуска: `PhotoCropQt.exe`, `KopiTehnikPrint-Setup-1.3.0.exe`.
