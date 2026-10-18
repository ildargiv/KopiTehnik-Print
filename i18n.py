# -*- coding: utf-8 -*-
"""Interface translations for PhotoCrop (Qt version).

The program's source strings are Russian; photo_crop.EN maps them to English (ru -> en).
This module adds the other interface languages on top of English: every language is a list of
translations aligned with CORE (English strings, in the same order).  Lookup: ru -> en (photo_crop.EN)
-> this module.  A string that is missing here is shown in English; Russian ("ru") is the original text.

Machine-assisted translations of a core set of ~130 strings (menus, buttons, settings, adjustments, print).
They have not been reviewed by native speakers; see README / RELEASE_NOTES.
"""
import locale

LANG_NAMES = {
    "ja": "日本語", "ko": "한국어", "tr": "Türkçe", "id": "Bahasa Indonesia", "ar": "العربية", "hi": "हिन्दी",
    "it": "Italiano", "pl": "Polski", "uk": "Українська", "vi": "Tiếng Việt", "th": "ไทย",
    "zh-Hant": "繁體中文", "tt": "Татарча",
}
RTL_LANGS = {"ar"}
# font families (Windows system fonts first, then fallbacks) for scripts the default UI font lacks
FONT_FAMILIES = {
    "ja": ["Yu Gothic UI", "Meiryo UI", "MS UI Gothic", "Noto Sans CJK JP"],
    "ko": ["Malgun Gothic", "Noto Sans CJK KR"],
    "zh-Hant": ["Microsoft JhengHei UI", "Microsoft JhengHei", "PMingLiU", "Noto Sans CJK TC"],
    "th": ["Leelawadee UI", "Leelawadee", "Tahoma", "Noto Sans Thai"],
    "hi": ["Nirmala UI", "Mangal", "Noto Sans Devanagari"],
    "ar": ["Segoe UI", "Tahoma", "Arial", "Noto Sans Arabic"],
}

CORE = """Open
Open photos or a folder
Settings
Print
Photos
Format
Save checked
Save project…
Open project…
Cancel
Close
Apply
Reset
Delete
Browse…
Copy
Paste
Name
Size
Places
Desktop
Pictures
Downloads
Folder
Errors
Done
Error
Preparing…
Cancelled
Up one level
Rotate photo left 90°
Rotate photo right 90°
Previous photo (←)
Next photo (→)
Undo (Ctrl+Z)
Redo (Ctrl+Y)
Check all photos
Uncheck all
Reset this photo's frame
Copies
Fewer copies
More copies
Rule-of-thirds grid
Level the frame (0°)
This photo
Auto
Portrait
Landscape
Crop
Fit
Saving
Next to photos, in folder
To another folder
No folder chosen
Choose folder
Resolution, dpi
File type
JPEG quality
Exact print size
Subfolder per format
Copies count in file name
Printer profile
Choose profile…
Show out-of-gamut colours
Colour
Colour adjustments
Apply to
this photo
all checked
Basic
Detail
off
contrast
colour
B/W
Auto levels
Brightness
Contrast
Gamma (midtones)
Shadows (lighten +)
Highlights (recover −)
Saturation
Vibrance (pale colours)
Temperature (cooler ← → warmer)
Tint (green ← → magenta)
Red
Green
Blue
Colour noise
Print sharpening, %
Sharpening radius (at 300 ppi)
Sharpening threshold
Show original (hold)
Photo settings
Reset for all
Double-click a slider to reset it.
Black & white
Sepia
Enhance
Super
Printer
Printer:
Paper:
Layout
What to print:
Left
Top
Right
Bottom
Cut marks
Processing
Black & white printing
Start printing?
No photos to print.
No printer selected or printer unavailable.
Open photos first.
General
Cropping
About
Interface language
Appearance
Brand
Dark
Light
Black, grey & white
Last used
Settings are stored in
Photo cropping and printing program.
Where to save
Files saved
Open the folder?
Saving is in progress. Quit anyway?""".split("\n")

_RAW = {}

_RAW["ja"] = """開く
写真またはフォルダーを開く
設定
印刷
写真
サイズ
チェックしたものを保存
プロジェクトを保存…
プロジェクトを開く…
キャンセル
閉じる
適用
リセット
削除
参照…
コピー
貼り付け
名前
サイズ
場所
デスクトップ
ピクチャ
ダウンロード
フォルダー
エラー
完了
エラー
準備中…
キャンセルしました
一つ上の階層へ
写真を左に90°回転
写真を右に90°回転
前の写真 (←)
次の写真 (→)
元に戻す (Ctrl+Z)
やり直す (Ctrl+Y)
すべての写真にチェック
すべてのチェックを外す
この写真の枠をリセット
部数
部数を減らす
部数を増やす
三分割グリッド
枠を水平にする (0°)
この写真
自動
縦
横
トリミング
全体表示
保存
写真と同じ場所のフォルダーへ
別のフォルダーへ
フォルダーが未選択です
フォルダーを選択
解像度 (dpi)
ファイル形式
JPEG品質
正確な印刷サイズ
サイズ別のサブフォルダー
ファイル名に部数を含める
プリンタープロファイル
プロファイルを選択…
色域外の色を表示
カラー
色調整
適用範囲
この写真
チェックした写真すべて
基本
詳細
オフ
コントラスト
カラー
白黒
自動レベル
明るさ
コントラスト
ガンマ (中間調)
シャドウ (明るく +)
ハイライト (戻す −)
彩度
自然な彩度 (淡い色)
色温度 (寒色 ← → 暖色)
色合い (緑 ← → マゼンタ)
赤
緑
青
カラーノイズ
印刷時シャープ (%)
シャープ半径 (300 ppi 時)
シャープのしきい値
元画像を表示 (押している間)
写真の設定
すべてリセット
スライダーをダブルクリックでリセット。
白黒
セピア
補正
スーパー
プリンター
プリンター:
用紙:
レイアウト
印刷する対象:
左
上
右
下
トンボ
処理
白黒印刷
印刷を開始しますか？
印刷する写真がありません。
プリンターが選択されていないか、使用できません。
先に写真を開いてください。
一般
トリミング
情報
表示言語
外観
ブランド
ダーク
ライト
黒・グレー・白
前回の場所
設定の保存先
写真のトリミングと印刷のプログラム。
保存先
保存したファイル
フォルダーを開きますか？
保存中です。それでも終了しますか？""".split("\n")

