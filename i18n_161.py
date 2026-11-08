# -*- coding: utf-8 -*-
"""Interface strings added in 1.5-1.6 (multi-printer, Quick Start, zoom/crop, Epson driver): ru -> en, and a short set for the other languages."""

EN = {
    "Подсказка": "Hint",
    "ИИ-агент работает": "AI agent is working",
    "По числу — выбираете, сколько фото на листе. По размеру — задаёте размер рамки, лист нарезается на столько таких рамок, сколько влезает.":
        "By number: you choose how many photos per sheet. By size: you set the frame size and the sheet is cut into as many such frames as fit.",
    "Печать на нескольких принтерах: отметьте больше одного, и листы разойдутся между ними":
        "Printing on several printers: tick more than one and the sheets are shared between them",
    "Качество печати": "Print quality",
    "Отключить цветокоррекцию драйвера": "Turn off the driver's colour correction",
    "Сохранить быстрый старт": "Save Quick Start",
    "Например: матовая, высокое, зеркально": "For example: matte, high quality, mirror",
    "Переименовать": "Rename",
    "Название ячейки": "Cell name",
    "Кадрировать — фото заполняет рамку целиком, лишнее обрезается. Вписать — фото помещается в рамку целиком, без обрезки (где пропорции не совпали, остаются белые поля).":
        "Crop: the photo fills the whole frame and the excess is cut off. Fit: the whole photo is placed in the frame without cutting (white margins remain where the proportions differ).",
    "Оригинал": "Original",
    "Поместить": "Fit",
    "Обрезать": "Crop",
    "Щёлкните по фото в месте, которое должно быть серым или белым (правая кнопка — отмена)":
        "Click the photo where it should be grey or white (right button cancels)",
    "Настройки скопированы — перейдите к другому фото и нажмите «Вставить»":
        "Settings copied. Go to another photo and press Paste",
    "Принтеры для печати": "Printers to print on",
    "Отправлять на принтеры по очереди (если драйвер зависает при параллельной печати)":
        "Send to the printers one at a time (if the driver hangs on parallel printing)",
    "Раздавать блоками: каждому принтеру подряд идущие листы, стопки не перемешиваются":
        "Distribute in blocks: each printer gets consecutive sheets, so the stacks do not get mixed",
    "Пока агент работает, окно только для просмотра: вы видите, что он делает, но не можете случайно ему помешать. Кнопка «Забрать управление» снимает блокировку.":
        "While the agent works the window is view-only: you see what it does but cannot get in its way by accident. The Take control button removes the lock.",
    "Принтер не подключён: очередь печатает в файл. Команда обслуживания никуда не отправлена.":
        "The printer is not connected: the queue prints to a file. The maintenance command was not sent anywhere.",
    "без привязки к принтеру": "not tied to a printer",
    "Ячейка пуста. Настройте всё как нужно и нажмите «Сохранить» под кнопкой.":
        "The cell is empty. Set everything up and press Save under the button.",
    "Цветокоррекция драйвера включена при цветовом профиле.": "The driver's colour correction is on together with a colour profile.",
    "Цветокоррекция драйвера включена, она исказит цвет цветового профиля. Отключить её сейчас?":
        "The driver's colour correction is on and will distort the colour profile. Turn it off now?",
    "Разные модели принтеров: цвет отпечатков может немного отличаться.": "Different printer models: the colour of the prints may differ slightly.",
    "Отметьте принтеры. Если отмечено больше одного, кнопка «Печать» распределит листы между ними: освободившийся принтер берёт следующий лист.":
        "Tick the printers. If more than one is ticked, the Print button shares the sheets between them: a printer that becomes free takes the next sheet.",
    "Как сохранено для принтера": "As saved for the printer",
    "Отключить печать на нескольких принтерах": "Turn off printing on several printers",
    "Включить печать на нескольких принтерах": "Turn on printing on several printers",
    "Программа не связана с компанией Epson. Epson и названия моделей — торговые марки их владельцев и используются только для описания совместимости. Управление драйвером принтера и обслуживание (проверка дюз, прочистка) вы используете на свой риск: прочистка расходует чернила.":
        "The programme is not affiliated with Epson. Epson and the model names are trademarks of their owners and are used only to describe compatibility. You use the printer driver controls and maintenance (nozzle check, cleaning) at your own risk: cleaning uses ink.",
    "Выключено": "Off",
    "Внимание: цветокоррекция драйвера включена, она исказит цвет профиля. Отключите её на странице «Принтер».":
        "Warning: the driver's colour correction is on and will distort the profile colour. Turn it off on the Printer page.",
    "Не удалось включить ИИ-агента": "Could not turn the AI agent on",
    "Разрешить?": "Allow?",
    "Драйвер не принял это качество печати. Выберите его в «Свойствах драйвера».": "The driver did not accept this print quality. Choose it in the driver properties.",
    "Пустая ячейка": "Empty cell",
    "Цветокоррекция драйвера включена при цветовом профиле — цвет исказится. Отключите её на странице «Принтер».":
        "The driver's colour correction is on together with a colour profile, so the colour will be distorted. Turn it off on the Printer page.",
    "Печать на нескольких принтерах": "Printing on several printers",
    "выключена": "off",
    "Нет ячеек «Быстрого старта»": "No Quick Start cells",
    "Режим печати из «Быстрого старта» этого принтера: бумага, качество, цвет.": "Print mode from this printer's Quick Start: paper, quality, colour.",
    "У этого принтера нет сохранённых ячеек «Быстрого старта»: выберите принтер на вкладке «Принтер», настройте бумагу и качество и нажмите дискету в ячейке.":
        "This printer has no saved Quick Start cells: choose the printer on the Printer tab, set paper and quality and press the floppy disk in a cell.",
    "Принтеры не найдены.": "No printers found.",
    "Не удалось отправить команду принтеру": "Could not send the command to the printer",
    "Печать без полей доступна только на фотобумаге: тип бумаги изменён на {m}. После отключения «Без полей» выберите нужный тип бумаги заново.":
        "Borderless printing is only available on photo paper: the paper type was changed to {m}. After turning Borderless off, choose the paper type again.",
    "Драйвер не включил печать без полей: для этого размера бумаги или типа бумаги она недоступна.":
        "The driver did not enable borderless printing: it is not available for this paper size or type.",
    "Настройки драйвера (бумага, качество) относятся к другой модели и не применены.":
        "The driver settings (paper, quality) belong to another model and were not applied.",
    "Ни один из отмеченных принтеров не готов": "None of the ticked printers is ready",
    "Не участвуют": "Not taking part",
    "лист": "sheet",
    "Не удалось обрезать фото": "Could not crop the photo",
    "Цветокоррекция драйвера": "Driver colour correction",
    "листов/мин": "sheets/min",
    "копия": "copy",
    "ошибка": "error",
    "Настройки драйвера не удалось применить.": "The driver settings could not be applied.",
    "да": "yes",
    "включена": "on",
    "отключена": "off",
    "бумага в драйвере другого размера": "the paper in the driver has another size",
    "нет своего профиля, настройки как в окне": "no profile of its own, settings as in the window",
    "выбыл": "dropped out",
    "нет своего профиля": "no profile of its own",
    "замедлился, получает меньше листов": "slowed down, gets fewer sheets",
    "офлайн": "offline",
    "Принтер замедлился, получает меньше листов": "The printer slowed down and gets fewer sheets",
    "Принтер выбыл": "The printer dropped out",
    "порт FILE: (печать в файл), на каждый лист спросит имя файла; смените порт в свойствах принтера":
        "port FILE: (print to file) will ask for a file name for each sheet; change the port in the printer properties",
}

