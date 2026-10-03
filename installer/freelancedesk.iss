; Установщик FreelanceDesk (Inno Setup 6).
; Собирается из build.ps1: ISCC /DAppVersion=1.0.0 installer\freelancedesk.iss
; На входе — папка dist\FreelanceDesk после PyInstaller.
;
; Установка без прав администратора — в папку пользователя
; (%LOCALAPPDATA%\Programs\FreelanceDesk). Данные программы лежат
; отдельно (%APPDATA%\FreelanceDesk) и при удалении не стираются.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; Постоянный идентификатор: по нему Windows узнаёт программу при обновлении
AppId={{6B0D2A3E-6F0B-4C56-9C7E-1F2D9A4B7C11}
AppName=FreelanceDesk
AppVersion={#AppVersion}
AppVerName=FreelanceDesk {#AppVersion}
AppPublisher=ZniKDK
AppPublisherURL=https://github.com/ZniKDK/FreelanceDesk
AppSupportURL=https://github.com/ZniKDK/FreelanceDesk/issues
DefaultDirName={autopf}\FreelanceDesk
DefaultGroupName=FreelanceDesk
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=FreelanceDesk-{#AppVersion}-Setup
SetupIconFile=..\resources\app.ico
UninstallDisplayIcon={app}\FreelanceDesk.exe
UninstallDisplayName=FreelanceDesk
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\FreelanceDesk\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\FreelanceDesk"; Filename: "{app}\FreelanceDesk.exe"
Name: "{group}\{cm:UninstallProgram,FreelanceDesk}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\FreelanceDesk"; Filename: "{app}\FreelanceDesk.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FreelanceDesk.exe"; Description: "{cm:LaunchProgram,FreelanceDesk}"; Flags: nowait postinstall skipifsilent