_RAW["ko"] = """열기
사진 또는 폴더 열기
설정
인쇄
사진
형식
선택한 항목 저장
프로젝트 저장…
프로젝트 열기…
취소
닫기
적용
초기화
삭제
찾아보기…
복사
붙여넣기
이름
크기
위치
바탕 화면
사진
다운로드
폴더
오류
완료
오류
준비 중…
취소됨
위로
사진을 왼쪽으로 90° 회전
사진을 오른쪽으로 90° 회전
이전 사진 (←)
다음 사진 (→)
실행 취소 (Ctrl+Z)
다시 실행 (Ctrl+Y)
모든 사진 선택
모두 선택 해제
이 사진의 프레임 초기화
매수
매수 줄이기
매수 늘리기
삼등분 격자
프레임 수평 맞추기 (0°)
이 사진
자동
세로
가로
자르기
맞추기
저장
사진 옆 폴더에
다른 폴더에
폴더가 선택되지 않음
폴더 선택
해상도 (dpi)
파일 형식
JPEG 품질
정확한 인쇄 크기
형식별 하위 폴더
파일 이름에 매수 포함
프린터 프로파일
프로파일 선택…
색 영역 밖 색상 표시
색상
색 보정
적용 대상
이 사진
선택한 모든 사진
기본
세부
끔
대비
컬러
흑백
자동 레벨
밝기
대비
감마 (중간톤)
그림자 (밝게 +)
하이라이트 (복원 −)
채도
생동감 (옅은 색)
색온도 (차갑게 ← → 따뜻하게)
색조 (녹색 ← → 자홍)
빨강
초록
파랑
색 노이즈
인쇄 선명도 (%)
선명도 반경 (300 ppi 기준)
선명도 임계값
원본 보기 (누르고 있기)
사진 설정
모두 초기화
슬라이더를 두 번 클릭하면 초기화됩니다.
흑백
세피아
향상
슈퍼
프린터
프린터:
용지:
레이아웃
인쇄 대상:
왼쪽
위
오른쪽
아래
재단선
처리
흑백 인쇄
인쇄를 시작할까요?
인쇄할 사진이 없습니다.
프린터가 선택되지 않았거나 사용할 수 없습니다.
먼저 사진을 여세요.
일반
자르기
정보
인터페이스 언어
모양
브랜드
어둡게
밝게
검정·회색·흰색
마지막 사용 위치
설정 저장 위치
사진 자르기 및 인쇄 프로그램.
저장 위치
저장된 파일
폴더를 열까요?
저장 중입니다. 그래도 종료할까요?""".split("\n")

_RAW["tr"] = """Aç
Fotoğrafları veya klasörü aç
Ayarlar
Yazdır
Fotoğraflar
Biçim
İşaretlileri kaydet
Projeyi kaydet…
Projeyi aç…
İptal
Kapat
Uygula
Sıfırla
Sil
Gözat…
Kopyala
Yapıştır
Ad
Boyut
Konumlar
Masaüstü
Resimler
İndirilenler
Klasör
Hatalar
Tamam
Hata
Hazırlanıyor…
İptal edildi
Bir üst düzey
Fotoğrafı 90° sola döndür
Fotoğrafı 90° sağa döndür
Önceki fotoğraf (←)
Sonraki fotoğraf (→)
Geri al (Ctrl+Z)
Yinele (Ctrl+Y)
Tüm fotoğrafları işaretle
Tüm işaretleri kaldır
Bu fotoğrafın çerçevesini sıfırla
Kopya
Daha az kopya
Daha fazla kopya
Üçler kuralı ızgarası
Çerçeveyi düzelt (0°)
Bu fotoğraf
Otomatik
Dikey
Yatay
Kırp
Sığdır
Kaydetme
Fotoğrafların yanında, klasöre
Başka bir klasöre
Klasör seçilmedi
Klasör seç
Çözünürlük, dpi
Dosya türü
JPEG kalitesi
Tam baskı boyutu
Biçime göre alt klasör
Dosya adında kopya sayısı
Yazıcı profili
Profil seç…
Gamut dışı renkleri göster
Renk
Renk ayarları
Uygulanacak
bu fotoğraf
işaretli tümü
Temel
Ayrıntı
kapalı
kontrast
renk
S/B
Otomatik seviyeler
Parlaklık
Kontrast
Gama (orta tonlar)
Gölgeler (aç +)
Parlak alanlar (geri al −)
Doygunluk
Canlılık (soluk renkler)
Sıcaklık (daha soğuk ← → daha sıcak)
Ton (yeşil ← → eflatun)
Kırmızı
Yeşil
Mavi
Renk gürültüsü
Baskı keskinleştirme, %
Keskinleştirme yarıçapı (300 ppi'de)
Keskinleştirme eşiği
Orijinali göster (basılı tut)
Fotoğraf ayarları
Hepsini sıfırla
Sıfırlamak için kaydırıcıya çift tıklayın.
Siyah beyaz
Sepya
İyileştir
Süper
Yazıcı
Yazıcı:
Kağıt:
Düzen
Yazdırılacak:
Sol
Üst
Sağ
Alt
Kesim işaretleri
İşleme
Siyah beyaz baskı
Yazdırma başlasın mı?
Yazdırılacak fotoğraf yok.
Yazıcı seçilmedi veya kullanılamıyor.
Önce fotoğrafları açın.
Genel
Kırpma
Hakkında
Arayüz dili
Görünüm
Marka
Koyu
Açık
Siyah, gri ve beyaz
Son kullanılan
Ayarların saklandığı yer
Fotoğraf kırpma ve yazdırma programı.
Kaydedilecek yer
Kaydedilen dosyalar
Klasör açılsın mı?
Kaydetme sürüyor. Yine de çıkılsın mı?""".split("\n")

