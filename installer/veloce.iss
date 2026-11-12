; Veloce — Windows installer (Inno Setup 6)
; Built in CI:  ISCC.exe installer\veloce.iss /DAppVersion=1.1.1
; Installs per user (no admin prompt) from the PyInstaller folder build in dist\Veloce.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E2B1C8E-6F7B-4F7A-9D2E-5A1F0C3B7E21}
AppName=Veloce
AppVersion={#AppVersion}
AppVerName=Veloce {#AppVersion}
AppPublisher=Veloce contributors
AppPublisherURL=https://github.com/Firojpaudel/veloce
AppSupportURL=https://github.com/Firojpaudel/veloce/issues
DefaultDirName={localappdata}\Programs\Veloce
DefaultGroupName=Veloce
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=veloce-setup-windows-x64
SetupIconFile=..\assets\veloce.ico
UninstallDisplayIcon={app}\Veloce.exe
UninstallDisplayName=Veloce
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force

[Tasks]
Name: "autostart"; Description: "Start Veloce when I sign in (recommended)"; GroupDescription: "Options:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Options:"; Flags: unchecked

[Files]
Source: "..\dist\Veloce\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Veloce"; Filename: "{app}\Veloce.exe"
Name: "{autodesktop}\Veloce"; Filename: "{app}\Veloce.exe"; Tasks: desktopicon

[Registry]
; Same entry `veloce autostart enable` writes, so the in-app toggle and the installer agree
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Veloce"; \
  ValueData: """{app}\Veloce.exe"" app --background"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\Veloce.exe"; Description: "Open Veloce now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM Veloce.exe /F"; Flags: runhidden; RunOnceId: "StopVeloce"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
