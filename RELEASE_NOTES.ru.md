[English](RELEASE_NOTES.md) | **Русский** | [Español](RELEASE_NOTES.es.md) | [简体中文](RELEASE_NOTES.zh-CN.md) | [繁體中文](RELEASE_NOTES.zh-Hant.md) | [Deutsch](RELEASE_NOTES.de.md) | [Français](RELEASE_NOTES.fr.md) | [Português](RELEASE_NOTES.pt.md) | [日本語](RELEASE_NOTES.ja.md) | [한국어](RELEASE_NOTES.ko.md) | [Türkçe](RELEASE_NOTES.tr.md) | [Bahasa Indonesia](RELEASE_NOTES.id.md) | [العربية](RELEASE_NOTES.ar.md) | [हिन्दी](RELEASE_NOTES.hi.md) | [Italiano](RELEASE_NOTES.it.md) | [Polski](RELEASE_NOTES.pl.md) | [Українська](RELEASE_NOTES.uk.md) | [Tiếng Việt](RELEASE_NOTES.vi.md) | [ไทย](RELEASE_NOTES.th.md) | [Татарча](RELEASE_NOTES.tt.md)

# Заметки о выпуске — v1.5.0

- **Управление драйвером Epson на вкладке «Принтер»** (T50, P50, TX650, PX660, R290, 1410, L805, L1800, L8050, L18050): качество печати, печать без полей и цветокоррекция драйвера; режимы, которые драйвер откатывает на выбранной бумаге, скрыты, а при смене типа бумаги из-за «Без полей» программа предупреждает.
- **Быстрый старт**: три ячейки на каждый принтер с форматом, бумагой, качеством, «без полей», цветовым профилем и обработкой; сохранить, переименовать, применить.
- Кнопки **«Проверка дюз»** и **«Прочистка головки»** (с предупреждением, что прочистка расходует чернила и наполняет памперс).
- **Тестовый лист печати** (клин, тени/света, цвета, оттенки кожи I–VI, градиенты, резкость) на текущий размер бумаги.
- **ИИ-агент (MCP)**: новые инструменты `epson_settings`, `quick_start` (list / save / apply / clear), `printer_maintenance` (нужен `confirm=true`) и `add_test_sheet`; `select_printer` теперь действительно переключает принтер в окне.
- Новая кнопка **«Настройки»** в шапке (шестерёнка с подписью, поворачивается при наведении).
- Счётчик фото не обрезает цифры; в окне «О программе» указано, что программа не связана с Epson.

Файлы выпуска: `KopiTehnikPrint-Setup-1.5.0.exe`.