_RAW["id"] = """Buka
Buka foto atau folder
Pengaturan
Cetak
Foto
Format
Simpan yang dicentang
Simpan proyek…
Buka proyek…
Batal
Tutup
Terapkan
Atur ulang
Hapus
Telusuri…
Salin
Tempel
Nama
Ukuran
Lokasi
Desktop
Gambar
Unduhan
Folder
Kesalahan
Selesai
Kesalahan
Menyiapkan…
Dibatalkan
Naik satu tingkat
Putar foto 90° ke kiri
Putar foto 90° ke kanan
Foto sebelumnya (←)
Foto berikutnya (→)
Urungkan (Ctrl+Z)
Ulangi (Ctrl+Y)
Centang semua foto
Hapus semua centang
Atur ulang bingkai foto ini
Salinan
Kurangi salinan
Tambah salinan
Kisi sepertiga
Luruskan bingkai (0°)
Foto ini
Otomatis
Potret
Lanskap
Pangkas
Pas
Penyimpanan
Di samping foto, dalam folder
Ke folder lain
Folder belum dipilih
Pilih folder
Resolusi, dpi
Jenis file
Kualitas JPEG
Ukuran cetak tepat
Subfolder per format
Jumlah salinan di nama file
Profil printer
Pilih profil…
Tampilkan warna di luar gamut
Warna
Penyesuaian warna
Terapkan ke
foto ini
semua yang dicentang
Dasar
Detail
mati
kontras
warna
H/P
Level otomatis
Kecerahan
Kontras
Gamma (nada tengah)
Bayangan (cerahkan +)
Sorotan (pulihkan −)
Saturasi
Vibrance (warna pucat)
Suhu (lebih dingin ← → lebih hangat)
Rona (hijau ← → magenta)
Merah
Hijau
Biru
Derau warna
Penajaman cetak, %
Radius penajaman (pada 300 ppi)
Ambang penajaman
Tampilkan asli (tahan)
Pengaturan foto
Atur ulang semua
Klik dua kali pada penggeser untuk mengatur ulang.
Hitam putih
Sepia
Tingkatkan
Super
Printer
Printer:
Kertas:
Tata letak
Yang dicetak:
Kiri
Atas
Kanan
Bawah
Tanda potong
Pemrosesan
Cetak hitam putih
Mulai mencetak?
Tidak ada foto untuk dicetak.
Printer belum dipilih atau tidak tersedia.
Buka foto terlebih dahulu.
Umum
Pemangkasan
Tentang
Bahasa antarmuka
Tampilan
Merek
Gelap
Terang
Hitam, abu-abu & putih
Terakhir digunakan
Pengaturan disimpan di
Program pemangkasan dan pencetakan foto.
Lokasi penyimpanan
File tersimpan
Buka folder?
Penyimpanan sedang berlangsung. Tetap keluar?""".split("\n")

_RAW["ar"] = """فتح
فتح صور أو مجلد
الإعدادات
طباعة
الصور
التنسيق
حفظ المحدد
حفظ المشروع…
فتح مشروع…
إلغاء
إغلاق
تطبيق
إعادة ضبط
حذف
استعراض…
نسخ
لصق
الاسم
الحجم
الأماكن
سطح المكتب
الصور
التنزيلات
مجلد
أخطاء
تم
خطأ
جارٍ التحضير…
تم الإلغاء
مستوى أعلى
تدوير الصورة 90° لليسار
تدوير الصورة 90° لليمين
الصورة السابقة (←)
الصورة التالية (→)
تراجع (Ctrl+Z)
إعادة (Ctrl+Y)
تحديد كل الصور
إلغاء تحديد الكل
إعادة ضبط إطار هذه الصورة
النسخ
نسخ أقل
نسخ أكثر
شبكة الأثلاث
تسوية الإطار (0°)
هذه الصورة
تلقائي
عمودي
أفقي
اقتصاص
ملاءمة
الحفظ
بجانب الصور، في مجلد
في مجلد آخر
لم يتم اختيار مجلد
اختيار مجلد
الدقة، dpi
نوع الملف
جودة JPEG
حجم الطباعة الدقيق
مجلد فرعي لكل تنسيق
عدد النسخ في اسم الملف
ملف تعريف الطابعة
اختيار ملف التعريف…
إظهار الألوان خارج النطاق
اللون
ضبط الألوان
تطبيق على
هذه الصورة
كل المحدد
أساسي
تفاصيل
إيقاف
التباين
لون
أبيض وأسود
مستويات تلقائية
السطوع
التباين
غاما (الدرجات المتوسطة)
الظلال (تفتيح +)
الإضاءات (استعادة −)
التشبع
النشاط اللوني (الألوان الباهتة)
درجة الحرارة (أبرد ← → أدفأ)
الصبغة (أخضر ← → أرجواني)
أحمر
أخضر
أزرق
ضجيج الألوان
حدة الطباعة، %
نصف قطر الحدة (عند 300 ppi)
عتبة الحدة
عرض الأصل (اضغط مع الاستمرار)
إعدادات الصورة
إعادة ضبط الكل
انقر مرتين على المنزلق لإعادة ضبطه.
أبيض وأسود
بني داكن (سيبيا)
تحسين
فائق
الطابعة
الطابعة:
الورق:
التخطيط
ما سيُطبع:
يسار
أعلى
يمين
أسفل
علامات القص
المعالجة
طباعة بالأبيض والأسود
بدء الطباعة؟
لا توجد صور للطباعة.
لم يتم اختيار طابعة أو أنها غير متاحة.
افتح الصور أولاً.
عام
الاقتصاص
حول
لغة الواجهة
المظهر
العلامة التجارية
داكن
فاتح
أسود ورمادي وأبيض
آخر استخدام
مكان حفظ الإعدادات
برنامج اقتصاص الصور وطباعتها.
مكان الحفظ
الملفات المحفوظة
فتح المجلد؟
الحفظ جارٍ. هل تريد الخروج على أي حال؟""".split("\n")

