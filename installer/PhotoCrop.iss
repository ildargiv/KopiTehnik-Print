; Установщик KopiTehnik Print: одна программа, установка для текущего пользователя, без прав администратора.
; Сборка: ISCC.exe /DAppVersion=1.4.0 installer\PhotoCrop.iss  (PhotoCropQt.exe должен лежать в dist\)
#ifndef AppVersion
  #define AppVersion "1.4.0"
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

[CustomMessages]
ru.TaskMcp=Подключить ИИ-агента (MCP) к Claude Desktop
ru.TaskMcpHint=Агент сможет работать с окном программы: видеть ваши фото, улучшать, кадрировать и печатать. Настройка Claude Desktop обновится автоматически.
ru.GroupAgent=ИИ-агент
en.TaskMcp=Connect the AI agent (MCP) to Claude Desktop
en.TaskMcpHint=The agent will work with the programme window: see your photos, enhance, crop and print. The Claude Desktop configuration is updated automatically.
en.GroupAgent=AI agent

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
