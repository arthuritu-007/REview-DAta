[Setup]
AppName=Review Data
AppVersion=0.1.0
AppPublisher=Review Data
DefaultDirName={localappdata}\ReviewData
DefaultGroupName=Review Data
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=ReviewData_Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\ReviewData.exe

[Tasks]
Name: "desktopicon"; Description: "Crear icono en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "dist\ReviewData\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "run_reviewdata.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: ".env.example"; DestDir: "{app}"; DestName: ".env"; Flags: ignoreversion

[Icons]
Name: "{group}\Review Data"; Filename: "{app}\ReviewData.exe"; WorkingDir: "{app}"; IconFilename: "{app}\ReviewData.exe"
Name: "{userdesktop}\Review Data"; Filename: "{app}\ReviewData.exe"; WorkingDir: "{app}"; IconFilename: "{app}\ReviewData.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ReviewData.exe"; Description: "Abrir Review Data"; WorkingDir: "{app}"; Flags: postinstall nowait skipifsilent