_RAW["hi"] = """खोलें
फ़ोटो या फ़ोल्डर खोलें
सेटिंग
प्रिंट
फ़ोटो
फ़ॉर्मेट
चुने हुए सहेजें
प्रोजेक्ट सहेजें…
प्रोजेक्ट खोलें…
रद्द करें
बंद करें
लागू करें
रीसेट
हटाएँ
ब्राउज़…
कॉपी
पेस्ट
नाम
आकार
स्थान
डेस्कटॉप
चित्र
डाउनलोड
फ़ोल्डर
त्रुटियाँ
हो गया
त्रुटि
तैयारी हो रही है…
रद्द किया गया
एक स्तर ऊपर
फ़ोटो को 90° बाएँ घुमाएँ
फ़ोटो को 90° दाएँ घुमाएँ
पिछली फ़ोटो (←)
अगली फ़ोटो (→)
पूर्ववत (Ctrl+Z)
फिर से करें (Ctrl+Y)
सभी फ़ोटो चुनें
सभी चयन हटाएँ
इस फ़ोटो का फ़्रेम रीसेट करें
प्रतियाँ
कम प्रतियाँ
अधिक प्रतियाँ
तिहाई का ग्रिड
फ़्रेम सीधा करें (0°)
यह फ़ोटो
स्वचालित
पोर्ट्रेट
लैंडस्केप
क्रॉप
फ़िट
सहेजना
फ़ोटो के पास, फ़ोल्डर में
किसी अन्य फ़ोल्डर में
फ़ोल्डर नहीं चुना गया
फ़ोल्डर चुनें
रेज़ोल्यूशन, dpi
फ़ाइल प्रकार
JPEG गुणवत्ता
सटीक प्रिंट आकार
हर फ़ॉर्मेट के लिए उप-फ़ोल्डर
फ़ाइल नाम में प्रतियों की संख्या
प्रिंटर प्रोफ़ाइल
प्रोफ़ाइल चुनें…
गैमट से बाहर के रंग दिखाएँ
रंग
रंग समायोजन
इन पर लागू करें
यह फ़ोटो
सभी चुने हुए
बुनियादी
विवरण
बंद
कंट्रास्ट
रंग
श्वेत-श्याम
स्वचालित लेवल
चमक
कंट्रास्ट
गामा (मध्य टोन)
छायाएँ (हल्का +)
हाइलाइट (वापस −)
संतृप्ति
वाइब्रेंस (फीके रंग)
तापमान (ठंडा ← → गर्म)
टिंट (हरा ← → मैजेंटा)
लाल
हरा
नीला
रंग का नॉइज़
प्रिंट शार्पनिंग, %
शार्पनिंग त्रिज्या (300 ppi पर)
शार्पनिंग सीमा
मूल दिखाएँ (दबाए रखें)
फ़ोटो सेटिंग
सभी रीसेट करें
रीसेट करने के लिए स्लाइडर पर डबल-क्लिक करें।
श्वेत-श्याम
सेपिया
बेहतर बनाएँ
सुपर
प्रिंटर
प्रिंटर:
कागज़:
लेआउट
क्या प्रिंट करना है:
बायाँ
ऊपर
दायाँ
नीचे
कट मार्क
प्रोसेसिंग
श्वेत-श्याम प्रिंट
प्रिंट शुरू करें?
प्रिंट करने के लिए कोई फ़ोटो नहीं है।
प्रिंटर चुना नहीं गया या उपलब्ध नहीं है।
पहले फ़ोटो खोलें।
सामान्य
क्रॉपिंग
परिचय
इंटरफ़ेस भाषा
रूप-रंग
ब्रांड
गहरा
हल्का
काला, स्लेटी और सफ़ेद
पिछली बार उपयोग किया
सेटिंग यहाँ सहेजी जाती हैं
फ़ोटो क्रॉप और प्रिंट करने का प्रोग्राम।
कहाँ सहेजना है
सहेजी गई फ़ाइलें
फ़ोल्डर खोलें?
सहेजना जारी है। फिर भी बाहर निकलें?""".split("\n")

