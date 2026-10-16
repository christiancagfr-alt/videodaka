[Setup]
AppId={{4D8D18C4-0FC2-4CA1-B786-56986E8DB279}
AppName=DevotionFlow
AppVersion=0.2.6
DefaultDirName={localappdata}\Programs\DevotionFlow
DefaultGroupName=DevotionFlow
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=DevotionFlow-0.2.6-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\DevotionFlow.exe
SetupIconFile=..\assets\devotionflow.ico

[Files]
Source: "..\dist\DevotionFlow\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\DevotionFlow"; Filename: "{app}\DevotionFlow.exe"
Name: "{autodesktop}\DevotionFlow"; Filename: "{app}\DevotionFlow.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\DevotionFlow.exe"; Description: "Launch DevotionFlow"; Flags: nowait postinstall skipifsilent
