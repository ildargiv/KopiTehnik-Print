; Установщик KopiTehnik Print: одна программа, установка для текущего пользователя, без прав администратора.
; Сборка: ISCC.exe /DAppVersion=1.7.0 installer\PhotoCrop.iss  (PhotoCropQt.exe должен лежать в dist\)
#ifndef AppVersion
  #define AppVersion "1.7.0"
#endif

[Setup]
AppId={{6B0F7C0E-5B7E-4B63-9C0A-4B0D9B1B0C11}
AppName=KopiTehnik Print
AppVersion={#AppVersion}
AppPublisher=Ildar Gaisin
AppPublisherURL=https://github.com/ildargiv/KopiTehnik-Print
AppSupportURL=https://github.com/ildargiv/KopiTehnik-Print/issues
AppUpdatesURL=https://github.com/ildargiv/KopiTehnik-Print/releases
DefaultDirName={autopf}\KopiTehnik Print
DefaultGroupName=KopiTehnik Print
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\PhotoCropQt.exe
SetupIconFile=..\brand\app_icon.ico
OutputDir=..\dist
LicenseFile=..\LICENSE
OutputBaseFilename=KopiTehnikPrint-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "pt"; MessagesFile: "compiler:Languages\Portuguese.isl"
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "ja"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "pl"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "uk"; MessagesFile: "compiler:Languages\Ukrainian.isl"
Name: "ar"; MessagesFile: "languages\Arabic.isl"
Name: "zhcn"; MessagesFile: "languages\ChineseSimplified.isl"
Name: "zhtw"; MessagesFile: "languages\ChineseTraditional.isl"
Name: "ko"; MessagesFile: "languages\Korean.isl"
Name: "th"; MessagesFile: "languages\Thai.isl"
Name: "hi"; MessagesFile: "languages\Hindi.islu"
Name: "id"; MessagesFile: "languages\Indonesian.isl"
Name: "vi"; MessagesFile: "languages\Vietnamese.isl"
Name: "tt"; MessagesFile: "languages\Tatar.isl"

[CustomMessages]
ru.TaskMcp=Подключить ИИ-агента (MCP) к Claude Desktop
ru.TaskMcpHint=Агент сможет работать с окном программы: видеть ваши фото, улучшать, кадрировать и печатать. Настройка Claude Desktop обновится автоматически.
ru.GroupAgent=ИИ-агент
en.TaskMcp=Connect the AI agent (MCP) to Claude Desktop
en.TaskMcpHint=The agent will work with the programme window: see your photos, enhance, crop and print. The Claude Desktop configuration is updated automatically.
en.GroupAgent=AI agent
de.TaskMcp=KI-Agent (MCP) mit Claude Desktop verbinden
de.TaskMcpHint=Der Agent arbeitet mit dem Programmfenster: Er sieht Ihre Fotos, verbessert, beschneidet und druckt. Die Konfiguration von Claude Desktop wird automatisch aktualisiert.
de.GroupAgent=KI-Agent
fr.TaskMcp=Connecter l'agent IA (MCP) à Claude Desktop
fr.TaskMcpHint=L'agent travaillera avec la fenêtre du programme : il voit vos photos, les améliore, les recadre et les imprime. La configuration de Claude Desktop est mise à jour automatiquement.
fr.GroupAgent=Agent IA
es.TaskMcp=Conectar el agente de IA (MCP) a Claude Desktop
es.TaskMcpHint=El agente trabajará con la ventana del programa: verá sus fotos, las mejorará, recortará e imprimirá. La configuración de Claude Desktop se actualiza automáticamente.
es.GroupAgent=Agente de IA
pt.TaskMcp=Ligar o agente de IA (MCP) ao Claude Desktop
pt.TaskMcpHint=O agente trabalha com a janela do programa: vê as suas fotografias, melhora, recorta e imprime. A configuração do Claude Desktop é atualizada automaticamente.
pt.GroupAgent=Agente de IA
it.TaskMcp=Collega l'agente IA (MCP) a Claude Desktop
it.TaskMcpHint=L'agente lavorerà con la finestra del programma: vede le foto, le migliora, le ritaglia e le stampa. La configurazione di Claude Desktop viene aggiornata automaticamente.
it.GroupAgent=Agente IA
ja.TaskMcp=AIエージェント(MCP)をClaude Desktopに接続する
ja.TaskMcpHint=エージェントはプログラムのウィンドウで作業し、写真を見て、補正・トリミング・印刷を行います。Claude Desktopの設定は自動的に更新されます。
ja.GroupAgent=AIエージェント
pl.TaskMcp=Połącz agenta AI (MCP) z Claude Desktop
pl.TaskMcpHint=Agent będzie pracował w oknie programu: zobaczy zdjęcia, poprawi je, przytnie i wydrukuje. Konfiguracja Claude Desktop zostanie zaktualizowana automatycznie.
pl.GroupAgent=Agent AI
tr.TaskMcp=Yapay zekâ ajanını (MCP) Claude Desktop'a bağla
tr.TaskMcpHint=Ajan program penceresiyle çalışır: fotoğraflarınızı görür, iyileştirir, kırpar ve yazdırır. Claude Desktop yapılandırması otomatik olarak güncellenir.
tr.GroupAgent=Yapay zekâ ajanı
uk.TaskMcp=Підключити ШІ-агента (MCP) до Claude Desktop
uk.TaskMcpHint=Агент працюватиме з вікном програми: бачитиме ваші фото, покращуватиме, кадруватиме й друкуватиме. Налаштування Claude Desktop оновиться автоматично.
uk.GroupAgent=ШІ-агент
ar.TaskMcp=ربط وكيل الذكاء الاصطناعي (MCP) بـ Claude Desktop
ar.TaskMcpHint=سيعمل الوكيل مع نافذة البرنامج: يرى صورك ويحسّنها ويقصّها ويطبعها. يتم تحديث إعدادات Claude Desktop تلقائيًا.
ar.GroupAgent=وكيل الذكاء الاصطناعي
zhcn.TaskMcp=将 AI 代理 (MCP) 连接到 Claude Desktop
zhcn.TaskMcpHint=代理将使用程序窗口工作:查看您的照片,进行优化、裁剪和打印。Claude Desktop 的配置会自动更新。
zhcn.GroupAgent=AI 代理
zhtw.TaskMcp=將 AI 代理 (MCP) 連接到 Claude Desktop
zhtw.TaskMcpHint=代理將使用程式視窗工作:檢視您的相片,進行優化、裁切與列印。Claude Desktop 的設定會自動更新。
zhtw.GroupAgent=AI 代理
ko.TaskMcp=AI 에이전트(MCP)를 Claude Desktop에 연결
ko.TaskMcpHint=에이전트가 프로그램 창에서 작업합니다. 사진을 보고 보정, 자르기, 인쇄를 합니다. Claude Desktop 설정은 자동으로 업데이트됩니다.
ko.GroupAgent=AI 에이전트
th.TaskMcp=เชื่อมต่อเอเจนต์ AI (MCP) กับ Claude Desktop
th.TaskMcpHint=เอเจนต์จะทำงานในหน้าต่างโปรแกรม: ดูภาพถ่ายของคุณ ปรับปรุง ครอบตัด และพิมพ์ การตั้งค่า Claude Desktop จะอัปเดตโดยอัตโนมัติ
th.GroupAgent=เอเจนต์ AI
hi.TaskMcp=AI एजेंट (MCP) को Claude Desktop से जोड़ें
hi.TaskMcpHint=एजेंट प्रोग्राम की विंडो में काम करेगा: आपकी तस्वीरें देखेगा, सुधारेगा, क्रॉप करेगा और प्रिंट करेगा। Claude Desktop की सेटिंग अपने आप अपडेट हो जाएगी।
hi.GroupAgent=AI एजेंट
id.TaskMcp=Hubungkan agen AI (MCP) ke Claude Desktop
id.TaskMcpHint=Agen akan bekerja di jendela program: melihat foto Anda, memperbaiki, memotong, dan mencetak. Konfigurasi Claude Desktop diperbarui secara otomatis.
id.GroupAgent=Agen AI
vi.TaskMcp=Kết nối tác nhân AI (MCP) với Claude Desktop
vi.TaskMcpHint=Tác nhân sẽ làm việc trong cửa sổ chương trình: xem ảnh của bạn, cải thiện, cắt và in. Cấu hình Claude Desktop được cập nhật tự động.
vi.GroupAgent=Tác nhân AI
tt.TaskMcp=ЯИ-агентны (MCP) Claude Desktop белән тоташтыру
tt.TaskMcpHint=Агент программа тәрәзәсендә эшләячәк: фотоларыгызны күрә, яхшырта, кисә һәм басма чыгара. Claude Desktop көйләүләре үзеннән-үзе яңартыла.
tt.GroupAgent=ЯИ-агент

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "mcp"; Description: "{cm:TaskMcp}"; GroupDescription: "{cm:GroupAgent}"

[Files]
Source: "..\dist\PhotoCropQt.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\KopiTehnik Print"; Filename: "{app}\PhotoCropQt.exe"
Name: "{autodesktop}\KopiTehnik Print"; Filename: "{app}\PhotoCropQt.exe"; Tasks: desktopicon

[Run]
; Подключение агента: записывает photocrop в claude_desktop_config.json (копия .bak остаётся) и включает приём подключений в окне
Filename: "{app}\PhotoCropQt.exe"; Parameters: "mcp-install"; Flags: runhidden waituntilterminated; Tasks: mcp
Filename: "{app}\PhotoCropQt.exe"; Description: "{cm:LaunchProgram,KopiTehnik Print}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\PhotoCropQt.exe"; Parameters: "mcp-uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveMcp"