_RAW["it"] = """Apri
Apri foto o una cartella
Impostazioni
Stampa
Foto
Formato
Salva selezionate
Salva progetto…
Apri progetto…
Annulla
Chiudi
Applica
Reimposta
Elimina
Sfoglia…
Copia
Incolla
Nome
Dimensione
Risorse
Desktop
Immagini
Download
Cartella
Errori
Fatto
Errore
Preparazione…
Annullato
Livello superiore
Ruota la foto di 90° a sinistra
Ruota la foto di 90° a destra
Foto precedente (←)
Foto successiva (→)
Annulla (Ctrl+Z)
Ripeti (Ctrl+Y)
Seleziona tutte le foto
Deseleziona tutto
Reimposta il riquadro di questa foto
Copie
Meno copie
Più copie
Griglia dei terzi
Raddrizza il riquadro (0°)
Questa foto
Auto
Verticale
Orizzontale
Ritaglia
Adatta
Salvataggio
Accanto alle foto, nella cartella
In un'altra cartella
Nessuna cartella scelta
Scegli cartella
Risoluzione, dpi
Tipo di file
Qualità JPEG
Dimensione di stampa esatta
Sottocartella per formato
Numero di copie nel nome del file
Profilo stampante
Scegli profilo…
Mostra colori fuori gamma
Colore
Regolazioni colore
Applica a
questa foto
tutte le selezionate
Base
Dettaglio
no
contrasto
colore
B/N
Livelli automatici
Luminosità
Contrasto
Gamma (mezzitoni)
Ombre (schiarisci +)
Alteluci (recupera −)
Saturazione
Vividezza (colori tenui)
Temperatura (più fredda ← → più calda)
Tinta (verde ← → magenta)
Rosso
Verde
Blu
Rumore del colore
Nitidezza in stampa, %
Raggio di nitidezza (a 300 ppi)
Soglia di nitidezza
Mostra originale (tieni premuto)
Impostazioni foto
Reimposta tutte
Doppio clic su un cursore per reimpostarlo.
Bianco e nero
Seppia
Migliora
Super
Stampante
Stampante:
Carta:
Impaginazione
Cosa stampare:
Sinistra
Alto
Destra
Basso
Crocini di taglio
Elaborazione
Stampa in bianco e nero
Avviare la stampa?
Nessuna foto da stampare.
Nessuna stampante selezionata o stampante non disponibile.
Apri prima le foto.
Generale
Ritaglio
Informazioni
Lingua dell'interfaccia
Aspetto
Marchio
Scuro
Chiaro
Nero, grigio e bianco
Ultima usata
Le impostazioni sono salvate in
Programma per ritagliare e stampare foto.
Dove salvare
File salvati
Aprire la cartella?
Salvataggio in corso. Uscire comunque?""".split("\n")

_RAW["pl"] = """Otwórz
Otwórz zdjęcia lub folder
Ustawienia
Drukuj
Zdjęcia
Format
Zapisz zaznaczone
Zapisz projekt…
Otwórz projekt…
Anuluj
Zamknij
Zastosuj
Resetuj
Usuń
Przeglądaj…
Kopiuj
Wklej
Nazwa
Rozmiar
Miejsca
Pulpit
Obrazy
Pobrane
Folder
Błędy
Gotowe
Błąd
Przygotowywanie…
Anulowano
Poziom wyżej
Obróć zdjęcie o 90° w lewo
Obróć zdjęcie o 90° w prawo
Poprzednie zdjęcie (←)
Następne zdjęcie (→)
Cofnij (Ctrl+Z)
Ponów (Ctrl+Y)
Zaznacz wszystkie zdjęcia
Odznacz wszystko
Resetuj ramkę tego zdjęcia
Kopie
Mniej kopii
Więcej kopii
Siatka trzecich
Wyrównaj ramkę (0°)
To zdjęcie
Auto
Pionowa
Pozioma
Przytnij
Dopasuj
Zapisywanie
Obok zdjęć, w folderze
Do innego folderu
Nie wybrano folderu
Wybierz folder
Rozdzielczość, dpi
Typ pliku
Jakość JPEG
Dokładny rozmiar wydruku
Podfolder dla formatu
Liczba kopii w nazwie pliku
Profil drukarki
Wybierz profil…
Pokaż kolory poza gamutem
Kolor
Korekta kolorów
Zastosuj do
to zdjęcie
wszystkie zaznaczone
Podstawowe
Szczegóły
wył.
kontrast
kolor
Cz/B
Poziomy automatyczne
Jasność
Kontrast
Gamma (półtony)
Cienie (rozjaśnij +)
Światła (odzyskaj −)
Nasycenie
Jaskrawość (blade kolory)
Temperatura (zimniej ← → cieplej)
Odcień (zielony ← → magenta)
Czerwony
Zielony
Niebieski
Szum kolorów
Wyostrzanie do druku, %
Promień wyostrzania (przy 300 ppi)
Próg wyostrzania
Pokaż oryginał (przytrzymaj)
Ustawienia zdjęcia
Resetuj wszystkie
Kliknij dwukrotnie suwak, aby go zresetować.
Czarno-białe
Sepia
Popraw
Super
Drukarka
Drukarka:
Papier:
Układ
Co drukować:
Lewy
Górny
Prawy
Dolny
Znaczniki cięcia
Przetwarzanie
Druk czarno-biały
Rozpocząć drukowanie?
Brak zdjęć do wydruku.
Nie wybrano drukarki lub jest niedostępna.
Najpierw otwórz zdjęcia.
Ogólne
Kadrowanie
O programie
Język interfejsu
Wygląd
Firmowy
Ciemny
Jasny
Czarno-szaro-biały
Ostatnio używany
Ustawienia są zapisane w
Program do kadrowania i drukowania zdjęć.
Gdzie zapisać
Zapisane pliki
Otworzyć folder?
Trwa zapisywanie. Mimo to zakończyć?""".split("\n")

