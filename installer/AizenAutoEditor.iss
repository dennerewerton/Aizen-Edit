#define AppName "Aizen Auto Editor"
#define AppVersion "0.2.1"
#define AppPublisher "Aizen"
#define AppExeName "Aizen Auto Editor.exe"

[Setup]
AppId={{9A5872CE-A80E-4C46-8A57-7820D1E03E2A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=..\release
OutputBaseFilename=Aizen-Auto-Editor-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExeName}
CloseApplications=yes
RestartApplications=yes

[Files]
Source: "..\dist\Aizen Auto Editor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Abrir o Aizen Auto Editor"; Flags: nowait postinstall skipifsilent