EN_FMT = {
    "Профиль: {t}": "Profile: {t}",
    "Принтер: {p}": "Printer: {p}",
    "Печать на нескольких принтерах. Листов: {n}, копий каждого: {k}.": "Printing on several printers. Sheets: {n}, copies of each: {k}.",
    "Баланс белого: r {r}, g {g}, b {b}": "White balance: r {r}, g {g}, b {b}",
    "Бумага в драйвере: авто, {f}": "Paper in the driver: auto, {f}",
    "Профиль: {t} (взято из «{n}»)": "Profile: {t} (taken from “{n}”)",
    "Профиль: {t} (общие настройки)": "Profile: {t} (common settings)",
    "Показывать ячеек: {n}": "Cells shown: {n}",
    "Допечатать недостающее: листов {n}. Начать?": "Print what is missing: {n} sheets. Start?",
    "Допечатать недостающее ({n})": "Print what is missing ({n})",
    "Включено, порт {p}": "On, port {p}",
    "принтеров: {n}": "printers: {n}",
    "включена, принтеров: {n}": "on, printers: {n}",
    "Влезает: {n} ({c}×{r}), рамка {w}×{h} мм": "Fits: {n} ({c}×{r}), frame {w}×{h} mm",
    "ИИ-агент хочет напечатать листов: {n}.": "The AI agent wants to print sheets: {n}.",
    "Принтер «{p}» не найден, оставлен текущий.": "Printer “{p}” was not found, the current one is kept.",
    "лист {a} из {b}": "sheet {a} of {b}",
    "Не напечатано листов: {n}": "Sheets not printed: {n}",
}