_RAW["uk"] = """Відкрити
Відкрити фото або теку
Налаштування
Друк
Фото
Формат
Зберегти позначені
Зберегти проєкт…
Відкрити проєкт…
Скасувати
Закрити
Застосувати
Скинути
Видалити
Огляд…
Копіювати
Вставити
Назва
Розмір
Місця
Робочий стіл
Зображення
Завантаження
Тека
Помилки
Готово
Помилка
Підготовка…
Скасовано
На рівень вище
Повернути фото вліво на 90°
Повернути фото вправо на 90°
Попереднє фото (←)
Наступне фото (→)
Скасувати дію (Ctrl+Z)
Повторити (Ctrl+Y)
Позначити всі фото
Зняти всі позначки
Скинути рамку цього фото
Копій
Менше копій
Більше копій
Сітка третин
Вирівняти рамку (0°)
Це фото
Авто
Книжкова
Альбомна
Обрізати
Вписати
Збереження
Поруч із фото, у теку
В іншу теку
Теку не вибрано
Вибрати теку
Роздільність, dpi
Тип файлу
Якість JPEG
Точний розмір друку
Підтека за форматом
Кількість копій в імені файлу
Профіль принтера
Вибрати профіль…
Показати кольори поза охопленням
Колір
Корекція кольору
Змінювати
це фото
усі позначені
Основне
Деталі
вимк.
контраст
колір
Ч/Б
Авторівні
Яскравість
Контраст
Гамма (середні тони)
Тіні (освітлити +)
Світла (повернути −)
Насиченість
Соковитість (бліді кольори)
Температура (холодніше ← → тепліше)
Відтінок (зелений ← → пурпуровий)
Червоний
Зелений
Синій
Шум кольору
Різкість під час друку, %
Радіус різкості (за 300 ppi)
Поріг різкості
Показати оригінал (утримуйте)
Налаштування фото
Скинути в усіх
Подвійний клік по повзунку скидає його.
Чорно-біле
Сепія
Покращити
Супер
Принтер
Принтер:
Папір:
Розкладка
Що друкувати:
Ліве
Верхнє
Праве
Нижнє
Мітки різання
Обробка
Чорно-білий друк
Почати друк?
Немає фото для друку.
Принтер не вибрано або він недоступний.
Спочатку відкрийте фото.
Загальні
Кадрування
Про програму
Мова інтерфейсу
Оформлення
Фірмова
Темна
Світла
Чорно-сіро-біла
Остання використана
Налаштування зберігаються у файлі
Програма для кадрування та друку фотографій.
Куди зберігати
Збережено файлів
Відкрити теку?
Триває збереження. Все одно вийти?""".split("\n")

_RAW["vi"] = """Mở
Mở ảnh hoặc thư mục
Cài đặt
In
Ảnh
Khổ
Lưu các ảnh đã chọn
Lưu dự án…
Mở dự án…
Hủy
Đóng
Áp dụng
Đặt lại
Xóa
Duyệt…
Sao chép
Dán
Tên
Kích thước
Vị trí
Màn hình nền
Hình ảnh
Tải xuống
Thư mục
Lỗi
Xong
Lỗi
Đang chuẩn bị…
Đã hủy
Lên một cấp
Xoay ảnh trái 90°
Xoay ảnh phải 90°
Ảnh trước (←)
Ảnh sau (→)
Hoàn tác (Ctrl+Z)
Làm lại (Ctrl+Y)
Chọn tất cả ảnh
Bỏ chọn tất cả
Đặt lại khung của ảnh này
Số bản
Ít bản hơn
Nhiều bản hơn
Lưới một phần ba
Làm thẳng khung (0°)
Ảnh này
Tự động
Dọc
Ngang
Cắt
Vừa khít
Lưu
Cạnh ảnh, trong thư mục
Vào thư mục khác
Chưa chọn thư mục
Chọn thư mục
Độ phân giải, dpi
Loại tệp
Chất lượng JPEG
Kích thước in chính xác
Thư mục con theo khổ
Số bản trong tên tệp
Hồ sơ máy in
Chọn hồ sơ…
Hiện màu ngoài gam màu
Màu
Chỉnh màu
Áp dụng cho
ảnh này
tất cả ảnh đã chọn
Cơ bản
Chi tiết
tắt
tương phản
màu
Đen trắng
Tự động cân bằng mức
Độ sáng
Tương phản
Gamma (tông giữa)
Vùng tối (làm sáng +)
Vùng sáng (khôi phục −)
Độ bão hòa
Độ rực (màu nhạt)
Nhiệt độ màu (lạnh hơn ← → ấm hơn)
Sắc thái (xanh lục ← → hồng tím)
Đỏ
Xanh lục
Xanh lam
Nhiễu màu
Làm nét khi in, %
Bán kính làm nét (ở 300 ppi)
Ngưỡng làm nét
Xem ảnh gốc (giữ nút)
Cài đặt ảnh
Đặt lại tất cả
Nhấp đúp vào thanh trượt để đặt lại.
Đen trắng
Nâu đỏ (sepia)
Cải thiện
Siêu
Máy in
Máy in:
Giấy:
Bố cục
Nội dung in:
Trái
Trên
Phải
Dưới
Dấu cắt
Xử lý
In đen trắng
Bắt đầu in?
Không có ảnh để in.
Chưa chọn máy in hoặc máy in không khả dụng.
Hãy mở ảnh trước.
Chung
Cắt ảnh
Giới thiệu
Ngôn ngữ giao diện
Giao diện
Thương hiệu
Tối
Sáng
Đen, xám và trắng
Dùng gần nhất
Cài đặt được lưu tại
Chương trình cắt và in ảnh.
Nơi lưu
Tệp đã lưu
Mở thư mục?
Đang lưu. Vẫn thoát?""".split("\n")

