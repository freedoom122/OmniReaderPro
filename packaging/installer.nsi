; Veyrion Workspace — one-time installer (NSIS 3.x)
; Builds VeyrionWorkspace-Setup-1.1.0.exe from the PyInstaller output at
; dist/VeyrionWorkspace, writing the installer to the repository root.
; Usage: tools\nsis-3.11\Bin\makensis.exe packaging\installer.nsi

; NSIS resolves File/OutFile relative to this script's own directory, so
; '..\' reaches the repository root from packaging/. That keeps the compile
; independent of the current working directory.

!define APPNAME "Veyrion Workspace"
!define COMPANY "Veyrion Studios"
!define VERSION "1.1.0"
!define EXE "VeyrionWorkspace.exe"

Name "${APPNAME} ${VERSION}"
OutFile "..\VeyrionWorkspace-Setup-1.1.0.exe"
InstallDir "$LOCALAPPDATA\VeyrionWorkspace"
InstallDirRegKey HKCU "Software\${COMPANY}\${APPNAME}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma

; ---- Presentation ------------------------------------------------------
VIProductVersion "1.1.0.0"
VIAddVersionKey ProductName "${APPNAME}"
VIAddVersionKey CompanyName "${COMPANY}"
VIAddVersionKey FileVersion "1.1.0.0"
VIAddVersionKey ProductVersion "1.1.0.0"
VIAddVersionKey FileDescription "${APPNAME} Installer"
VIAddVersionKey LegalCopyright "MIT License"

Icon "..\resources\icons\veyrion.ico"
UninstallIcon "..\resources\icons\veyrion.ico"
Caption "${APPNAME} ${VERSION} Setup"
BrandingText "${APPNAME} — READ. EDIT. ORGANIZE. CREATE."

!include "MUI2.nsh"
!define MUI_ICON "..\resources\icons\veyrion.ico"
!define MUI_UNICON "..\resources\icons\veyrion.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\${EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Launch ${APPNAME}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

; ---- Install -----------------------------------------------------------
Section "Install"
  ; Remove a previous-name install so upgrading users never end up with two
  ; copies side by side after the rebrand. The folder removal is guarded by
  ; an executable check, so a tampered registry value cannot make the
  ; installer delete an unrelated directory.
  Delete "$DESKTOP\OmniReader Pro.lnk"
  Delete "$SMPROGRAMS\OmniReader\OmniReader Pro.lnk"
  RMDir "$SMPROGRAMS\OmniReader"
  ReadRegStr $0 HKCU "Software\OmniReader\OmniReader Pro" "InstallDir"
  IfFileExists "$0\OmniReaderPro.exe" 0 legacy_cleanup_done
    RMDir /r "$0"
  legacy_cleanup_done:
  DeleteRegKey HKCU "Software\OmniReader\OmniReader Pro"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\OmniReader Pro"

  SetOutPath "$INSTDIR"
  File /r "..\dist\VeyrionWorkspace\*.*"

  ; Start Menu shortcut
  CreateDirectory "$SMPROGRAMS\${COMPANY}"
  CreateShortCut "$SMPROGRAMS\${COMPANY}\${APPNAME}.lnk" "$INSTDIR\${EXE}"

  ; Desktop shortcut
  CreateShortCut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\${EXE}"

  ; Uninstaller + registry keys
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\${COMPANY}\${APPNAME}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" \
    "DisplayName" "${APPNAME} ${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" \
    "UninstallString" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" \
    "DisplayIcon" "$INSTDIR\${EXE}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" \
    "Publisher" "${COMPANY}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" \
    "DisplayVersion" "${VERSION}"
SectionEnd

; ---- Uninstall ---------------------------------------------------------
Section "Uninstall"
  Delete "$DESKTOP\${APPNAME}.lnk"
  Delete "$SMPROGRAMS\${COMPANY}\${APPNAME}.lnk"
  RMDir "$SMPROGRAMS\${COMPANY}"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
  DeleteRegKey HKCU "Software\${COMPANY}\${APPNAME}"
  ; User documents, settings, and library data in %APPDATA%\VeyrionWorkspace are preserved.
SectionEnd
