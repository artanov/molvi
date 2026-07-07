#define MyAppName "VoiceFlow"
#define MyAppVersion GetEnv("VF_VERSION")
#if MyAppVersion == ""
  #define MyAppVersion "0.0-dev"
#endif

[Setup]
AppId={{7E4A2C31-9B0D-4F5E-8A67-C3D1E5F70012}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\{#MyAppName}
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=VoiceFlow-Setup-{#MyAppVersion}
SetupIconFile=voiceflow.ico
UninstallDisplayIcon={app}\VoiceFlow.exe
DisableProgramGroupPage=yes
Compression=lzma2
SolidCompression=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Ярлык на рабочем столе"
Name: "autostart"; Description: "Запускать вместе с Windows"

[Files]
Source: "dist\VoiceFlow\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{userprograms}\VoiceFlow"; Filename: "{app}\VoiceFlow.exe"
Name: "{userdesktop}\VoiceFlow"; Filename: "{app}\VoiceFlow.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "VoiceFlow"; ValueData: """{app}\VoiceFlow.exe"""; \
  Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\VoiceFlow.exe"; Description: "Запустить VoiceFlow"; \
  Flags: postinstall nowait skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: string;
begin
  if CurUninstallStep = usPostUninstall then begin
    DataDir := ExpandConstant('{userappdata}\VoiceFlow');
    if DirExists(DataDir) then
      if MsgBox('Удалить настройки и загруженные компоненты VoiceFlow ('
                + DataDir + ')?', mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