_RAW["th"] = """เปิด
เปิดรูปภาพหรือโฟลเดอร์
การตั้งค่า
พิมพ์
รูปภาพ
ขนาด
บันทึกที่เลือก
บันทึกโปรเจกต์…
เปิดโปรเจกต์…
ยกเลิก
ปิด
นำไปใช้
รีเซ็ต
ลบ
เลือกไฟล์…
คัดลอก
วาง
ชื่อ
ขนาด
ตำแหน่ง
เดสก์ท็อป
รูปภาพ
ดาวน์โหลด
โฟลเดอร์
ข้อผิดพลาด
เสร็จแล้ว
ข้อผิดพลาด
กำลังเตรียม…
ยกเลิกแล้ว
ขึ้นไปหนึ่งระดับ
หมุนรูปไปทางซ้าย 90°
หมุนรูปไปทางขวา 90°
รูปก่อนหน้า (←)
รูปถัดไป (→)
เลิกทำ (Ctrl+Z)
ทำซ้ำ (Ctrl+Y)
เลือกทุกรูป
ยกเลิกการเลือกทั้งหมด
รีเซ็ตกรอบของรูปนี้
จำนวนสำเนา
ลดจำนวนสำเนา
เพิ่มจำนวนสำเนา
เส้นกริดแบ่งสามส่วน
ปรับกรอบให้ตรง (0°)
รูปนี้
อัตโนมัติ
แนวตั้ง
แนวนอน
ครอป
พอดี
การบันทึก
ข้างรูป ในโฟลเดอร์
ไปยังโฟลเดอร์อื่น
ยังไม่ได้เลือกโฟลเดอร์
เลือกโฟลเดอร์
ความละเอียด (dpi)
ชนิดไฟล์
คุณภาพ JPEG
ขนาดพิมพ์ที่แน่นอน
โฟลเดอร์ย่อยตามขนาด
ใส่จำนวนสำเนาในชื่อไฟล์
โปรไฟล์เครื่องพิมพ์
เลือกโปรไฟล์…
แสดงสีที่อยู่นอกขอบเขตสี
สี
ปรับแต่งสี
ใช้กับ
รูปนี้
ทุกรูปที่เลือก
พื้นฐาน
รายละเอียด
ปิด
คอนทราสต์
สี
ขาวดำ
ระดับอัตโนมัติ
ความสว่าง
คอนทราสต์
แกมมา (โทนกลาง)
เงา (ทำให้สว่าง +)
ไฮไลต์ (ดึงกลับ −)
ความอิ่มตัว
ความสดของสี (สีซีด)
อุณหภูมิสี (เย็นลง ← → อุ่นขึ้น)
โทนสี (เขียว ← → ม่วงแดง)
แดง
เขียว
น้ำเงิน
สัญญาณรบกวนสี
ความคมชัดตอนพิมพ์ %
รัศมีความคมชัด (ที่ 300 ppi)
เกณฑ์ความคมชัด
แสดงต้นฉบับ (กดค้างไว้)
การตั้งค่ารูป
รีเซ็ตทั้งหมด
ดับเบิลคลิกแถบเลื่อนเพื่อรีเซ็ต
ขาวดำ
ซีเปีย
ปรับปรุง
ซูเปอร์
เครื่องพิมพ์
เครื่องพิมพ์:
กระดาษ:
เลย์เอาต์
สิ่งที่จะพิมพ์:
ซ้าย
บน
ขวา
ล่าง
เครื่องหมายตัด
การประมวลผล
พิมพ์ขาวดำ
เริ่มพิมพ์หรือไม่
ไม่มีรูปที่จะพิมพ์
ยังไม่ได้เลือกเครื่องพิมพ์หรือใช้งานไม่ได้
กรุณาเปิดรูปภาพก่อน
ทั่วไป
การครอป
เกี่ยวกับ
ภาษาของอินเทอร์เฟซ
รูปลักษณ์
แบรนด์
มืด
สว่าง
ดำ เทา และขาว
ใช้ล่าสุด
การตั้งค่าถูกเก็บไว้ที่
โปรแกรมครอปและพิมพ์รูปภาพ
บันทึกไปที่
ไฟล์ที่บันทึกแล้ว
เปิดโฟลเดอร์หรือไม่
กำลังบันทึกอยู่ ต้องการออกต่อไปหรือไม่""".split("\n")

_RAW["zh-Hant"] = """開啟
開啟照片或資料夾
設定
列印
照片
尺寸
儲存已勾選項目
儲存專案…
開啟專案…
取消
關閉
套用
重設
刪除
瀏覽…
複製
貼上
名稱
大小
位置
桌面
圖片
下載
資料夾
錯誤
完成
錯誤
準備中…
已取消
上一層
將照片向左旋轉 90°
將照片向右旋轉 90°
上一張照片 (←)
下一張照片 (→)
復原 (Ctrl+Z)
重做 (Ctrl+Y)
勾選所有照片
取消全部勾選
重設此照片的裁切框
份數
減少份數
增加份數
三分法格線
校正裁切框 (0°)
此照片
自動
直向
橫向
裁切
符合
儲存
照片旁的資料夾
另一個資料夾
尚未選擇資料夾
選擇資料夾
解析度 (dpi)
檔案類型
JPEG 品質
精確列印尺寸
依尺寸建立子資料夾
檔名包含份數
印表機描述檔
選擇描述檔…
顯示超出色域的顏色
色彩
色彩調整
套用到
此照片
所有已勾選項目
基本
細節
關閉
對比
色彩
黑白
自動色階
亮度
對比
Gamma（中間調）
陰影（提亮 +）
亮部（還原 −）
飽和度
鮮豔度（淡色）
色溫（偏冷 ← → 偏暖）
色調（綠 ← → 洋紅）
紅
綠
藍
色彩雜訊
列印銳利化 (%)
銳利化半徑 (300 ppi 時)
銳利化臨界值
顯示原圖（按住）
照片設定
全部重設
連按兩下滑桿即可重設。
黑白
復古棕
增強
超強
印表機
印表機：
紙張：
版面配置
要列印的內容：
左
上
右
下
裁切線
處理
黑白列印
開始列印？
沒有可列印的照片。
未選擇印表機，或印表機無法使用。
請先開啟照片。
一般
裁切
關於
介面語言
外觀
品牌
深色
淺色
黑、灰、白
上次使用
設定儲存於
照片裁切與列印程式。
儲存位置
已儲存的檔案
要開啟資料夾嗎？
正在儲存。仍要結束嗎？""".split("\n")

