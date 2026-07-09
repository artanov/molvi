#define MyAppName "Molvi"
#define MyAppVersion GetEnv("VF_VERSION")
#if MyAppVersion == ""
  #define MyAppVersion "0.0-dev"
#endif

[Setup]
AppId={{58F3587C-61BD-4156-A61F-B419CEA48DAA}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\{#MyAppName}
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=Molvi-Setup-{#MyAppVersion}
SetupIconFile=molvi.ico
UninstallDisplayIcon={app}\Molvi.exe
DisableProgramGroupPage=yes
Compression=lzma2
SolidCompression=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Ярлык на рабочем столе"
Name: "autostart"; Description: "Запускать вместе с Windows"

[Files]
Source: "dist\Molvi\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{userprograms}\Molvi"; Filename: "{app}\Molvi.exe"
Name: "{userdesktop}\Molvi"; Filename: "{app}\Molvi.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "Molvi"; ValueData: """{app}\Molvi.exe"""; \
  Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Molvi.exe"; Description: "Запустить Molvi"; \
  Flags: postinstall nowait skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: string;
begin
  if CurUninstallStep = usPostUninstall then begin
    DataDir := ExpandConstant('{userappdata}\Molvi');
    if DirExists(DataDir) then
      if MsgBox('Удалить настройки и загруженные компоненты Molvi ('
                + DataDir + ')?', mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
