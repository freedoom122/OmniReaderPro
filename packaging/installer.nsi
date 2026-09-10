; OmniReader Pro — one-time installer (NSIS 3.x)
; Builds OmniReaderPro-Setup-1.0.0.exe from packaging/dist/OmniReaderPro.
; Usage: tools\nsis-3.11\Bin\makensis.exe packaging\installer.nsi

!define APPNAME "OmniReader Pro"
!define COMPANY "OmniReader"
!define VERSION "1.0.0"
!define EXE "OmniReaderPro.exe"

Name "${APPNAME} ${VERSION}"
OutFile "..\..\OmniReaderPro-Setup-1.0.0.exe"
InstallDir "$LOCALAPPDATA\OmniReaderPro"
InstallDirRegKey HKCU "Software\${COMPANY}\${APPNAME}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma

; ---- Presentation ------------------------------------------------------
VIProductVersion "1.0.0.0"
VIAddVersionKey ProductName "${APPNAME}"
VIAddVersionKey CompanyName "${COMPANY}"
VIAddVersionKey FileVersion "1.0.0.0"
VIAddVersionKey ProductVersion "1.0.0.0"
VIAddVersionKey FileDescription "${APPNAME} Installer"
VIAddVersionKey LegalCopyright "MIT License"

Icon "..\resources\icons\omnireader.ico"
UninstallIcon "..\resources\icons\omnireader.ico"
Caption "${APPNAME} ${VERSION} Setup"
BrandingText "${APPNAME} — READ. EDIT. ORGANIZE. CREATE."

!include "MUI2.nsh"
!define MUI_ICON "..\resources\icons\omnireader.ico"
!define MUI_UNICON "..\resources\icons\omnireader.ico"
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
  SetOutPath "$INSTDIR"
  File /r "dist\OmniReaderPro\*.*"

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
  ; User documents, settings, and library data in %APPDATA%\OmniReaderPro are preserved.
SectionEnd