_RAW["tt"] = """Ачу
Фотоларны яки папканы ачу
Көйләүләр
Бастыру
Фотолар
Формат
Билгеләнгәннәрне саклау
Проектны саклау…
Проектны ачу…
Баш тарту
Ябу
Куллану
Ташлау
Бетерү
Күчереп карау…
Күчереп алу
Куеп кую
Исем
Зурлык
Урыннар
Эш өстәле
Рәсемнәр
Йөкләнмәләр
Папка
Хаталар
Әзер
Хата
Әзерләнә…
Кире кагылды
Бер дәрәҗә югарыга
Фотоны 90° сулга бору
Фотоны 90° уңга бору
Алдагы фото (←)
Киләсе фото (→)
Кире кайтару (Ctrl+Z)
Кабатлау (Ctrl+Y)
Барлык фотоларны билгеләү
Барлык билгеләрне алу
Бу фотоның рамкасын ташлау
Күчермәләр
Азрак күчермә
Күбрәк күчермә
Өчтән бер челтәре
Рамканы тигезләү (0°)
Бу фото
Авто
Тик
Ятма
Кисү
Сыйдыру
Саклау
Фото янында, папкага
Икенче папкага
Папка сайланмаган
Папканы сайлау
Ачыклык, dpi
Файл төре
JPEG сыйфаты
Басманың төгәл зурлыгы
Формат буенча эчке папка
Файл исемендә күчермә саны
Принтер профиле
Профильне сайлау…
Колорит чикләреннән тыш төсләрне күрсәтү
Төс
Төсне көйләү
Куллану:
бу фото
барлык билгеләнгәннәр
Төп
Детальләр
сүнгән
контраст
төс
А/К
Авто-дәрәҗәләр
Яктылык
Контраст
Гамма (урта тоннар)
Күләгәләр (яктырту +)
Яктылар (кайтару −)
Туендырылганлык
Төсләр тулылыгы (сүрән төсләр)
Температура (суыграк ← → җылырак)
Төсмер (яшел ← → шәмәхә)
Кызыл
Яшел
Зәңгәр
Төс шавы
Басканда ачыклык, %
Ачыклык радиусы (300 ppi вакытында)
Ачыклык чиге
Оригиналны күрсәтү (тотып торыгыз)
Фото көйләүләре
Барысын ташлау
Ташлау өчен шуткычка ике тапкыр басыгыз.
Ак-кара
Сепия
Яхшырту
Супер
Принтер
Принтер:
Кәгазь:
Урнаштыру
Нәрсә бастырырга:
Сул
Өске
Уң
Түбән
Кисү билгеләре
Эшкәртү
Ак-кара басма
Бастыруны башларгамы?
Бастыру өчен фото юк.
Принтер сайланмаган яки ул ирекле түгел.
Башта фотоларны ачыгыз.
Гомуми
Кадрлау
Программа турында
Интерфейс теле
Рәвеш
Фирма
Караңгы
Якты
Кара-соры-ак
Соңгы кулланылган
Көйләүләр сакланган урын
Фотоларны кадрлау һәм бастыру программасы.
Кайда саклау
Сакланган файллар
Папканы ачарга?
Саклау бара. Барыбер чыгыргамы?""".split("\n")

TABLE = {}
for _code, _lines in _RAW.items():
    if len(_lines) == len(CORE):
        TABLE[_code] = dict(zip(CORE, _lines))
del _RAW
try:                                         # second batch: main-screen strings (i18n_more.py)
    import i18n_more as _more
    for _code, _lines in _more.RAW2.items():
        if _code in TABLE and len(_lines) == len(_more.CORE2):
            TABLE[_code].update(zip(_more.CORE2, _lines))
except Exception:
    pass


def lookup(lang, english):
    """Translation of an English string into `lang`, or None."""
    t = TABLE.get(lang)
    return t.get(english) if t else None


def detect_language(supported):
    """Default UI language from the system locale: a supported language, else ru for Russian, else en."""
    try:
        loc = (locale.getdefaultlocale()[0] or "")
    except Exception:
        loc = ""
    try:
        if not loc and hasattr(locale, "getlocale"):
            loc = locale.getlocale()[0] or ""
    except Exception:
        pass
    loc = loc.replace("-", "_")
    low = loc.lower()
    if low.startswith("zh"):
        code = "zh-Hant" if any(x in low for x in ("tw", "hk", "mo", "hant")) else "zh-Hans"
        return code if code in supported else "en"
    base = low.split("_")[0]
    if base == "nb" or base == "nn":
        base = "no"
    if base == "in":
        base = "id"
    return base if base in supported else "en"
