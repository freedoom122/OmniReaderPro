; Veyrion Workspace — Windows installer (Inno Setup 6)
; Build:  ISCC.exe installer\veyrion_setup.iss
; Requires the PyInstaller output at dist\VeyrionWorkspace\.
; Inno Setup: https://jrsoftware.org/isinfo.php

#define MyAppName "Veyrion Workspace"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "Veyrion Studios"
#define MyAppExeName "VeyrionWorkspace.exe"
#define MyAppAssocName "Veyrion Document"
#define MyAppAssocExt ".pdf"
#define MyAppAssocKey StringChange(MyAppAssocName, " ", "") + MyAppAssocExt

[Setup]
AppId={{8C4E1B2A-5F2C-4E9B-9C1E-7A2B4D6F8E01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
OutputDir=..\dist\installer
OutputBaseFilename=VeyrionWorkspace-Setup-{#MyAppVersion}
SetupIconFile=..\resources\icons\veyrion.ico
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "assoc"; Description: "Open supported documents with {#MyAppName}"; GroupDescription: "File associations:"; Flags: checkedonce

[Files]
Source: "..\dist\VeyrionWorkspace\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

; Per-user file associations (HKCU) so no admin rights are needed.
[Registry]
Root: HKCU; Subkey: "Software\Classes\{#MyAppAssocKey}"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocName}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\{#MyAppAssocKey}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\{#MyAppAssocKey}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: assoc
; Register for each supported extension.
Root: HKCU; Subkey: "Software\Classes\.pdf"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.epub"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.mobi"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.azw"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.azw3"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.cbz"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.cbr"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.djvu"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.docx"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.odt"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.rtf"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.txt"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.md"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.html"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.csv"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.json"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.png"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.jpg"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.jpeg"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.webp"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.tiff"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.gif"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue; Tasks: assoc

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove per-user app data only if the user explicitly uninstalls with data removal;
; by default keep user documents. App data lives in %APPDATA%\VeyrionWorkspace.
Type: dirifempty; Name: "{userappdata}\VeyrionWorkspace"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then begin
    if MsgBox('Keep your documents, library, and settings? (Recommended)', mbConfirmation, MB_YESNO or MB_DEFBUTTON1) = IDNO then begin
      DelTree(ExpandConstant('{userappdata}\VeyrionWorkspace'), True, True, True);
    end;
  end;
end;