# other languages: English -> translation, key UI labels of 1.5-1.6 (machine-assisted, not reviewed by native speakers)
_KEYS = ["Original", "Fit", "Crop", "Printers", "Printers to print on", "Printing on several printers", "Print quality", "Rename", "Allow?",
         "Empty cell", "Cell name", "No printers found.", "Not taking part", "offline", "on", "off", "yes", "error", "sheet", "copy", "Hint"]
_RAW = {
    "ja": ["オリジナル", "全体を収める", "トリミング", "プリンター", "印刷するプリンター", "複数のプリンターで印刷", "印刷品質", "名前を変更", "許可しますか?", "空のセル", "セル名", "プリンターが見つかりません。", "対象外", "オフライン", "オン", "オフ", "はい", "エラー", "シート", "コピー", "ヒント"],
    "ko": ["원본", "맞추기", "자르기", "프린터", "인쇄할 프린터", "여러 프린터로 인쇄", "인쇄 품질", "이름 바꾸기", "허용하시겠습니까?", "빈 셀", "셀 이름", "프린터를 찾을 수 없습니다.", "제외됨", "오프라인", "켜짐", "꺼짐", "예", "오류", "시트", "복사본", "힌트"],
    "tr": ["Orijinal", "Sığdır", "Kırp", "Yazıcılar", "Yazdırılacak yazıcılar", "Birden fazla yazıcıda yazdırma", "Baskı kalitesi", "Yeniden adlandır", "İzin verilsin mi?", "Boş hücre", "Hücre adı", "Yazıcı bulunamadı.", "Katılmıyor", "çevrimdışı", "açık", "kapalı", "evet", "hata", "sayfa", "kopya", "İpucu"],
    "id": ["Asli", "Muatkan", "Pangkas", "Printer", "Printer untuk mencetak", "Cetak di beberapa printer", "Kualitas cetak", "Ganti nama", "Izinkan?", "Sel kosong", "Nama sel", "Printer tidak ditemukan.", "Tidak ikut", "offline", "aktif", "nonaktif", "ya", "kesalahan", "lembar", "salinan", "Petunjuk"],
    "ar": ["الأصل", "احتواء", "اقتصاص", "الطابعات", "الطابعات للطباعة", "الطباعة على عدة طابعات", "جودة الطباعة", "إعادة تسمية", "هل تسمح؟", "خلية فارغة", "اسم الخلية", "لم يتم العثور على طابعات.", "غير مشاركة", "غير متصلة", "مفعّل", "متوقف", "نعم", "خطأ", "ورقة", "نسخة", "تلميح"],
    "hi": ["मूल", "फ़िट करें", "काटें", "प्रिंटर", "प्रिंट करने के प्रिंटर", "कई प्रिंटर पर प्रिंट", "प्रिंट गुणवत्ता", "नाम बदलें", "अनुमति दें?", "खाली सेल", "सेल का नाम", "कोई प्रिंटर नहीं मिला।", "शामिल नहीं", "ऑफ़लाइन", "चालू", "बंद", "हाँ", "त्रुटि", "शीट", "प्रति", "सुझाव"],
    "it": ["Originale", "Adatta", "Ritaglia", "Stampanti", "Stampanti su cui stampare", "Stampa su più stampanti", "Qualità di stampa", "Rinomina", "Consentire?", "Cella vuota", "Nome della cella", "Nessuna stampante trovata.", "Non partecipa", "offline", "attivo", "disattivo", "sì", "errore", "foglio", "copia", "Suggerimento"],
    "pl": ["Oryginał", "Dopasuj", "Przytnij", "Drukarki", "Drukarki do druku", "Drukowanie na kilku drukarkach", "Jakość wydruku", "Zmień nazwę", "Zezwolić?", "Pusta komórka", "Nazwa komórki", "Nie znaleziono drukarek.", "Nie biorą udziału", "offline", "włączone", "wyłączone", "tak", "błąd", "arkusz", "kopia", "Wskazówka"],
    "uk": ["Оригінал", "Вмістити", "Обрізати", "Принтери", "Принтери для друку", "Друк на кількох принтерах", "Якість друку", "Перейменувати", "Дозволити?", "Порожня комірка", "Назва комірки", "Принтери не знайдено.", "Не беруть участі", "офлайн", "увімкнено", "вимкнено", "так", "помилка", "аркуш", "копія", "Підказка"],
    "vi": ["Gốc", "Vừa khung", "Cắt", "Máy in", "Máy in để in", "In trên nhiều máy in", "Chất lượng in", "Đổi tên", "Cho phép?", "Ô trống", "Tên ô", "Không tìm thấy máy in.", "Không tham gia", "ngoại tuyến", "bật", "tắt", "có", "lỗi", "tờ", "bản sao", "Gợi ý"],
    "th": ["ต้นฉบับ", "ใส่พอดี", "ครอป", "เครื่องพิมพ์", "เครื่องพิมพ์ที่ใช้พิมพ์", "พิมพ์บนหลายเครื่องพิมพ์", "คุณภาพการพิมพ์", "เปลี่ยนชื่อ", "อนุญาตหรือไม่?", "ช่องว่าง", "ชื่อช่อง", "ไม่พบเครื่องพิมพ์", "ไม่ร่วมพิมพ์", "ออฟไลน์", "เปิด", "ปิด", "ใช่", "ข้อผิดพลาด", "แผ่น", "สำเนา", "คำแนะนำ"],
    "zh-Hant": ["原始", "放入", "裁切", "印表機", "要列印的印表機", "在多台印表機上列印", "列印品質", "重新命名", "允許嗎?", "空白儲存格", "儲存格名稱", "找不到印表機。", "未參與", "離線", "開", "關", "是", "錯誤", "紙張", "份", "提示"],
    "tt": ["Оригинал", "Сыйдыру", "Кисү", "Принтерлар", "Басма өчен принтерлар", "Берничә принтерда басу", "Басма сыйфаты", "Исемен үзгәртү", "Рөхсәт итәргәме?", "Буш күзәнәк", "Күзәнәк исеме", "Принтерлар табылмады.", "Катнашмый", "офлайн", "кабулы", "сүнгән", "әйе", "хата", "бит", "күчермә", "Киңәш"],
}
OTHER = {code: dict(zip(_KEYS, vals)) for code, vals in _RAW.items() if len(vals) == len(_KEYS)}
